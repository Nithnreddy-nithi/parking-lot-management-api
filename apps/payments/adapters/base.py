from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True)
class ProviderPaymentResult:
    merchant_reference: UUID
    provider_reference: str | None
    status: str
    amount: Decimal
    currency: str
    failure_code: str | None = None
    provider_order_reference: str | None = None


@dataclass(frozen=True)
class ProviderRefundResult:
    merchant_reference: UUID
    provider_reference: str
    payment_reference: str
    status: str
    amount: Decimal
    currency: str
    failure_code: str | None = None


class PaymentProvider(Protocol):
    name: str

    def initiate_payment(
        self,
        *,
        merchant_reference: UUID,
        amount: Decimal,
        currency: str,
    ) -> ProviderPaymentResult: ...

    def retrieve_payment(
        self,
        *,
        merchant_reference: UUID,
        provider_order_reference: str | None = None,
        provider_reference: str | None = None,
    ) -> ProviderPaymentResult: ...

    def verify_checkout_signature(
        self,
        *,
        provider_order_reference: str,
        provider_reference: str,
        signature: str,
    ) -> None: ...

    def verify_webhook_signature(self, *, body: bytes, signature: str, secret: str) -> None: ...

    def initiate_refund(
        self,
        *,
        merchant_reference: UUID,
        payment_reference: str,
        amount: Decimal,
        currency: str,
    ) -> ProviderRefundResult: ...

    def retrieve_refund(
        self,
        *,
        merchant_reference: UUID,
        provider_reference: str,
    ) -> ProviderRefundResult: ...
