from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.db import IntegrityError, transaction

from apps.parking.enums import SpotType, VehicleType
from apps.parking.models import ParkingSpot, Vehicle
from apps.pricing.models import CheckoutQuote, PricingSnapshot
from apps.sessions.enums import SessionStatus
from apps.sessions.models import ParkingSession
from apps.sessions.services import build_entry_service
from apps.sessions.tests.conftest import authenticate
from apps.sessions.tests.test_reads_and_availability import make_session

CHECKOUT_TIME = datetime(2026, 1, 2, 1, 0, 1, tzinfo=UTC)


def entered_session(*, operator, vehicle, entry_gate):
    session = build_entry_service().enter(
        vehicle_id=vehicle.pk,
        entry_gate_id=entry_gate.pk,
        actor=operator,
    )
    entered_at = CHECKOUT_TIME - timedelta(hours=25, seconds=1)
    ParkingSession.objects.filter(pk=session.pk).update(entered_at=entered_at)
    session.refresh_from_db()
    return session


@pytest.mark.django_db
def test_checkout_freezes_amount_and_transitions_without_releasing_spot(
    api_client, operator, vehicle, entry_gate, compact_spot, pricing_policy
):
    session = entered_session(operator=operator, vehicle=vehicle, entry_gate=entry_gate)
    with patch("apps.sessions.services.checkout.timezone.now", return_value=CHECKOUT_TIME):
        response = authenticate(api_client, operator).post(
            f"/api/v1/parking-sessions/{session.pk}/checkout/",
            {},
            format="json",
        )

    assert response.status_code == 200
    assert response.data["amount"] == "360.00"
    assert response.data["currency"] == "INR"
    assert response.data["calculation_breakdown"]["full_24_hour_blocks"]["count"] == 1
    assert response.data["calculation_breakdown"]["remainder"]["billable_hours"] == 2
    session.refresh_from_db()
    assert session.status == SessionStatus.PAYMENT_PENDING
    assert session.closed_at is None
    assert session.spot_id == compact_spot.pk

    availability = api_client.get(f"/api/v1/parking-lots/{entry_gate.parking_lot_id}/availability/")
    compact = next(
        item for item in availability.data["counts"] if item["spot_type"] == SpotType.COMPACT
    )
    assert compact["occupied"] == 1
    assert compact["available"] == 0


@pytest.mark.django_db
def test_repeated_checkout_returns_original_quote_without_recalculation(
    api_client, operator, vehicle, entry_gate, compact_spot, pricing_policy
):
    session = entered_session(operator=operator, vehicle=vehicle, entry_gate=entry_gate)
    client = authenticate(api_client, operator)
    with patch("apps.sessions.services.checkout.timezone.now", return_value=CHECKOUT_TIME):
        first = client.post(f"/api/v1/parking-sessions/{session.pk}/checkout/", {}, format="json")
    with patch(
        "apps.sessions.services.checkout.timezone.now",
        return_value=CHECKOUT_TIME + timedelta(days=10),
    ):
        second = client.post(f"/api/v1/parking-sessions/{session.pk}/checkout/", {}, format="json")

    assert first.status_code == second.status_code == 200
    assert first.data == second.data
    assert CheckoutQuote.objects.filter(parking_session=session).count() == 1


@pytest.mark.django_db
def test_checkout_rejects_protected_input_and_customer_permission(
    api_client, customer, operator, vehicle, entry_gate, compact_spot, pricing_policy
):
    session = entered_session(operator=operator, vehicle=vehicle, entry_gate=entry_gate)
    customer_response = authenticate(api_client, customer).post(
        f"/api/v1/parking-sessions/{session.pk}/checkout/", {}, format="json"
    )
    assert customer_response.status_code == 403

    protected = authenticate(api_client, operator).post(
        f"/api/v1/parking-sessions/{session.pk}/checkout/",
        {
            "amount": "1.00",
            "currency": "USD",
            "calculated_until": CHECKOUT_TIME.isoformat(),
            "pricing_policy": 99,
            "status": "CLOSED",
        },
        format="json",
    )
    assert protected.status_code == 400
    assert set(protected.data["error"]["fields"]) == {
        "amount",
        "calculated_until",
        "currency",
        "pricing_policy",
        "status",
    }
    assert not CheckoutQuote.objects.exists()


@pytest.mark.django_db
def test_zero_charge_checkout_still_becomes_payment_pending(
    api_client, operator, vehicle, entry_gate, compact_spot, pricing_policy
):
    session = build_entry_service().enter(
        vehicle_id=vehicle.pk,
        entry_gate_id=entry_gate.pk,
        actor=operator,
    )
    with patch(
        "apps.sessions.services.checkout.timezone.now",
        return_value=session.entered_at + timedelta(minutes=15),
    ):
        response = authenticate(api_client, operator).post(
            f"/api/v1/parking-sessions/{session.pk}/checkout/", {}, format="json"
        )
    assert response.status_code == 200
    assert response.data["amount"] == "0.00"
    session.refresh_from_db()
    assert session.status == SessionStatus.PAYMENT_PENDING


