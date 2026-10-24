import json
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from django.utils import timezone

from apps.payments.adapters.base import ProviderPaymentResult, ProviderRefundResult
from apps.payments.adapters.razorpay import RazorpayPaymentProvider
from apps.payments.composition import build_payment_result_service, build_refund_result_service
from apps.payments.enums import (
    PaymentProviderName,
    PaymentStatus,
    RefundStatus,
    SettlementMethod,
    WebhookEventStatus,
)
from apps.payments.exceptions import PaymentConflict
from apps.payments.models import PaymentAttempt, Settlement, WebhookEvent
from apps.payments.services.confirmation import PaymentConfirmationService
from apps.payments.services.initiation import PaymentInitiationService
from apps.payments.services.refunds import RefundInitiationService
from apps.payments.services.webhooks import RazorpayWebhookService
from apps.sessions.enums import SessionStatus


class FakeOrderResource:
    def __init__(self):
        self.created = []

    def create(self, data):
        self.created.append(data)
        return {
            "id": "order_test",
            "amount": data["amount"],
            "currency": data["currency"],
            "receipt": data["receipt"],
            "status": "created",
        }


class FakePaymentResource:
    def __init__(self):
        self.refunds = []

    def fetch(self, payment_id):
        return {
            "id": payment_id,
            "order_id": "order_test",
            "amount": 9000,
            "currency": "INR",
            "status": "captured",
        }

    def refund(self, payment_id, data):
        self.refunds.append((payment_id, data))
        return {
            "id": "rfnd_test",
            "payment_id": payment_id,
            "amount": data["amount"],
            "currency": "INR",
            "status": "processed",
        }


class FakeUtility:
    def verify_payment_signature(self, values):
        if values["razorpay_signature"] != "valid":
            raise ValueError("bad signature")


def test_razorpay_adapter_creates_order_in_subunits_and_maps_captured_payment():
    client = SimpleNamespace(
        order=FakeOrderResource(),
        payment=FakePaymentResource(),
        utility=FakeUtility(),
    )
    provider = RazorpayPaymentProvider(key_id="rzp_test", key_secret="secret", client=client)
    merchant_reference = uuid4()

    initiated = provider.initiate_payment(
        merchant_reference=merchant_reference,
        amount=Decimal("90.00"),
        currency="INR",
    )
    provider.verify_checkout_signature(
        provider_order_reference="order_test",
        provider_reference="pay_test",
        signature="valid",
    )
    captured = provider.retrieve_payment(
        merchant_reference=merchant_reference,
        provider_order_reference="order_test",
        provider_reference="pay_test",
    )

    assert client.order.created[0]["amount"] == 9000
    assert client.order.created[0]["receipt"] == f"pay_{merchant_reference.hex}"
    assert initiated.status == PaymentStatus.PENDING
    assert initiated.provider_order_reference == "order_test"
    assert captured.status == PaymentStatus.SUCCEEDED
    assert captured.amount == Decimal("90.00")


class FakeRazorpayProvider:
    name = PaymentProviderName.RAZORPAY

    def __init__(self):
        self.initiation_count = 0
        self.signature_verified = False

    def initiate_payment(self, *, merchant_reference, amount, currency):
        self.initiation_count += 1
        return ProviderPaymentResult(
            merchant_reference=merchant_reference,
            provider_reference=None,
            provider_order_reference=f"order_{merchant_reference.hex}",
            status=PaymentStatus.PENDING,
            amount=amount,
            currency=currency,
        )

    def verify_checkout_signature(self, **kwargs):
        self.signature_verified = True

    def retrieve_payment(
        self,
        *,
        merchant_reference,
        provider_order_reference=None,
        provider_reference=None,
    ):
        return ProviderPaymentResult(
            merchant_reference=merchant_reference,
            provider_reference=provider_reference,
            provider_order_reference=provider_order_reference,
            status=PaymentStatus.SUCCEEDED,
            amount=Decimal("90.00"),
            currency="INR",
        )

    def initiate_refund(
        self,
        *,
        merchant_reference,
        payment_reference,
        amount,
        currency,
    ):
        return ProviderRefundResult(
            merchant_reference=merchant_reference,
            provider_reference=f"rfnd_{merchant_reference.hex}",
            payment_reference=payment_reference,
            status=RefundStatus.SUCCEEDED,
            amount=amount,
            currency=currency,
        )

    def retrieve_refund(self, **kwargs):
        raise AssertionError("not used")


