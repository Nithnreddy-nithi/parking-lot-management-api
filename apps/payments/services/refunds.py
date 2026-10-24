from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum

from apps.payments.adapters.base import PaymentProvider, ProviderRefundResult
from apps.payments.enums import PaymentProviderName, PaymentStatus, RefundStatus
from apps.payments.exceptions import PaymentConflict, ProviderOutcomeUnknown, ProviderProtocolError
from apps.payments.models import PaymentAttempt, Refund, Settlement


@dataclass(frozen=True)
class RefundResultService:
    clock: Callable[[], datetime]

    def apply(self, *, refund_id, result: ProviderRefundResult) -> Refund:
        with transaction.atomic():
            refund = (
                Refund.objects.select_for_update()
                .select_related("settlement__payment_attempt")
                .get(pk=refund_id)
            )
            attempt = refund.settlement.payment_attempt
            if (
                result.merchant_reference != refund.pk
                or result.payment_reference != attempt.provider_reference
            ):
                raise PaymentConflict(
                    code="REFUND_PROVIDER_REFERENCE_MISMATCH",
                    detail="The provider refund does not match the original payment.",
                )
            if result.amount != refund.amount or result.currency != refund.currency:
                raise PaymentConflict(
                    code="REFUND_FINANCIAL_MISMATCH",
                    detail="The provider refund amount or currency does not match.",
                )
            if result.status not in RefundStatus.values or not result.provider_reference:
                raise PaymentConflict(
                    code="INVALID_REFUND_RESULT",
                    detail="The provider returned an invalid refund result.",
                )
            if refund.status != RefundStatus.PENDING:
                identical = (
                    refund.status == result.status
                    and refund.provider_reference == result.provider_reference
                )
                if not identical:
                    raise PaymentConflict(
                        code="CONTRADICTORY_REFUND_RESULT",
                        detail="The provider result contradicts the terminal refund.",
                    )
                return refund
            refund.provider_reference = result.provider_reference
            refund.status = result.status
            refund.failure_code = (
                result.failure_code or "PROVIDER_REFUND_FAILED"
                if result.status == RefundStatus.FAILED
                else ""
            )
            if result.status != RefundStatus.PENDING:
                refund.completed_at = self.clock()
            refund.save(
                update_fields=[
                    "provider_reference",
                    "status",
                    "failure_code",
                    "completed_at",
                    "updated_at",
                ]
            )
            return refund


@dataclass(frozen=True)
class RefundInitiationService:
    provider: PaymentProvider
    result_service: RefundResultService

    def initiate(
        self,
        *,
        payment_attempt_id,
        amount: Decimal,
        reason: str,
        actor,
    ) -> Refund:
        refund = self._prepare(
            payment_attempt_id=payment_attempt_id,
            amount=amount,
            reason=reason,
            actor=actor,
        )
        try:
            result = self.provider.initiate_refund(
                merchant_reference=refund.pk,
                payment_reference=refund.settlement.payment_attempt.provider_reference,
                amount=refund.amount,
                currency=refund.currency,
            )
        except ProviderOutcomeUnknown:
            return refund
        except ProviderProtocolError as exc:
            raise PaymentConflict(
                code="REFUND_PROVIDER_ERROR",
                detail="The payment provider could not safely process the refund.",
            ) from exc
        return self.result_service.apply(refund_id=refund.pk, result=result)

    def _prepare(self, *, payment_attempt_id, amount, reason, actor) -> Refund:
        with transaction.atomic():
            try:
                # Matches exit's financial suffix: settlement -> payment attempt.
                settlement = Settlement.objects.select_for_update().get(
                    payment_attempt_id=payment_attempt_id
                )
                attempt = PaymentAttempt.objects.select_for_update().get(pk=payment_attempt_id)
            except (PaymentAttempt.DoesNotExist, Settlement.DoesNotExist) as exc:
                raise PaymentConflict(
                    code="SETTLED_PAYMENT_REQUIRED",
                    detail="Refunds require a successfully settled provider payment.",
                ) from exc
            if (
                attempt.provider != PaymentProviderName.RAZORPAY
                or attempt.status != PaymentStatus.SUCCEEDED
                or not attempt.provider_reference
            ):
                raise PaymentConflict(
                    code="REFUND_NOT_SUPPORTED",
                    detail="Only captured Razorpay payments can be refunded here.",
                )
            reserved = Refund.objects.filter(
                settlement=settlement,
                status__in=(RefundStatus.PENDING, RefundStatus.SUCCEEDED),
            ).aggregate(total=Sum("amount"))["total"] or Decimal("0")
            if amount <= 0 or reserved + amount > settlement.amount:
                raise PaymentConflict(
                    code="REFUND_AMOUNT_EXCEEDS_AVAILABLE",
                    detail="The refund exceeds the unrefunded settlement amount.",
                )
            return Refund.objects.create(
                settlement=settlement,
                amount=amount,
                currency=settlement.currency,
                status=RefundStatus.PENDING,
                reason=reason,
                requested_by=actor,
            )
