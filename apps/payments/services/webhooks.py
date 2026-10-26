import hashlib
from dataclasses import dataclass
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from apps.payments.adapters.base import PaymentProvider
from apps.payments.enums import PaymentProviderName, WebhookEventStatus
from apps.payments.exceptions import PaymentConflict, ProviderProtocolError
from apps.payments.models import PaymentAttempt, Refund, WebhookEvent
from apps.payments.services.refunds import RefundResultService
from apps.payments.services.settlement import PaymentResultService


@dataclass(frozen=True)
class RazorpayWebhookService:
    provider: PaymentProvider
    payment_results: PaymentResultService
    refund_results: RefundResultService

    def process(self, *, event_id: str, body: bytes, payload: dict) -> WebhookEvent:
        event_type = str(payload.get("event", ""))
        digest = hashlib.sha256(body).hexdigest()
        with transaction.atomic():
            event, created = WebhookEvent.objects.get_or_create(
                provider=PaymentProviderName.RAZORPAY,
                provider_event_id=event_id,
                defaults={"event_type": event_type, "payload_sha256": digest},
            )
            if not created:
                if event.payload_sha256 != digest:
                    raise ProviderProtocolError("A webhook event ID was reused with a new payload.")
                if event.status != WebhookEventStatus.RECEIVED:
                    return event

        try:
            if event_type == "payment.captured":
                self._process_payment(payload)
            elif event_type == "payment.failed":
                # A failed payment does not close its Razorpay Order; Checkout may retry it.
                self._validate_known_payment_order(payload)
            elif event_type in {"refund.created", "refund.processed", "refund.failed"}:
                self._process_refund(payload)
            else:
                return self._finish(event, WebhookEventStatus.IGNORED)
        except PaymentConflict:
            return self._finish(event, WebhookEventStatus.FAILED, "DOMAIN_CONFLICT")
        return self._finish(event, WebhookEventStatus.PROCESSED)

    def _process_payment(self, payload: dict) -> None:
        entity = payload.get("payload", {}).get("payment", {}).get("entity", {})
        order_reference = entity.get("order_id")
        payment_reference = entity.get("id")
        if not order_reference or not payment_reference:
            raise ProviderProtocolError("The payment webhook has no order or payment ID.")
        try:
            attempt = PaymentAttempt.objects.get(
                provider=PaymentProviderName.RAZORPAY,
                provider_order_reference=order_reference,
            )
        except PaymentAttempt.DoesNotExist as exc:
            raise ProviderProtocolError("The payment webhook order is unknown.") from exc
        result = self.provider.retrieve_payment(
            merchant_reference=attempt.pk,
            provider_order_reference=order_reference,
            provider_reference=payment_reference,
        )
        self.payment_results.apply(attempt_id=attempt.pk, result=result)

    @staticmethod
    def _validate_known_payment_order(payload: dict) -> None:
        entity = payload.get("payload", {}).get("payment", {}).get("entity", {})
        order_reference = entity.get("order_id")
        if (
            not order_reference
            or not PaymentAttempt.objects.filter(
                provider=PaymentProviderName.RAZORPAY,
                provider_order_reference=order_reference,
            ).exists()
        ):
            raise ProviderProtocolError("The failed-payment webhook order is unknown.")

    def _process_refund(self, payload: dict) -> None:
        entity = payload.get("payload", {}).get("refund", {}).get("entity", {})
        provider_reference = entity.get("id")
        merchant_reference = entity.get("notes", {}).get("refund_id")
        try:
            refund = (
                Refund.objects.get(pk=UUID(str(merchant_reference)))
                if merchant_reference
                else Refund.objects.get(provider_reference=provider_reference)
            )
        except (Refund.DoesNotExist, ValueError, TypeError) as exc:
            raise ProviderProtocolError("The refund webhook is unknown.") from exc
        result = self.provider.retrieve_refund(
            merchant_reference=refund.pk,
            provider_reference=provider_reference,
        )
        self.refund_results.apply(refund_id=refund.pk, result=result)

    @staticmethod
    def _finish(event: WebhookEvent, status: str, failure_code: str = "") -> WebhookEvent:
        event.status = status
        event.failure_code = failure_code
        event.processed_at = timezone.now()
        event.save(update_fields=["status", "failure_code", "processed_at"])
        return event