@pytest.mark.django_db
def test_razorpay_order_is_reused_then_confirmation_settles(
    operator,
    payment_context,
):
    provider = FakeRazorpayProvider()
    results = build_payment_result_service()
    initiation = PaymentInitiationService(provider=provider, result_service=results)

    attempt = initiation.initiate(session_id=payment_context["session"].pk, actor=operator)
    repeated = initiation.initiate(session_id=payment_context["session"].pk, actor=operator)

    assert repeated.pk == attempt.pk
    assert provider.initiation_count == 1
    assert attempt.provider_order_reference

    confirmed = PaymentConfirmationService(provider=provider, result_service=results).confirm(
        attempt_id=attempt.pk,
        provider_order_reference=attempt.provider_order_reference,
        provider_reference="pay_captured",
        signature="valid",
    )
    payment_context["session"].refresh_from_db()
    assert provider.signature_verified is True
    assert confirmed.status == PaymentStatus.SUCCEEDED
    assert payment_context["session"].status == SessionStatus.PAID
    assert Settlement.objects.filter(quote=payment_context["quote"]).count() == 1


@pytest.mark.django_db
def test_refund_reserves_amount_and_prevents_over_refund(operator, payment_context):
    attempt = PaymentAttempt.objects.create(
        quote=payment_context["quote"],
        provider=PaymentProviderName.RAZORPAY,
        provider_order_reference="order_refund",
        provider_reference="pay_refund",
        amount=Decimal("90.00"),
        currency="INR",
        status=PaymentStatus.SUCCEEDED,
        initiated_by=operator,
        completed_at=timezone.now(),
    )
    settlement = Settlement.objects.create(
        quote=payment_context["quote"],
        payment_attempt=attempt,
        method=SettlementMethod.PROVIDER,
        amount=Decimal("90.00"),
        currency="INR",
        settled_at=timezone.now(),
    )
    service = RefundInitiationService(
        provider=FakeRazorpayProvider(),
        result_service=build_refund_result_service(),
    )

    refund = service.initiate(
        payment_attempt_id=attempt.pk,
        amount=Decimal("60.00"),
        reason="Customer overpayment",
        actor=operator,
    )

    assert refund.status == RefundStatus.SUCCEEDED
    assert refund.settlement == settlement
    with pytest.raises(PaymentConflict) as exc:
        service.initiate(
            payment_attempt_id=attempt.pk,
            amount=Decimal("40.00"),
            reason="Would exceed payment",
            actor=operator,
        )
    assert exc.value.detail["code"] == "REFUND_AMOUNT_EXCEEDS_AVAILABLE"


@pytest.mark.django_db
def test_webhook_delivery_is_deduplicated(operator, payment_context):
    attempt = PaymentAttempt.objects.create(
        quote=payment_context["quote"],
        provider=PaymentProviderName.RAZORPAY,
        provider_order_reference="order_test",
        amount=Decimal("90.00"),
        currency="INR",
        initiated_by=operator,
    )
    provider = FakeRazorpayProvider()
    service = RazorpayWebhookService(
        provider=provider,
        payment_results=build_payment_result_service(),
        refund_results=build_refund_result_service(),
    )
    payload = {
        "event": "payment.captured",
        "payload": {"payment": {"entity": {"id": "pay_captured", "order_id": "order_test"}}},
    }
    body = json.dumps(payload).encode()

    first = service.process(event_id="event-1", body=body, payload=payload)
    second = service.process(event_id="event-1", body=body, payload=payload)

    attempt.refresh_from_db()
    assert first.status == second.status == WebhookEventStatus.PROCESSED
    assert attempt.status == PaymentStatus.SUCCEEDED
    assert WebhookEvent.objects.count() == 1
    assert Settlement.objects.count() == 1
