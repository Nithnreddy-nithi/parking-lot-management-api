from dataclasses import replace
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import IntegrityError, connection, transaction
from django.test import override_settings
from django.utils import timezone

from apps.payments.adapters.base import ProviderPaymentResult
from apps.payments.composition import build_payment_result_service
from apps.payments.enums import PaymentStatus, SettlementMethod, SimulationScenario
from apps.payments.exceptions import PaymentConflict
from apps.payments.models import PaymentAttempt, Settlement, SimulatedPaymentRecord
from apps.payments.services.initiation import PaymentInitiationService
from apps.payments.services.settlement import ZeroChargeSettlementService
from apps.payments.tests.conftest import authenticate
from apps.pricing.models import CheckoutQuote
from apps.sessions.enums import SessionStatus
from apps.sessions.models import ParkingSession


def payment_url(session) -> str:
    return "/api/v1/payments/"


def initiate(client, session):
    return client.post(payment_url(session), {"parking_session_id": session.pk}, format="json")


@pytest.mark.django_db
def test_successful_payment_creates_settlement_and_marks_session_paid(
    api_client, customer, payment_context
):
    response = initiate(authenticate(api_client, customer), payment_context["session"])
    repeated = initiate(api_client, payment_context["session"])

    assert response.status_code == repeated.status_code == 200
    assert response.data["id"] == repeated.data["id"]
    assert response.data["status"] == PaymentStatus.SUCCEEDED
    attempt = PaymentAttempt.objects.get(pk=response.data["id"])
    settlement = Settlement.objects.get(quote=payment_context["quote"])
    assert settlement.payment_attempt == attempt
    assert settlement.method == SettlementMethod.PROVIDER
    payment_context["session"].refresh_from_db()
    assert payment_context["session"].status == SessionStatus.PAID
    assert SimulatedPaymentRecord.objects.get(merchant_reference=attempt.pk).initiation_count == 1


@pytest.mark.django_db(transaction=True)
def test_provider_call_occurs_outside_database_transaction(operator, payment_context):
    class InspectingProvider:
        def initiate_payment(self, *, merchant_reference, amount, currency):
            assert connection.in_atomic_block is False
            return ProviderPaymentResult(
                merchant_reference=merchant_reference,
                provider_reference="outside-transaction",
                status=PaymentStatus.PENDING,
                amount=amount,
                currency=currency,
            )

    service = PaymentInitiationService(
        provider=InspectingProvider(),
        result_service=build_payment_result_service(),
    )
    attempt = service.initiate(session_id=payment_context["session"].pk, actor=operator)
    assert attempt.status == PaymentStatus.PENDING


@pytest.mark.django_db
@override_settings(SIMULATED_PAYMENT_SCENARIO=SimulationScenario.FAILURE)
def test_failure_preserves_quote_occupancy_and_allows_new_attempt(
    api_client, customer, payment_context
):
    client = authenticate(api_client, customer)
    first = initiate(client, payment_context["session"])
    second = initiate(client, payment_context["session"])

    assert first.status_code == second.status_code == 200
    assert first.data["status"] == second.data["status"] == PaymentStatus.FAILED
    assert first.data["id"] != second.data["id"]
    assert PaymentAttempt.objects.filter(quote=payment_context["quote"]).count() == 2
    assert not Settlement.objects.exists()
    payment_context["session"].refresh_from_db()
    assert payment_context["session"].status == SessionStatus.PAYMENT_PENDING


@pytest.mark.django_db
@override_settings(SIMULATED_PAYMENT_SCENARIO=SimulationScenario.PENDING)
def test_pending_initiation_reuses_stable_attempt(api_client, operator, payment_context):
    client = authenticate(api_client, operator)
    first = initiate(client, payment_context["session"])
    second = initiate(client, payment_context["session"])

    assert first.status_code == second.status_code == 202
    assert first.data["id"] == second.data["id"]
    assert PaymentAttempt.objects.filter(quote=payment_context["quote"]).count() == 1


