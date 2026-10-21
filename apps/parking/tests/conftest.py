import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.parking.enums import SpotOperationalStatus, SpotType
from apps.parking.models import Floor, ParkingLot, ParkingSpot


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def customer(db):
    return User.objects.create_user(username="parking-customer", password="test-password")


@pytest.fixture
def other_customer(db):
    return User.objects.create_user(username="other-customer", password="test-password")


@pytest.fixture
def operator(db):
    return User.objects.create_user(
        username="parking-operator",
        password="test-password",
        role=User.Role.OPERATOR,
    )


@pytest.fixture
def app_admin(db):
    return User.objects.create_user(
        username="parking-admin",
        password="test-password",
        role=User.Role.ADMIN,
    )


@pytest.fixture
def parking_lot(db):
    return ParkingLot.objects.create(
        code="LOT-A",
        name="Lot A",
        address="Address A",
    )


@pytest.fixture
def floor(parking_lot):
    return Floor.objects.create(
        parking_lot=parking_lot,
        code="G",
        name="Ground",
        level=0,
    )


@pytest.fixture
def parking_spot(floor):
    return ParkingSpot.objects.create(
        floor=floor,
        number="G-01",
        spot_type=SpotType.COMPACT,
        operational_status=SpotOperationalStatus.ENABLED,
    )


def authenticate(api_client, user):
    api_client.force_authenticate(user=user)
    return api_client
