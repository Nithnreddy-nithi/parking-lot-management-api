import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.parking.models import ParkingLot


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def app_admin(db):
    return User.objects.create_user(username="pricing-admin", role=User.Role.ADMIN)


@pytest.fixture
def operator(db):
    return User.objects.create_user(username="pricing-operator", role=User.Role.OPERATOR)


@pytest.fixture
def customer(db):
    return User.objects.create_user(username="pricing-customer")


@pytest.fixture
def parking_lot(db):
    return ParkingLot.objects.create(code="PRICE", name="Pricing Lot", address="Address")


def authenticate(client, user):
    client.force_authenticate(user=user)
    return client
