from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True)
class ProviderPaymentResult:
    merchant_reference: UUID
    provider_reference: str
    status: str
    amount: Decimal
    currency: str
    failure_code: str | None = None


class PaymentProvider(Protocol):
    def initiate_payment(
        self,
        *,
        merchant_reference: UUID,
        amount: Decimal,
        currency: str,
    ) -> ProviderPaymentResult: ...

    def retrieve_payment(self, *, merchant_reference: UUID) -> ProviderPaymentResult: ...
