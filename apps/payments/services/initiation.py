from dataclasses import dataclass

from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction

from apps.payments.adapters.base import PaymentProvider
from apps.payments.enums import PaymentProviderName, PaymentStatus, SettlementMethod
from apps.payments.exceptions import (
    PaymentConflict,
    ProviderOutcomeUnknown,
    ProviderProtocolError,
)
from apps.payments.models import PaymentAttempt
from apps.payments.services.settlement import PaymentResultService, validate_settlement
from apps.pricing.models import CheckoutQuote
from apps.sessions.enums import SessionStatus
from apps.sessions.models import ParkingSession


@dataclass(frozen=True)
class PaymentInitiationService:
    provider: PaymentProvider
    result_service: PaymentResultService

    def initiate(self, *, session_id: int, actor) -> PaymentAttempt:
        attempt, should_call_provider = self._prepare(session_id=session_id, actor=actor)
        if not should_call_provider:
            return attempt

        try:
            result = self.provider.initiate_payment(
                merchant_reference=attempt.pk,
                amount=attempt.amount,
                currency=attempt.currency,
            )
        except ProviderOutcomeUnknown:
            return attempt
        except ProviderProtocolError as exc:
            raise PaymentConflict(
                code="PAYMENT_PROVIDER_ERROR",
                detail="The payment provider could not safely process the request.",
            ) from exc
        return self.result_service.apply(attempt_id=attempt.pk, result=result)

    def _prepare(self, *, session_id: int, actor) -> tuple[PaymentAttempt, bool]:
        provider_name = getattr(self.provider, "name", PaymentProviderName.SIMULATED)
        with transaction.atomic():
            try:
                parking_session = ParkingSession.objects.select_for_update().get(pk=session_id)
                quote = CheckoutQuote.objects.select_for_update().get(
                    parking_session=parking_session
                )
            except (ParkingSession.DoesNotExist, CheckoutQuote.DoesNotExist) as exc:
                raise PaymentConflict(
                    code="CHECKOUT_QUOTE_REQUIRED",
                    detail="A frozen checkout quote is required before payment.",
                ) from exc

            try:
                settlement = quote.settlement
            except ObjectDoesNotExist:
                settlement = None
            if settlement is not None:
                validate_settlement(settlement=settlement, quote=quote)
                if settlement.method != SettlementMethod.PROVIDER:
                    raise PaymentConflict(
                        code="ZERO_CHARGE_REQUIRES_SETTLEMENT",
                        detail="Zero-amount quotes must use the zero-charge endpoint.",
                    )
                return settlement.payment_attempt, False

            if parking_session.status != SessionStatus.PAYMENT_PENDING:
                raise PaymentConflict(
                    code="INVALID_SESSION_STATE",
                    detail="Payment requires a payment-pending parking session.",
                )
            if quote.amount <= 0:
                raise PaymentConflict(
                    code="POSITIVE_QUOTE_REQUIRED",
                    detail="Provider payment requires a positive checkout quote.",
                )

            pending = PaymentAttempt.objects.filter(
                quote=quote,
                status=PaymentStatus.PENDING,
            ).first()
            if pending is not None:
                if pending.provider != provider_name:
                    raise PaymentConflict(
                        code="PAYMENT_PROVIDER_CHANGED",
                        detail=(
                            "Finish or reconcile the existing payment with its original provider."
                        ),
                    )
                # A Razorpay order is created once. Checkout and reconciliation reuse it.
                return pending, pending.provider == PaymentProviderName.SIMULATED

            attempt = PaymentAttempt.objects.create(
                quote=quote,
                provider=provider_name,
                amount=quote.amount,
                currency=quote.currency,
                initiated_by=actor,
            )
            return attempt, True
