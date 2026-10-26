from dataclasses import dataclass

from apps.payments.adapters.base import PaymentProvider
from apps.payments.exceptions import PaymentConflict, ProviderOutcomeUnknown, ProviderProtocolError
from apps.payments.models import PaymentAttempt
from apps.payments.services.settlement import PaymentResultService


@dataclass(frozen=True)
class PaymentConfirmationService:
    provider: PaymentProvider
    result_service: PaymentResultService

    def confirm(
        self,
        *,
        attempt_id,
        provider_order_reference: str,
        provider_reference: str,
        signature: str,
    ) -> PaymentAttempt:
        try:
            attempt = PaymentAttempt.objects.get(pk=attempt_id)
        except PaymentAttempt.DoesNotExist as exc:
            raise PaymentConflict(
                code="PAYMENT_ATTEMPT_NOT_FOUND",
                detail="The payment attempt was not found.",
            ) from exc
        if attempt.provider != self.provider.name:
            raise PaymentConflict(
                code="PAYMENT_PROVIDER_MISMATCH",
                detail="The payment attempt belongs to a different provider.",
            )
        if attempt.provider_order_reference != provider_order_reference:
            raise PaymentConflict(
                code="PROVIDER_ORDER_MISMATCH",
                detail="The checkout order does not match this payment attempt.",
            )
        try:
            self.provider.verify_checkout_signature(
                provider_order_reference=provider_order_reference,
                provider_reference=provider_reference,
                signature=signature,
            )
            result = self.provider.retrieve_payment(
                merchant_reference=attempt.pk,
                provider_order_reference=provider_order_reference,
                provider_reference=provider_reference,
            )
        except ProviderOutcomeUnknown as exc:
            raise PaymentConflict(
                code="PAYMENT_CONFIRMATION_PENDING",
                detail="Payment confirmation is temporarily unavailable; reconciliation is safe.",
            ) from exc
        except ProviderProtocolError as exc:
            raise PaymentConflict(
                code="INVALID_PAYMENT_CONFIRMATION",
                detail="The payment confirmation could not be verified.",
            ) from exc
        return self.result_service.apply(attempt_id=attempt.pk, result=result)
