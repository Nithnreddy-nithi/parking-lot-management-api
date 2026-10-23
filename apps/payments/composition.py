from django.utils import timezone

from apps.payments.adapters.simulated import SimulatedPaymentProvider
from apps.payments.services.initiation import PaymentInitiationService
from apps.payments.services.settlement import PaymentResultService, ZeroChargeSettlementService


def build_payment_result_service() -> PaymentResultService:
    return PaymentResultService(clock=timezone.now)


def build_payment_initiation_service() -> PaymentInitiationService:
    return PaymentInitiationService(
        provider=SimulatedPaymentProvider(),
        result_service=build_payment_result_service(),
    )


def build_zero_charge_settlement_service() -> ZeroChargeSettlementService:
    return ZeroChargeSettlementService(clock=timezone.now)
