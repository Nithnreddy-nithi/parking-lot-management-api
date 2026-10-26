from django.conf import settings
from django.utils import timezone

from apps.payments.adapters.razorpay import RazorpayPaymentProvider
from apps.payments.adapters.simulated import SimulatedPaymentProvider
from apps.payments.enums import PaymentProviderName
from apps.payments.services.confirmation import PaymentConfirmationService
from apps.payments.services.initiation import PaymentInitiationService
from apps.payments.services.refunds import RefundInitiationService, RefundResultService
from apps.payments.services.settlement import PaymentResultService, ZeroChargeSettlementService
from apps.payments.services.webhooks import RazorpayWebhookService


def build_payment_result_service() -> PaymentResultService:
    return PaymentResultService(clock=timezone.now)


def build_payment_provider(provider_name: str | None = None):
    selected = provider_name or settings.PAYMENT_PROVIDER
    if selected == PaymentProviderName.SIMULATED:
        return SimulatedPaymentProvider()
    if selected == PaymentProviderName.RAZORPAY:
        return RazorpayPaymentProvider(
            key_id=settings.RAZORPAY_KEY_ID,
            key_secret=settings.RAZORPAY_KEY_SECRET,
        )
    raise ValueError("Unsupported payment provider configuration.")


def build_payment_initiation_service() -> PaymentInitiationService:
    return PaymentInitiationService(
        provider=build_payment_provider(),
        result_service=build_payment_result_service(),
    )


def build_zero_charge_settlement_service() -> ZeroChargeSettlementService:
    return ZeroChargeSettlementService(clock=timezone.now)


def build_payment_confirmation_service(*, provider_name: str) -> PaymentConfirmationService:
    return PaymentConfirmationService(
        provider=build_payment_provider(provider_name),
        result_service=build_payment_result_service(),
    )


def build_refund_result_service() -> RefundResultService:
    return RefundResultService(clock=timezone.now)


def build_refund_initiation_service() -> RefundInitiationService:
    return RefundInitiationService(
        provider=build_payment_provider(PaymentProviderName.RAZORPAY),
        result_service=build_refund_result_service(),
    )


def build_razorpay_webhook_service() -> RazorpayWebhookService:
    return RazorpayWebhookService(
        provider=build_payment_provider(PaymentProviderName.RAZORPAY),
        payment_results=build_payment_result_service(),
        refund_results=build_refund_result_service(),
    )
