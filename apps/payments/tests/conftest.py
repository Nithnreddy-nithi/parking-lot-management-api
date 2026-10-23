from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.parking.enums import GateType, SpotType, VehicleType
from apps.parking.models import Floor, Gate, ParkingLot, ParkingSpot, Vehicle
from apps.pricing.models import CheckoutQuote
from apps.sessions.enums import SessionStatus
from apps.sessions.models import ParkingSession


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def customer(db):
    return User.objects.create_user(username="payment-customer", password="password")


@pytest.fixture
def other_customer(db):
    return User.objects.create_user(username="payment-other", password="password")


@pytest.fixture
def operator(db):
    return User.objects.create_user(
        username="payment-operator",
        password="password",
        role=User.Role.OPERATOR,
    )


@pytest.fixture
def payment_context(customer, operator):
    lot = ParkingLot.objects.create(code="PAY", name="Payment Lot", address="Address")
    floor = Floor.objects.create(parking_lot=lot, code="G", name="Ground", level=0)
    entry_gate = Gate.objects.create(
        parking_lot=lot,
        code="IN",
        name="Entry",
        gate_type=GateType.ENTRY,
    )
    exit_gate = Gate.objects.create(
        parking_lot=lot,
        code="OUT",
        name="Exit",
        gate_type=GateType.EXIT,
    )
    spot = ParkingSpot.objects.create(floor=floor, number="C-1", spot_type=SpotType.COMPACT)
    vehicle = Vehicle.objects.create(
        owner=customer,
        registration_number="PAY123",
        vehicle_type=VehicleType.CAR,
    )
    session = ParkingSession.objects.create(
        vehicle=vehicle,
        spot=spot,
        entry_gate=entry_gate,
        entered_by=operator,
        status=SessionStatus.PAYMENT_PENDING,
        registration_number_snapshot=vehicle.registration_number,
        vehicle_type_snapshot=vehicle.vehicle_type,
    )
    quote = CheckoutQuote.objects.create(
        parking_session=session,
        calculated_until=timezone.now(),
        amount=Decimal("90.00"),
        currency="INR",
        calculation_breakdown={"calculator": "HOURLY_V1"},
        created_by=operator,
    )
    return {
        "lot": lot,
        "floor": floor,
        "entry_gate": entry_gate,
        "exit_gate": exit_gate,
        "spot": spot,
        "vehicle": vehicle,
        "session": session,
        "quote": quote,
    }


def authenticate(client, user):
    client.force_authenticate(user=user)
    return client
