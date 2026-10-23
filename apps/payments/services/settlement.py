from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction

from apps.payments.adapters.base import ProviderPaymentResult
from apps.payments.enums import PaymentStatus, SettlementMethod
from apps.payments.exceptions import PaymentConflict
from apps.payments.models import PaymentAttempt, Settlement
from apps.pricing.models import CheckoutQuote
from apps.sessions.enums import SessionStatus
from apps.sessions.models import ParkingSession


def validate_settlement(*, settlement: Settlement, quote: CheckoutQuote) -> None:
    """Validate cross-table invariants that SQL CHECK constraints cannot express."""
    if settlement.quote_id != quote.pk:
        raise PaymentConflict(
            code="SETTLEMENT_INTEGRITY_ERROR",
            detail="The settlement does not belong to the checkout quote.",
        )
    if settlement.amount != quote.amount or settlement.currency != quote.currency:
        raise PaymentConflict(
            code="SETTLEMENT_INTEGRITY_ERROR",
            detail="The settlement financial values do not match the checkout quote.",
        )
    if settlement.method == SettlementMethod.ZERO_CHARGE:
        if settlement.payment_attempt_id is not None or quote.amount != 0:
            raise PaymentConflict(
                code="SETTLEMENT_INTEGRITY_ERROR",
                detail="The zero-charge settlement is inconsistent.",
            )
        return
    if settlement.method != SettlementMethod.PROVIDER or settlement.payment_attempt_id is None:
        raise PaymentConflict(
            code="SETTLEMENT_INTEGRITY_ERROR",
            detail="The provider settlement is inconsistent.",
        )
    attempt = settlement.payment_attempt
    if (
        attempt.quote_id != quote.pk
        or attempt.status != PaymentStatus.SUCCEEDED
        or attempt.amount != quote.amount
        or attempt.currency != quote.currency
    ):
        raise PaymentConflict(
            code="SETTLEMENT_INTEGRITY_ERROR",
            detail="The successful payment does not match the settlement and quote.",
        )


