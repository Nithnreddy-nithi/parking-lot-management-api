import pytest
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError

from apps.parking.enums import SpotOperationalStatus, SpotType
from apps.parking.models import Floor, Gate, ParkingLot, ParkingSpot, Vehicle


@pytest.mark.django_db
@pytest.mark.parametrize(
    "factory",
    [
        lambda lot, floor, user: Gate.objects.create(
            parking_lot=lot, code="G", name="Gate", gate_type="INVALID"
        ),
        lambda lot, floor, user: ParkingSpot.objects.create(
            floor=floor, number="1", spot_type="INVALID"
        ),
        lambda lot, floor, user: ParkingSpot.objects.create(
            floor=floor,
            number="2",
            spot_type=SpotType.COMPACT,
            operational_status="OCCUPIED",
        ),
        lambda lot, floor, user: Vehicle.objects.create(
            owner=user, registration_number="KA01AA9999", vehicle_type="INVALID"
        ),
    ],
)
def test_database_enum_constraints(factory, parking_lot, floor, customer):
    with pytest.raises(IntegrityError), transaction.atomic():
        factory(parking_lot, floor, customer)


@pytest.mark.django_db
def test_database_nonblank_and_unique_constraints(parking_lot):
    with pytest.raises(IntegrityError), transaction.atomic():
        ParkingLot.objects.create(code=" ", name="Blank", address="X")
    with pytest.raises(IntegrityError), transaction.atomic():
        ParkingLot.objects.create(code="lot-a", name="Duplicate", address="X")


@pytest.mark.django_db
def test_parent_relationships_are_protected(parking_lot, floor, parking_spot):
    with pytest.raises(ProtectedError):
        floor.delete()
    with pytest.raises(ProtectedError):
        parking_lot.delete()


@pytest.mark.django_db
def test_seed_command_is_idempotent_and_preserves_customized_data():
    call_command("seed_parking")
    counts = (
        ParkingLot.objects.count(),
        Floor.objects.count(),
        Gate.objects.count(),
        ParkingSpot.objects.count(),
    )
    parking_lot = ParkingLot.objects.get(code="DEMO")
    parking_lot.name = "Customized Demo Name"
    parking_lot.save(update_fields=["name", "updated_at"])

    call_command("seed_parking")

    assert (
        ParkingLot.objects.count(),
        Floor.objects.count(),
        Gate.objects.count(),
        ParkingSpot.objects.count(),
    ) == counts
    parking_lot.refresh_from_db()
    assert parking_lot.name == "Customized Demo Name"
    assert SpotOperationalStatus.MAINTENANCE in ParkingSpot.objects.values_list(
        "operational_status", flat=True
    )
    assert SpotOperationalStatus.DISABLED in ParkingSpot.objects.values_list(
        "operational_status", flat=True
    )