@pytest.mark.django_db
def test_repeated_success_result_is_noop_and_contradiction_is_rejected(
    api_client, operator, payment_context
):
    response = initiate(authenticate(api_client, operator), payment_context["session"])
    attempt = PaymentAttempt.objects.get(pk=response.data["id"])
    result = ProviderPaymentResult(
        merchant_reference=attempt.pk,
        provider_reference=attempt.provider_reference,
        status=PaymentStatus.SUCCEEDED,
        amount=attempt.amount,
        currency=attempt.currency,
    )
    service = build_payment_result_service()

    assert service.apply(attempt_id=attempt.pk, result=result).pk == attempt.pk
    assert Settlement.objects.filter(quote=payment_context["quote"]).count() == 1
    with pytest.raises(PaymentConflict) as exc:
        service.apply(
            attempt_id=attempt.pk,
            result=replace(result, status=PaymentStatus.FAILED, failure_code="LATE_FAILURE"),
        )
    assert exc.value.detail["code"] == "CONTRADICTORY_PROVIDER_RESULT"


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("change", "code"),
    [
        ({"merchant_reference": uuid4()}, "PROVIDER_REFERENCE_MISMATCH"),
        ({"amount": Decimal("91.00")}, "PROVIDER_FINANCIAL_MISMATCH"),
        ({"currency": "USD"}, "PROVIDER_FINANCIAL_MISMATCH"),
    ],
)
def test_provider_result_identity_and_financial_mismatch_rejected(
    operator, payment_context, change, code
):
    attempt = PaymentAttempt.objects.create(
        quote=payment_context["quote"],
        amount=payment_context["quote"].amount,
        currency=payment_context["quote"].currency,
        initiated_by=operator,
    )
    result = ProviderPaymentResult(
        merchant_reference=attempt.pk,
        provider_reference="provider-test",
        status=PaymentStatus.SUCCEEDED,
        amount=attempt.amount,
        currency=attempt.currency,
    )
    with pytest.raises(PaymentConflict) as exc:
        build_payment_result_service().apply(
            attempt_id=attempt.pk,
            result=replace(result, **change),
        )
    assert exc.value.detail["code"] == code
    attempt.refresh_from_db()
    assert attempt.status == PaymentStatus.PENDING


@pytest.mark.django_db
@override_settings(SIMULATED_PAYMENT_SCENARIO=SimulationScenario.TIMEOUT_AFTER_SUCCESS)
def test_timeout_keeps_pending_and_reconciliation_recovers_success(
    api_client, customer, payment_context
):
    response = initiate(authenticate(api_client, customer), payment_context["session"])
    assert response.status_code == 202
    attempt = PaymentAttempt.objects.get(pk=response.data["id"])
    assert attempt.status == PaymentStatus.PENDING
    assert SimulatedPaymentRecord.objects.get(merchant_reference=attempt.pk).status == (
        PaymentStatus.SUCCEEDED
    )

    call_command("reconcile_payment", str(attempt.pk))
    attempt.refresh_from_db()
    payment_context["session"].refresh_from_db()
    assert attempt.status == PaymentStatus.SUCCEEDED
    assert payment_context["session"].status == SessionStatus.PAID
    assert Settlement.objects.filter(quote=payment_context["quote"]).count() == 1


@pytest.mark.django_db
def test_zero_charge_is_idempotent_owned_and_never_calls_provider(
    api_client, customer, other_customer, payment_context
):
    CheckoutQuote.objects.filter(pk=payment_context["quote"].pk).update(amount=0)
    client = authenticate(api_client, customer)
    url = f"/api/v1/parking-sessions/{payment_context['session'].pk}/settle-zero/"
    hidden = authenticate(api_client, other_customer).post(
        url,
        {},
        format="json",
    )
    assert hidden.status_code == 404
    client = authenticate(api_client, customer)
    first = client.post(url, {}, format="json")
    second = client.post(url, {}, format="json")

    assert first.status_code == second.status_code == 200
    assert first.data == second.data
    assert first.data["method"] == SettlementMethod.ZERO_CHARGE
    assert not PaymentAttempt.objects.exists()
    assert not SimulatedPaymentRecord.objects.exists()


@pytest.mark.django_db
def test_payment_rejects_client_controlled_financial_and_status_fields(
    api_client, customer, payment_context
):
    response = authenticate(api_client, customer).post(
        "/api/v1/payments/",
        {
            "parking_session_id": payment_context["session"].pk,
            "amount": "1.00",
            "currency": "USD",
            "status": "SUCCEEDED",
            "success": True,
        },
        format="json",
    )
    assert response.status_code == 400
    assert set(response.data["error"]["fields"]) == {
        "amount",
        "currency",
        "status",
        "success",
    }
    assert not PaymentAttempt.objects.exists()