@dataclass(frozen=True)
class PaymentResultService:
    clock: Callable[[], datetime]

    def apply(self, *, attempt_id, result: ProviderPaymentResult) -> PaymentAttempt:
        try:
            identifiers = PaymentAttempt.objects.values(
                "quote_id",
                "quote__parking_session_id",
            ).get(pk=attempt_id)
        except PaymentAttempt.DoesNotExist as exc:
            raise PaymentConflict(
                code="PAYMENT_ATTEMPT_NOT_FOUND",
                detail="The payment attempt was not found.",
            ) from exc

        with transaction.atomic():
            parking_session = ParkingSession.objects.select_for_update().get(
                pk=identifiers["quote__parking_session_id"]
            )
            quote = CheckoutQuote.objects.select_for_update().get(pk=identifiers["quote_id"])
            attempt = PaymentAttempt.objects.select_for_update().get(pk=attempt_id)

            self._validate_result(attempt=attempt, result=result)
            if attempt.status != PaymentStatus.PENDING:
                self._validate_terminal_replay(attempt=attempt, result=result)
                return attempt

            if result.status == PaymentStatus.PENDING:
                if attempt.provider_reference not in {None, result.provider_reference}:
                    raise PaymentConflict(
                        code="PROVIDER_RESULT_CONFLICT",
                        detail="The provider reference contradicts the existing attempt.",
                    )
                attempt.provider_reference = result.provider_reference
                attempt.save(update_fields=["provider_reference", "updated_at"])
                return attempt

            completed_at = self.clock()
            attempt.provider_reference = result.provider_reference
            attempt.status = result.status
            attempt.completed_at = completed_at
            attempt.failure_code = (
                result.failure_code or "PROVIDER_DECLINED"
                if result.status == PaymentStatus.FAILED
                else ""
            )
            attempt.save(
                update_fields=[
                    "provider_reference",
                    "status",
                    "completed_at",
                    "failure_code",
                    "updated_at",
                ]
            )

            if result.status == PaymentStatus.FAILED:
                return attempt
            if parking_session.status != SessionStatus.PAYMENT_PENDING:
                raise PaymentConflict(
                    code="INVALID_SESSION_STATE",
                    detail="A successful payment requires a payment-pending session.",
                )

            settlement = Settlement.objects.create(
                quote=quote,
                payment_attempt=attempt,
                method=SettlementMethod.PROVIDER,
                amount=quote.amount,
                currency=quote.currency,
                settled_at=completed_at,
            )
            validate_settlement(settlement=settlement, quote=quote)
            parking_session.status = SessionStatus.PAID
            parking_session.save(update_fields=["status", "updated_at"])
            return attempt

    @staticmethod
    def _validate_result(*, attempt: PaymentAttempt, result: ProviderPaymentResult) -> None:
        if result.status not in PaymentStatus.values:
            raise PaymentConflict(
                code="INVALID_PROVIDER_RESULT",
                detail="The provider returned an unsupported payment status.",
            )
        if result.merchant_reference != attempt.pk:
            raise PaymentConflict(
                code="PROVIDER_REFERENCE_MISMATCH",
                detail="The provider returned a different merchant reference.",
            )
        if result.amount != attempt.amount or result.currency != attempt.currency:
            raise PaymentConflict(
                code="PROVIDER_FINANCIAL_MISMATCH",
                detail="The provider result does not match the attempted amount and currency.",
            )
        if not result.provider_reference:
            raise PaymentConflict(
                code="INVALID_PROVIDER_RESULT",
                detail="The provider result has no provider reference.",
            )

    @staticmethod
    def _validate_terminal_replay(
        *, attempt: PaymentAttempt, result: ProviderPaymentResult
    ) -> None:
        identical = (
            attempt.status == result.status
            and attempt.provider_reference == result.provider_reference
            and (
                attempt.status != PaymentStatus.FAILED
                or attempt.failure_code == (result.failure_code or "PROVIDER_DECLINED")
            )
        )
        if not identical:
            raise PaymentConflict(
                code="CONTRADICTORY_PROVIDER_RESULT",
                detail="The provider result contradicts the terminal payment attempt.",
            )


@dataclass(frozen=True)
class ZeroChargeSettlementService:
    clock: Callable[[], datetime]

    def settle(self, *, session_id: int) -> Settlement:
        with transaction.atomic():
            try:
                parking_session = ParkingSession.objects.select_for_update().get(pk=session_id)
                quote = CheckoutQuote.objects.select_for_update().get(
                    parking_session=parking_session
                )
            except (ParkingSession.DoesNotExist, CheckoutQuote.DoesNotExist) as exc:
                raise PaymentConflict(
                    code="CHECKOUT_QUOTE_REQUIRED",
                    detail="A frozen checkout quote is required before settlement.",
                ) from exc

            try:
                existing = quote.settlement
            except ObjectDoesNotExist:
                existing = None
            if existing is not None:
                validate_settlement(settlement=existing, quote=quote)
                if existing.method != SettlementMethod.ZERO_CHARGE:
                    raise PaymentConflict(
                        code="QUOTE_ALREADY_SETTLED",
                        detail="The quote already has a provider settlement.",
                    )
                return existing

            if parking_session.status != SessionStatus.PAYMENT_PENDING:
                raise PaymentConflict(
                    code="INVALID_SESSION_STATE",
                    detail="Zero-charge settlement requires a payment-pending session.",
                )
            if quote.amount != 0:
                raise PaymentConflict(
                    code="ZERO_CHARGE_NOT_ALLOWED",
                    detail="Only a zero-amount quote can use zero-charge settlement.",
                )

            settlement = Settlement.objects.create(
                quote=quote,
                method=SettlementMethod.ZERO_CHARGE,
                amount=quote.amount,
                currency=quote.currency,
                settled_at=self.clock(),
            )
            validate_settlement(settlement=settlement, quote=quote)
            parking_session.status = SessionStatus.PAID
            parking_session.save(update_fields=["status", "updated_at"])
            return settlement
