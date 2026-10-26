from decimal import Decimal
from uuid import UUID

from django.conf import settings
from django.db import transaction

from apps.payments.adapters.base import ProviderPaymentResult
from apps.payments.enums import PaymentStatus, SimulationScenario
from apps.payments.exceptions import ProviderOutcomeUnknown, ProviderProtocolError
from apps.payments.models import SimulatedPaymentRecord


class SimulatedPaymentProvider:
    """Deterministic, database-backed simulator suitable for multi-request local demos."""

    name = "SIMULATED"

    def _scenario(self) -> str:
        scenario = getattr(settings, "SIMULATED_PAYMENT_SCENARIO", SimulationScenario.SUCCESS)
        if scenario not in SimulationScenario.values:
            raise ProviderProtocolError("The configured simulator scenario is invalid.")
        return scenario

    @staticmethod
    def _provider_reference(merchant_reference: UUID) -> str:
        return f"sim_{merchant_reference.hex}"

    @staticmethod
    def _result(record: SimulatedPaymentRecord) -> ProviderPaymentResult:
        return ProviderPaymentResult(
            merchant_reference=record.merchant_reference,
            provider_reference=record.provider_reference,
            status=record.status,
            amount=record.amount,
            currency=record.currency,
            failure_code=record.failure_code,
        )

    def initiate_payment(
        self,
        *,
        merchant_reference: UUID,
        amount: Decimal,
        currency: str,
    ) -> ProviderPaymentResult:
        with transaction.atomic():
            scenario = self._scenario()
            status = {
                SimulationScenario.SUCCESS: PaymentStatus.SUCCEEDED,
                SimulationScenario.FAILURE: PaymentStatus.FAILED,
                SimulationScenario.PENDING: PaymentStatus.PENDING,
                SimulationScenario.TIMEOUT_AFTER_SUCCESS: PaymentStatus.SUCCEEDED,
            }[scenario]
            SimulatedPaymentRecord.objects.get_or_create(
                merchant_reference=merchant_reference,
                defaults={
                    "provider_reference": self._provider_reference(merchant_reference),
                    "amount": amount,
                    "currency": currency,
                    "status": status,
                    "failure_code": "SIMULATED_DECLINE" if status == PaymentStatus.FAILED else "",
                    "scenario": scenario,
                },
            )
            record = SimulatedPaymentRecord.objects.select_for_update().get(
                merchant_reference=merchant_reference
            )

            if record.amount != amount or record.currency != currency:
                raise ProviderProtocolError(
                    "A merchant reference was reused with different financial values."
                )

            record.initiation_count += 1
            record.save(update_fields=["initiation_count", "updated_at"])
            should_timeout = (
                record.scenario == SimulationScenario.TIMEOUT_AFTER_SUCCESS
                and record.initiation_count == 1
            )
            result = self._result(record)
        if should_timeout:
            raise ProviderOutcomeUnknown("The simulated response timed out after success.")
        return result

    def retrieve_payment(
        self,
        *,
        merchant_reference: UUID,
        provider_order_reference: str | None = None,
        provider_reference: str | None = None,
    ) -> ProviderPaymentResult:
        try:
            record = SimulatedPaymentRecord.objects.get(merchant_reference=merchant_reference)
        except SimulatedPaymentRecord.DoesNotExist as exc:
            raise ProviderProtocolError("The simulator has no record for this payment.") from exc
        return self._result(record)

    def verify_checkout_signature(self, **kwargs) -> None:
        raise ProviderProtocolError("Checkout signatures are not used by the simulator.")

    def verify_webhook_signature(self, **kwargs) -> None:
        raise ProviderProtocolError("Webhooks are not used by the simulator.")

    def initiate_refund(self, **kwargs):
        raise ProviderProtocolError("Refunds are only supported by the Razorpay adapter.")

    def retrieve_refund(self, **kwargs):
        raise ProviderProtocolError("Refunds are only supported by the Razorpay adapter.")
