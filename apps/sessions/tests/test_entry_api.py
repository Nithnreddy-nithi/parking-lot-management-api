from unittest.mock import patch

import pytest
from django.db import DatabaseError

from apps.parking.enums import GateType, SpotType, VehicleType
from apps.parking.models import Floor, ParkingSpot, Vehicle
from apps.sessions.allocation import AllocationStrategy
from apps.sessions.models import ParkingSession
from apps.sessions.services.entry import EntryService
from apps.sessions.tests.conftest import authenticate

ENTRY_URL = "/api/v1/parking-sessions/entry/"


def enter(client, vehicle, gate, **extra):
    return client.post(
        ENTRY_URL,
        {"vehicle_id": vehicle.pk, "entry_gate_id": gate.pk, **extra},
        format="json",
    )


@pytest.mark.django_db
def test_operator_enters_vehicle_and_receives_safe_ticket(
    api_client, operator, vehicle, entry_gate, compact_spot
):
    response = enter(authenticate(api_client, operator), vehicle, entry_gate)

    assert response.status_code == 201
    assert response.data["vehicle_registration"] == "KA01AB1234"
    assert response.data["spot_id"] == compact_spot.pk
    assert response.data["parking_lot_id"] == entry_gate.parking_lot_id
    assert response.data["status"] == "ACTIVE"
    assert len(response.data["ticket_reference"]) >= 24
    assert "entered_by" not in response.data
    session = ParkingSession.objects.get()
    assert session.entered_by == operator
    assert session.closed_at is None


@pytest.mark.django_db
def test_entry_rejects_protected_client_fields(
    api_client, operator, vehicle, entry_gate, compact_spot
):
    response = enter(
        authenticate(api_client, operator),
        vehicle,
        entry_gate,
        status="CLOSED",
        spot_id=compact_spot.pk,
        ticket_reference="chosen-by-client",
    )

    assert response.status_code == 400
    assert set(response.data["error"]["fields"]) == {"spot_id", "status", "ticket_reference"}
    assert not ParkingSession.objects.exists()


@pytest.mark.django_db
def test_entry_is_staff_only(api_client, customer, vehicle, entry_gate, compact_spot):
    assert enter(api_client, vehicle, entry_gate).status_code == 401
    assert enter(authenticate(api_client, customer), vehicle, entry_gate).status_code == 403
    assert not ParkingSession.objects.exists()


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("vehicle_type", "spot_type"),
    [
        (VehicleType.MOTORCYCLE, SpotType.MOTORCYCLE),
        (VehicleType.CAR, SpotType.COMPACT),
        (VehicleType.CAR, SpotType.LARGE),
        (VehicleType.TRUCK, SpotType.LARGE),
    ],
)
def test_compatibility_rules(
    api_client, operator, customer, parking_lot, floor, entry_gate, vehicle_type, spot_type
):
    candidate = ParkingSpot.objects.create(
        floor=floor,
        number=f"{spot_type}-01",
        spot_type=spot_type,
    )
    entering_vehicle = Vehicle.objects.create(
        owner=customer,
        registration_number=f"TEST{vehicle_type}{spot_type}",
        vehicle_type=vehicle_type,
    )

    response = enter(authenticate(api_client, operator), entering_vehicle, entry_gate)

    assert response.status_code == 201
    assert response.data["spot_id"] == candidate.pk


@pytest.mark.django_db
def test_car_prefers_compact_then_deterministic_floor_number_and_id(
    api_client, operator, vehicle, entry_gate, parking_lot
):
    upper = Floor.objects.create(parking_lot=parking_lot, code="L1", name="Upper", level=1)
    ground = Floor.objects.create(parking_lot=parking_lot, code="G2", name="Ground", level=0)
    ParkingSpot.objects.create(floor=upper, number="A-01", spot_type=SpotType.COMPACT)
    expected = ParkingSpot.objects.create(floor=ground, number="B-02", spot_type=SpotType.COMPACT)
    ParkingSpot.objects.create(floor=ground, number="C-01", spot_type=SpotType.COMPACT)
    ParkingSpot.objects.create(floor=ground, number="A-00", spot_type=SpotType.LARGE)

    response = enter(authenticate(api_client, operator), vehicle, entry_gate)

    assert response.status_code == 201
    assert response.data["spot_id"] == expected.pk


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("resource", "code"),
    [
        ("lot", "LOT_INACTIVE"),
        ("gate", "ENTRY_GATE_INACTIVE"),
        ("vehicle", "VEHICLE_INACTIVE"),
    ],
)
def test_inactive_resources_conflict(
    api_client, operator, vehicle, entry_gate, compact_spot, resource, code
):
    instance = {
        "lot": entry_gate.parking_lot,
        "gate": entry_gate,
        "vehicle": vehicle,
    }[resource]
    instance.is_active = False
    instance.save(update_fields=["is_active"])

    response = enter(authenticate(api_client, operator), vehicle, entry_gate)

    assert response.status_code == 409
    assert response.data["error"]["code"] == code
    assert not ParkingSession.objects.exists()


