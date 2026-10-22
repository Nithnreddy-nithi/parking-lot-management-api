import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.parking.enums import GateType, SpotOperationalStatus, SpotType, VehicleType
from apps.parking.models import Floor, Gate, ParkingLot, ParkingSpot, Vehicle
from apps.pricing.enums import Currency
from apps.pricing.models import PricingPolicy


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
def pricing_policies(parking_lot, app_admin):
    return {
        vehicle_type: PricingPolicy.objects.create(
            parking_lot=parking_lot,
            vehicle_type=vehicle_type,
            version=1,
            currency=Currency.INR,
            hourly_rate=rate,
            grace_minutes=15,
            daily_cap=cap,
            created_by=app_admin,
        )
        for vehicle_type, rate, cap in (
            (VehicleType.MOTORCYCLE, "20.00", "200.00"),
            (VehicleType.CAR, "30.00", "300.00"),
            (VehicleType.TRUCK, "50.00", "500.00"),
        )
    }


@pytest.fixture
def pricing_policy(pricing_policies):
    return pricing_policies[VehicleType.CAR]


@pytest.fixture
def entry_gate(parking_lot, pricing_policies):
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
