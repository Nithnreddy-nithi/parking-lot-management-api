from datetime import timedelta

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.parking.enums import SpotOperationalStatus, SpotType, VehicleType
from apps.parking.models import ParkingSpot, Vehicle
from apps.parking.services.configuration import update_parking_spot
from apps.parking.services.vehicles import update_vehicle
from apps.sessions.enums import SessionStatus
from apps.sessions.models import ParkingSession
from apps.sessions.tests.test_reads_and_availability import make_session


@pytest.mark.django_db(transaction=True)
def test_database_prevents_two_open_sessions_for_one_spot(
    customer, other_customer, operator, entry_gate, compact_spot
):
    first = Vehicle.objects.create(
        owner=customer, registration_number="UNIQUE1", vehicle_type=VehicleType.CAR
    )
    second = Vehicle.objects.create(
        owner=other_customer, registration_number="UNIQUE2", vehicle_type=VehicleType.CAR
    )
    make_session(vehicle=first, spot=compact_spot, gate=entry_gate, actor=operator)

    with pytest.raises(IntegrityError), transaction.atomic():
        make_session(vehicle=second, spot=compact_spot, gate=entry_gate, actor=operator)
    assert ParkingSession.objects.count() == 1


@pytest.mark.django_db(transaction=True)
def test_database_prevents_two_open_sessions_for_one_vehicle(
    vehicle, operator, entry_gate, compact_spot, floor
):
    other_spot = ParkingSpot.objects.create(floor=floor, number="C-02", spot_type=SpotType.COMPACT)
    make_session(vehicle=vehicle, spot=compact_spot, gate=entry_gate, actor=operator)

    with pytest.raises(IntegrityError), transaction.atomic():
        make_session(vehicle=vehicle, spot=other_spot, gate=entry_gate, actor=operator)
    assert ParkingSession.objects.count() == 1


@pytest.mark.django_db(transaction=True)
def test_database_enforces_closed_at_lifecycle_constraints(
    vehicle, operator, entry_gate, compact_spot
):
    with pytest.raises(IntegrityError), transaction.atomic():
        ParkingSession.objects.create(
            vehicle=vehicle,
            spot=compact_spot,
            entry_gate=entry_gate,
            entered_by=operator,
            status=SessionStatus.CLOSED,
            closed_at=None,
            registration_number_snapshot=vehicle.registration_number,
            vehicle_type_snapshot=vehicle.vehicle_type,
        )

    session = make_session(vehicle=vehicle, spot=compact_spot, gate=entry_gate, actor=operator)
    with pytest.raises(IntegrityError), transaction.atomic():
        ParkingSession.objects.filter(pk=session.pk).update(closed_at=timezone.now())

    with pytest.raises(IntegrityError), transaction.atomic():
        ParkingSession.objects.filter(pk=session.pk).update(
            status=SessionStatus.CLOSED,
            closed_at=session.entered_at - timedelta(seconds=1),
        )


@pytest.mark.django_db
@pytest.mark.parametrize(
    "data",
    [
        {"registration_number": "NEW123"},
        {"vehicle_type": VehicleType.TRUCK},
        {"is_active": False},
    ],
)
def test_open_session_blocks_vehicle_identity_changes(
    vehicle, operator, entry_gate, compact_spot, data
):
    make_session(vehicle=vehicle, spot=compact_spot, gate=entry_gate, actor=operator)
    with pytest.raises(Exception) as error:
        update_vehicle(vehicle=vehicle, data=data)
    assert getattr(error.value, "status_code", None) == 409
    vehicle.refresh_from_db()
    assert vehicle.registration_number == "KA01AB1234"
    assert vehicle.vehicle_type == VehicleType.CAR
    assert vehicle.is_active is True


@pytest.mark.django_db
@pytest.mark.parametrize("data", [{"number": "NEW-1"}, {"spot_type": SpotType.LARGE}])
def test_open_session_blocks_spot_identity_changes(
    vehicle, operator, entry_gate, compact_spot, data
):
    make_session(vehicle=vehicle, spot=compact_spot, gate=entry_gate, actor=operator)
    with pytest.raises(Exception) as error:
        update_parking_spot(parking_spot=compact_spot, data=data)
    assert getattr(error.value, "status_code", None) == 409


@pytest.mark.django_db
def test_occupied_spot_can_be_put_in_maintenance_without_releasing_occupancy(
    vehicle, operator, entry_gate, compact_spot
):
    session = make_session(vehicle=vehicle, spot=compact_spot, gate=entry_gate, actor=operator)
    updated = update_parking_spot(
        parking_spot=compact_spot,
        data={"operational_status": SpotOperationalStatus.MAINTENANCE},
    )
    assert updated.operational_status == SpotOperationalStatus.MAINTENANCE
    assert ParkingSession.objects.filter(pk=session.pk, status=SessionStatus.ACTIVE).exists()
