from decimal import Decimal
from unittest.mock import patch

import pytest
from django.core.exceptions import ValidationError
from django.db import DatabaseError

from apps.parking.enums import SpotType
from apps.parking.models import ParkingSpot
from apps.pricing.models import PricingPolicy, PricingSnapshot
from apps.pricing.services import publish_policy
from apps.sessions.models import ParkingSession
from apps.sessions.services import build_entry_service
from apps.sessions.tests.conftest import authenticate
from apps.sessions.tests.test_entry_api import ENTRY_URL


@pytest.mark.django_db
def test_entry_captures_immutable_pricing_snapshot(
    api_client, operator, vehicle, entry_gate, compact_spot, pricing_policy
):
    response = authenticate(api_client, operator).post(
        ENTRY_URL,
        {"vehicle_id": vehicle.pk, "entry_gate_id": entry_gate.pk},
        format="json",
    )
    snapshot = PricingSnapshot.objects.get(parking_session_id=response.data["id"])
    assert response.status_code == 201
    assert snapshot.pricing_policy == pricing_policy
    assert snapshot.policy_version == 1
    assert snapshot.currency == "INR"
    assert snapshot.hourly_rate == Decimal("30.00")
    assert snapshot.grace_minutes == 15
    assert snapshot.daily_cap == Decimal("300.00")
    assert snapshot.calculator_version == "HOURLY_V1"

    snapshot.hourly_rate = Decimal("1.00")
    with pytest.raises(ValidationError):
        snapshot.save()


@pytest.mark.django_db
def test_car_in_large_spot_uses_car_policy(
    api_client, operator, vehicle, entry_gate, floor, pricing_policy
):
    large = ParkingSpot.objects.create(floor=floor, number="L-ONLY", spot_type=SpotType.LARGE)
    response = authenticate(api_client, operator).post(
        ENTRY_URL,
        {"vehicle_id": vehicle.pk, "entry_gate_id": entry_gate.pk},
        format="json",
    )
    snapshot = PricingSnapshot.objects.get(parking_session_id=response.data["id"])
    assert response.status_code == 201
    assert response.data["spot_id"] == large.pk
    assert snapshot.pricing_policy_id == pricing_policy.pk
    assert snapshot.hourly_rate == Decimal("30.00")


@pytest.mark.django_db
def test_later_policy_version_does_not_change_entry_snapshot(
    operator, app_admin, vehicle, entry_gate, compact_spot, pricing_policy
):
    session = build_entry_service().enter(
        vehicle_id=vehicle.pk,
        entry_gate_id=entry_gate.pk,
        actor=operator,
    )
    publish_policy(
        data={
            "parking_lot": entry_gate.parking_lot,
            "vehicle_type": vehicle.vehicle_type,
            "currency": "INR",
            "hourly_rate": Decimal("90.00"),
            "grace_minutes": 0,
            "daily_cap": None,
        },
        actor=app_admin,
    )
    snapshot = PricingSnapshot.objects.get(parking_session=session)
    assert snapshot.policy_version == 1
    assert snapshot.hourly_rate == Decimal("30.00")
    assert PricingPolicy.objects.get(pk=pricing_policy.pk).is_active is False


@pytest.mark.django_db
def test_missing_pricing_blocks_entry_without_partial_writes(
    api_client, operator, vehicle, entry_gate, compact_spot, pricing_policy
):
    pricing_policy.delete()
    response = authenticate(api_client, operator).post(
        ENTRY_URL,
        {"vehicle_id": vehicle.pk, "entry_gate_id": entry_gate.pk},
        format="json",
    )
    assert response.status_code == 409
    assert response.data["error"]["code"] == "PRICING_NOT_CONFIGURED"
    assert not ParkingSession.objects.exists()
    assert not PricingSnapshot.objects.exists()


@pytest.mark.django_db
def test_snapshot_failure_rolls_back_session(
    operator, vehicle, entry_gate, compact_spot, pricing_policy
):
    with (
        patch("apps.sessions.services.entry.create_snapshot", side_effect=DatabaseError("boom")),
        pytest.raises(DatabaseError),
    ):
        build_entry_service().enter(
            vehicle_id=vehicle.pk,
            entry_gate_id=entry_gate.pk,
            actor=operator,
        )
    assert not ParkingSession.objects.exists()
    assert not PricingSnapshot.objects.exists()
