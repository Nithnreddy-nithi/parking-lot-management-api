import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.parking.enums import GateType, SpotOperationalStatus, SpotType, VehicleType
from apps.parking.models import Floor, Gate, ParkingLot, ParkingSpot, Vehicle


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def customer(db):
    return User.objects.create_user(username="session-customer", password="password")


@pytest.fixture
def other_customer(db):
    return User.objects.create_user(username="session-other", password="password")


@pytest.fixture
def operator(db):
    return User.objects.create_user(
        username="session-operator",
        password="password",
        role=User.Role.OPERATOR,
    )


@pytest.fixture
def app_admin(db):
    return User.objects.create_user(
        username="session-admin",
        password="password",
        role=User.Role.ADMIN,
    )


@pytest.fixture
def parking_lot(db):
    return ParkingLot.objects.create(code="ENTRY", name="Entry Lot", address="Test address")


@pytest.fixture
def floor(parking_lot):
    return Floor.objects.create(parking_lot=parking_lot, code="G", name="Ground", level=0)


@pytest.fixture
def entry_gate(parking_lot):
    return Gate.objects.create(
        parking_lot=parking_lot,
        code="IN",
        name="Entry",
        gate_type=GateType.ENTRY,
    )


@pytest.fixture
def compact_spot(floor):
    return ParkingSpot.objects.create(
        floor=floor,
        number="C-01",
        spot_type=SpotType.COMPACT,
        operational_status=SpotOperationalStatus.ENABLED,
    )


@pytest.fixture
def vehicle(customer):
    return Vehicle.objects.create(
        owner=customer,
        registration_number="KA01AB1234",
        vehicle_type=VehicleType.CAR,
    )


def authenticate(client, user):
    client.force_authenticate(user=user)
    return client