@pytest.mark.django_db
def test_positive_quote_rejected_by_zero_charge_endpoint(api_client, operator, payment_context):
    response = authenticate(api_client, operator).post(
        f"/api/v1/parking-sessions/{payment_context['session'].pk}/settle-zero/",
        {},
        format="json",
    )
    assert response.status_code == 409
    assert response.data["error"]["code"] == "ZERO_CHARGE_NOT_ALLOWED"
    assert not Settlement.objects.exists()


@pytest.mark.django_db
def test_customer_ownership_isolation_and_payment_reads(
    api_client, customer, other_customer, operator, payment_context
):
    hidden_create = initiate(authenticate(api_client, other_customer), payment_context["session"])
    assert hidden_create.status_code == 404

    created = initiate(authenticate(api_client, customer), payment_context["session"])
    attempt_id = created.data["id"]
    own_detail = api_client.get(f"/api/v1/payments/{attempt_id}/")
    own_list = api_client.get("/api/v1/payments/?status=SUCCEEDED")
    hidden_detail = authenticate(api_client, other_customer).get(f"/api/v1/payments/{attempt_id}/")
    staff_list = authenticate(api_client, operator).get(
        f"/api/v1/payments/?session={payment_context['session'].pk}"
    )

    assert own_detail.status_code == 200
    assert len(own_list.data["results"]) == 1
    assert hidden_detail.status_code == 404
    assert len(staff_list.data["results"]) == 1
    assert api_client.get("/api/v1/payments/?status=INVALID").status_code == 400


@pytest.mark.django_db(transaction=True)
def test_payment_and_settlement_database_constraints(operator, payment_context):
    with pytest.raises(IntegrityError), transaction.atomic():
        PaymentAttempt.objects.create(
            quote=payment_context["quote"],
            amount=0,
            currency="INR",
            initiated_by=operator,
        )

    pending = PaymentAttempt.objects.create(
        quote=payment_context["quote"],
        amount=payment_context["quote"].amount,
        currency="INR",
        initiated_by=operator,
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        PaymentAttempt.objects.create(
            quote=payment_context["quote"],
            amount=payment_context["quote"].amount,
            currency="INR",
            initiated_by=operator,
        )
    with pytest.raises(IntegrityError), transaction.atomic():
        PaymentAttempt.objects.filter(pk=pending.pk).update(status=PaymentStatus.FAILED)

    completed_at = timezone.now()
    PaymentAttempt.objects.filter(pk=pending.pk).update(
        status=PaymentStatus.FAILED,
        completed_at=completed_at,
    )
    succeeded = PaymentAttempt.objects.create(
        quote=payment_context["quote"],
        provider_reference="constraint-success",
        amount=payment_context["quote"].amount,
        currency="INR",
        status=PaymentStatus.SUCCEEDED,
        initiated_by=operator,
        completed_at=completed_at,
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        PaymentAttempt.objects.create(
            quote=payment_context["quote"],
            provider_reference="second-success",
            amount=payment_context["quote"].amount,
            currency="INR",
            status=PaymentStatus.SUCCEEDED,
            initiated_by=operator,
            completed_at=completed_at,
        )
    succeeded.amount = Decimal("1.00")
    with pytest.raises(ValidationError):
        succeeded.save()

    with pytest.raises(IntegrityError), transaction.atomic():
        Settlement.objects.create(
            quote=payment_context["quote"],
            method=SettlementMethod.ZERO_CHARGE,
            amount=Decimal("90.00"),
            currency="INR",
            settled_at=timezone.now(),
        )


@pytest.mark.django_db
def test_zero_charge_service_rolls_back_when_session_update_fails(operator, payment_context):
    CheckoutQuote.objects.filter(pk=payment_context["quote"].pk).update(amount=0)
    service = ZeroChargeSettlementService(clock=timezone.now)
    with (
        patch.object(ParkingSession, "save", side_effect=RuntimeError("write failed")),
        pytest.raises(RuntimeError),
    ):
        service.settle(session_id=payment_context["session"].pk)
    assert not Settlement.objects.exists()
