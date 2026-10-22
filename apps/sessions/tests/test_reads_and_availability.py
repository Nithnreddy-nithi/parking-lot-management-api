from datetime import timedelta

import pytest
from django.utils import timezone

from apps.parking.enums import SpotOperationalStatus, SpotType, VehicleType
from apps.parking.models import ParkingSpot, Vehicle
from apps.sessions.enums import SessionStatus
from apps.sessions.models import ParkingSession
from apps.sessions.tests.conftest import authenticate


def make_session(*, vehicle, spot, gate, actor, status=SessionStatus.ACTIVE):
    return ParkingSession.objects.create(
        vehicle=vehicle,
        spot=spot,
        entry_gate=gate,
        entered_by=actor,
        status=status,
        registration_number_snapshot=vehicle.registration_number,
        vehicle_type_snapshot=vehicle.vehicle_type,
    )


@pytest.mark.django_db
def test_customer_reads_only_owned_sessions_and_other_detail_is_404(
    api_client,
    customer,
    other_customer,
    operator,
    vehicle,
    entry_gate,
    compact_spot,
    floor,
):
    owned = make_session(vehicle=vehicle, spot=compact_spot, gate=entry_gate, actor=operator)
    other_vehicle = Vehicle.objects.create(
        owner=other_customer,
        registration_number="OTHER123",
        vehicle_type=VehicleType.TRUCK,
    )
    other_spot = ParkingSpot.objects.create(
        floor=floor,
        number="L-01",
        spot_type=SpotType.LARGE,
    )
    other = make_session(
        vehicle=other_vehicle,
        spot=other_spot,
        gate=entry_gate,
        actor=operator,
    )

    client = authenticate(api_client, customer)
    response = client.get("/api/v1/parking-sessions/")
    hidden = client.get(f"/api/v1/parking-sessions/{other.pk}/")

    assert response.status_code == 200
    assert [item["id"] for item in response.data["results"]] == [owned.pk]
    assert hidden.status_code == 404
    assert "owner" not in response.data["results"][0]


@pytest.mark.django_db
def test_staff_reads_all_and_filters_strictly(
    api_client, operator, customer, vehicle, entry_gate, compact_spot
):
    session = make_session(vehicle=vehicle, spot=compact_spot, gate=entry_gate, actor=operator)
    client = authenticate(api_client, operator)

    response = client.get(
        "/api/v1/parking-sessions/",
        {
            "status": SessionStatus.ACTIVE,
            "lot": entry_gate.parking_lot_id,
            "vehicle": vehicle.pk,
            "entry_date_from": timezone.localdate().isoformat(),
            "entry_date_to": timezone.localdate().isoformat(),
        },
    )
    invalid = client.get("/api/v1/parking-sessions/?unknown=value")
    reversed_dates = client.get(
        "/api/v1/parking-sessions/?entry_date_from=2026-02-02&entry_date_to=2026-02-01"
    )

    assert response.status_code == 200
    assert [item["id"] for item in response.data["results"]] == [session.pk]
    assert invalid.status_code == 400
    assert reversed_dates.status_code == 400


@pytest.mark.django_db
def test_customer_cannot_use_staff_vehicle_filter(
    api_client, customer, vehicle, entry_gate, compact_spot, operator
):
    make_session(vehicle=vehicle, spot=compact_spot, gate=entry_gate, actor=operator)
    response = authenticate(api_client, customer).get(
        f"/api/v1/parking-sessions/?vehicle={vehicle.pk}"
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_session_endpoints_do_not_allow_patch_or_delete(
    api_client, operator, vehicle, entry_gate, compact_spot
):
    session = make_session(vehicle=vehicle, spot=compact_spot, gate=entry_gate, actor=operator)
    client = authenticate(api_client, operator)
    assert client.patch(f"/api/v1/parking-sessions/{session.pk}/", {}).status_code == 405
    assert client.delete(f"/api/v1/parking-sessions/{session.pk}/").status_code == 405


@pytest.mark.django_db
def test_availability_counts_operational_and_occupancy_separately(
    api_client, customer, operator, vehicle, parking_lot, floor, entry_gate, compact_spot
):
    motorcycle = ParkingSpot.objects.create(
        floor=floor,
        number="M-01",
        spot_type=SpotType.MOTORCYCLE,
        operational_status=SpotOperationalStatus.MAINTENANCE,
    )
    large = ParkingSpot.objects.create(
        floor=floor,
        number="L-01",
        spot_type=SpotType.LARGE,
        operational_status=SpotOperationalStatus.DISABLED,
    )
    make_session(vehicle=vehicle, spot=motorcycle, gate=entry_gate, actor=operator)

    response = authenticate(api_client, customer).get(
        f"/api/v1/parking-lots/{parking_lot.pk}/availability/"
    )

    assert response.status_code == 200
    counts = {item["spot_type"]: item for item in response.data["counts"]}
    assert counts[SpotType.COMPACT] == {
        "spot_type": SpotType.COMPACT,
        "total": 1,
        "operationally_enabled": 1,
        "occupied": 0,
        "available": 1,
    }
    assert counts[SpotType.MOTORCYCLE]["occupied"] == 1
    assert counts[SpotType.MOTORCYCLE]["available"] == 0
    assert counts[SpotType.LARGE]["total"] == 1
    assert counts[SpotType.LARGE]["available"] == 0
    assert large.pk


@pytest.mark.django_db
def test_inactive_parent_contributes_zero_available(
    api_client, customer, parking_lot, floor, compact_spot
):
    floor.is_active = False
    floor.save(update_fields=["is_active"])
    response = authenticate(api_client, customer).get(
        f"/api/v1/parking-lots/{parking_lot.pk}/availability/"
    )
    compact = next(
        item for item in response.data["counts"] if item["spot_type"] == SpotType.COMPACT
    )
    assert compact["total"] == 1
    assert compact["operationally_enabled"] == 1
    assert compact["available"] == 0

    floor.is_active = True
    floor.save(update_fields=["is_active"])
    parking_lot.is_active = False
    parking_lot.save(update_fields=["is_active"])
    response = api_client.get(f"/api/v1/parking-lots/{parking_lot.pk}/availability/")
    compact = next(
        item for item in response.data["counts"] if item["spot_type"] == SpotType.COMPACT
    )
    assert compact["available"] == 0


@pytest.mark.django_db
def test_session_order_is_deterministic(api_client, operator, customer, entry_gate, floor):
    older_vehicle = Vehicle.objects.create(
        owner=customer,
        registration_number="ORDER1",
        vehicle_type=VehicleType.CAR,
    )
    newer_vehicle = Vehicle.objects.create(
        owner=customer,
        registration_number="ORDER2",
        vehicle_type=VehicleType.CAR,
    )
    first_spot = ParkingSpot.objects.create(floor=floor, number="O-1", spot_type=SpotType.COMPACT)
    second_spot = ParkingSpot.objects.create(floor=floor, number="O-2", spot_type=SpotType.COMPACT)
    older = make_session(vehicle=older_vehicle, spot=first_spot, gate=entry_gate, actor=operator)
    newer = make_session(vehicle=newer_vehicle, spot=second_spot, gate=entry_gate, actor=operator)
    ParkingSession.objects.filter(pk=older.pk).update(entered_at=timezone.now() - timedelta(days=1))

    response = authenticate(api_client, operator).get("/api/v1/parking-sessions/")
    assert [item["id"] for item in response.data["results"]] == [newer.pk, older.pk]