@pytest.mark.django_db
def test_legacy_session_without_snapshot_cannot_checkout(
    api_client, operator, vehicle, entry_gate, compact_spot
):
    legacy = make_session(
        vehicle=vehicle,
        spot=compact_spot,
        gate=entry_gate,
        actor=operator,
    )
    response = authenticate(api_client, operator).post(
        f"/api/v1/parking-sessions/{legacy.pk}/checkout/", {}, format="json"
    )
    assert response.status_code == 409
    assert response.data["error"]["code"] == "SESSION_PRICING_NOT_CONFIGURED"
    legacy.refresh_from_db()
    assert legacy.status == SessionStatus.ACTIVE
    assert not CheckoutQuote.objects.exists()


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("status", "with_quote", "expected_code"),
    [
        (SessionStatus.ACTIVE, True, "FINANCIAL_INTEGRITY_ERROR"),
        (SessionStatus.PAYMENT_PENDING, False, "FINANCIAL_INTEGRITY_ERROR"),
        (SessionStatus.PAID, True, "INVALID_SESSION_STATE"),
        (SessionStatus.CLOSED, True, "INVALID_SESSION_STATE"),
    ],
)
def test_checkout_rejects_inconsistent_or_unsupported_states(
    api_client,
    operator,
    vehicle,
    entry_gate,
    compact_spot,
    pricing_policy,
    status,
    with_quote,
    expected_code,
):
    session = entered_session(operator=operator, vehicle=vehicle, entry_gate=entry_gate)
    closed_at = CHECKOUT_TIME if status == SessionStatus.CLOSED else None
    ParkingSession.objects.filter(pk=session.pk).update(status=status, closed_at=closed_at)
    if with_quote:
        CheckoutQuote.objects.create(
            parking_session=session,
            calculated_until=CHECKOUT_TIME,
            amount=Decimal("30.00"),
            currency="INR",
            calculation_breakdown={},
            created_by=operator,
        )
    response = authenticate(api_client, operator).post(
        f"/api/v1/parking-sessions/{session.pk}/checkout/", {}, format="json"
    )
    assert response.status_code == 409
    assert response.data["error"]["code"] == expected_code


@pytest.mark.django_db
def test_customer_quote_is_owner_scoped(
    api_client,
    customer,
    other_customer,
    operator,
    vehicle,
    entry_gate,
    compact_spot,
    pricing_policy,
):
    session = entered_session(operator=operator, vehicle=vehicle, entry_gate=entry_gate)
    with patch("apps.sessions.services.checkout.timezone.now", return_value=CHECKOUT_TIME):
        authenticate(api_client, operator).post(
            f"/api/v1/parking-sessions/{session.pk}/checkout/", {}, format="json"
        )

    own = authenticate(api_client, customer).get(f"/api/v1/parking-sessions/{session.pk}/quote/")
    hidden = authenticate(api_client, other_customer).get(
        f"/api/v1/parking-sessions/{session.pk}/quote/"
    )
    assert own.status_code == 200
    assert own.data["amount"] == "360.00"
    assert "created_by" not in own.data
    assert hidden.status_code == 404


@pytest.mark.django_db
def test_accessible_session_without_quote_returns_stable_404(
    api_client, customer, operator, vehicle, entry_gate, compact_spot, pricing_policy
):
    session = entered_session(operator=operator, vehicle=vehicle, entry_gate=entry_gate)
    response = authenticate(api_client, customer).get(
        f"/api/v1/parking-sessions/{session.pk}/quote/"
    )
    assert response.status_code == 404
    assert response.data["error"]["code"] == "QUOTE_NOT_FOUND"


@pytest.mark.django_db
def test_backfill_command_is_explicit_idempotent_and_never_overwrites(
    operator, vehicle, entry_gate, compact_spot, pricing_policy
):
    legacy = make_session(
        vehicle=vehicle,
        spot=compact_spot,
        gate=entry_gate,
        actor=operator,
    )
    call_command(
        "backfill_pricing_snapshots",
        policy_id=pricing_policy.pk,
        session_ids=[legacy.pk],
    )
    snapshot = PricingSnapshot.objects.get(parking_session=legacy)
    original_rate = snapshot.hourly_rate
    call_command(
        "backfill_pricing_snapshots",
        policy_id=pricing_policy.pk,
        session_ids=[legacy.pk],
    )
    snapshot.refresh_from_db()
    assert snapshot.hourly_rate == original_rate
    assert PricingSnapshot.objects.filter(parking_session=legacy).count() == 1


@pytest.mark.django_db(transaction=True)
def test_checkout_quote_database_constraints(
    operator, vehicle, entry_gate, compact_spot, pricing_policy
):
    session = entered_session(operator=operator, vehicle=vehicle, entry_gate=entry_gate)
    quote = CheckoutQuote.objects.create(
        parking_session=session,
        calculated_until=CHECKOUT_TIME,
        amount=Decimal("1.00"),
        currency="INR",
        calculation_breakdown={},
        created_by=operator,
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        CheckoutQuote.objects.create(
            parking_session=session,
            calculated_until=CHECKOUT_TIME,
            amount=Decimal("2.00"),
            currency="INR",
            calculation_breakdown={},
            created_by=operator,
        )
    other_vehicle = Vehicle.objects.create(
        owner=vehicle.owner,
        registration_number="NEGQUOTE",
        vehicle_type=VehicleType.CAR,
    )
    other_spot = ParkingSpot.objects.create(
        floor=compact_spot.floor,
        number="NEG-1",
        spot_type=SpotType.COMPACT,
    )
    other_session = make_session(
        vehicle=other_vehicle,
        spot=other_spot,
        gate=entry_gate,
        actor=operator,
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        CheckoutQuote.objects.create(
            parking_session=other_session,
            calculated_until=CHECKOUT_TIME,
            amount=Decimal("-0.01"),
            currency="INR",
            calculation_breakdown={},
            created_by=operator,
        )
    assert quote.pk