@pytest.mark.django_db
def test_inactive_floor_and_incompatible_capacity_return_no_spot(
    api_client, operator, vehicle, entry_gate, compact_spot
):
    compact_spot.floor.is_active = False
    compact_spot.floor.save(update_fields=["is_active"])
    response = enter(authenticate(api_client, operator), vehicle, entry_gate)
    assert response.status_code == 409
    assert response.data["error"]["code"] == "NO_COMPATIBLE_SPOT"

    compact_spot.floor.is_active = True
    compact_spot.floor.save(update_fields=["is_active"])
    compact_spot.spot_type = SpotType.MOTORCYCLE
    compact_spot.save(update_fields=["spot_type"])
    response = enter(api_client, vehicle, entry_gate)
    assert response.status_code == 409
    assert response.data["error"]["code"] == "NO_COMPATIBLE_SPOT"


@pytest.mark.django_db
def test_exit_only_gate_rejected(api_client, operator, vehicle, entry_gate, compact_spot):
    entry_gate.gate_type = GateType.EXIT
    entry_gate.save(update_fields=["gate_type"])

    response = enter(authenticate(api_client, operator), vehicle, entry_gate)

    assert response.status_code == 409
    assert response.data["error"]["code"] == "GATE_NOT_ENTRY_CAPABLE"


@pytest.mark.django_db
def test_both_gate_is_entry_capable(api_client, operator, vehicle, entry_gate, compact_spot):
    entry_gate.gate_type = GateType.BOTH
    entry_gate.save(update_fields=["gate_type"])

    response = enter(authenticate(api_client, operator), vehicle, entry_gate)

    assert response.status_code == 201
    assert response.data["spot_id"] == compact_spot.pk


@pytest.mark.django_db
def test_full_lot_and_duplicate_vehicle_are_conflicts(
    api_client, operator, customer, vehicle, entry_gate, compact_spot
):
    client = authenticate(api_client, operator)
    assert enter(client, vehicle, entry_gate).status_code == 201
    duplicate = enter(client, vehicle, entry_gate)
    assert duplicate.status_code == 409
    assert duplicate.data["error"]["code"] == "VEHICLE_ALREADY_PARKED"

    another = Vehicle.objects.create(
        owner=customer,
        registration_number="KA02CD5678",
        vehicle_type=VehicleType.CAR,
    )
    full = enter(client, another, entry_gate)
    assert full.status_code == 409
    assert full.data["error"]["code"] == "NO_COMPATIBLE_SPOT"
    assert ParkingSession.objects.count() == 1


@pytest.mark.django_db
def test_session_snapshots_survive_vehicle_change(
    api_client, operator, vehicle, entry_gate, compact_spot
):
    response = enter(authenticate(api_client, operator), vehicle, entry_gate)
    Vehicle.objects.filter(pk=vehicle.pk).update(
        registration_number="CHANGED",
        vehicle_type=VehicleType.TRUCK,
    )

    session = ParkingSession.objects.get(pk=response.data["id"])
    assert session.registration_number_snapshot == "KA01AB1234"
    assert session.vehicle_type_snapshot == VehicleType.CAR


class LargeFirstTestStrategy:
    def spot_type_preferences(self, vehicle_type: str) -> tuple[str, ...]:
        return (SpotType.LARGE, SpotType.COMPACT)

    def ordering_fields(self) -> tuple[str, ...]:
        return ("floor__level", "number", "id")


@pytest.mark.django_db
def test_entry_service_accepts_substitutable_strategy(operator, vehicle, entry_gate, compact_spot):
    large = ParkingSpot.objects.create(
        floor=compact_spot.floor,
        number="L-01",
        spot_type=SpotType.LARGE,
    )
    strategy: AllocationStrategy = LargeFirstTestStrategy()

    session = EntryService(allocation_strategy=strategy).enter(
        vehicle_id=vehicle.pk,
        entry_gate_id=entry_gate.pk,
        actor=operator,
    )

    assert session.spot_id == large.pk


@pytest.mark.django_db
def test_failed_creation_rolls_back_without_partial_session(
    operator, vehicle, entry_gate, compact_spot
):
    service = EntryService(allocation_strategy=LargeFirstTestStrategy())
    with (
        patch(
            "apps.sessions.services.entry.create_active_session", side_effect=DatabaseError("boom")
        ),
        pytest.raises(DatabaseError),
    ):
        service.enter(vehicle_id=vehicle.pk, entry_gate_id=entry_gate.pk, actor=operator)

    assert not ParkingSession.objects.exists()
