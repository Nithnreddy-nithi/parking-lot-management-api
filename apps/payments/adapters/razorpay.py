from decimal import Decimal
from uuid import UUID

import razorpay

from apps.payments.adapters.base import ProviderPaymentResult, ProviderRefundResult
from apps.payments.enums import PaymentStatus, RefundStatus
from apps.payments.exceptions import ProviderOutcomeUnknown, ProviderProtocolError


def _to_subunits(amount: Decimal) -> int:
    subunits = amount * 100
    if subunits != subunits.to_integral_value():
        raise ProviderProtocolError("Razorpay amounts must have at most two decimal places.")
    return int(subunits)


def _from_subunits(amount: object) -> Decimal:
    try:
        return (Decimal(str(amount)) / 100).quantize(Decimal("0.01"))
    except Exception as exc:
        raise ProviderProtocolError("Razorpay returned an invalid amount.") from exc


class RazorpayPaymentProvider:
    """Razorpay Orders/Payments adapter. It never handles raw card or UPI credentials."""

    name = "RAZORPAY"

    def __init__(self, *, key_id: str, key_secret: str, client=None):
        self.key_id = key_id
        self.client = client or razorpay.Client(auth=(key_id, key_secret))

    @staticmethod
    def _receipt(merchant_reference: UUID) -> str:
        return f"pay_{merchant_reference.hex}"

    @staticmethod
    def _merchant_reference(receipt: object) -> UUID:
        try:
            return UUID(str(receipt).removeprefix("pay_"))
        except (ValueError, TypeError, AttributeError) as exc:
            raise ProviderProtocolError("Razorpay returned an invalid merchant receipt.") from exc

    def initiate_payment(
        self,
        *,
        merchant_reference: UUID,
        amount: Decimal,
        currency: str,
    ) -> ProviderPaymentResult:
        data = {
            "amount": _to_subunits(amount),
            "currency": currency,
            "receipt": self._receipt(merchant_reference),
            "notes": {"payment_attempt_id": str(merchant_reference)},
        }
        try:
            order = self.client.order.create(data=data)
        except razorpay.errors.BadRequestError as exc:
            raise ProviderProtocolError("Razorpay rejected the order request.") from exc
        except Exception as exc:
            # The request may have reached Razorpay. Never create a new attempt automatically.
            raise ProviderOutcomeUnknown("Razorpay order creation outcome is unknown.") from exc
        return self._order_result(order, expected_merchant_reference=merchant_reference)

    def retrieve_payment(
        self,
        *,
        merchant_reference: UUID,
        provider_order_reference: str | None = None,
        provider_reference: str | None = None,
    ) -> ProviderPaymentResult:
        if provider_reference:
            try:
                payment = self.client.payment.fetch(provider_reference)
            except razorpay.errors.BadRequestError as exc:
                raise ProviderProtocolError("Razorpay rejected the payment lookup.") from exc
            except Exception as exc:
                raise ProviderOutcomeUnknown("Razorpay payment retrieval failed.") from exc
            return self._payment_result(payment, merchant_reference=merchant_reference)
        if not provider_order_reference:
            try:
                collection = self.client.order.all(
                    {"receipt": self._receipt(merchant_reference), "count": 2}
                )
            except razorpay.errors.BadRequestError as exc:
                raise ProviderProtocolError("Razorpay rejected the order lookup.") from exc
            except Exception as exc:
                raise ProviderOutcomeUnknown("Razorpay order lookup failed.") from exc
            orders = collection.get("items", [])
            if not orders:
                raise ProviderOutcomeUnknown("Razorpay has not exposed the order yet.")
            if len(orders) != 1:
                raise ProviderProtocolError(
                    "Razorpay returned multiple orders for the unique merchant receipt."
                )
            provider_order_reference = str(orders[0].get("id", ""))
            if not provider_order_reference:
                raise ProviderProtocolError("Razorpay returned an incomplete order lookup.")
        try:
            order = self.client.order.fetch(provider_order_reference)
            collection = self.client.order.payments(provider_order_reference)
        except razorpay.errors.BadRequestError as exc:
            raise ProviderProtocolError("Razorpay rejected the order lookup.") from exc
        except Exception as exc:
            raise ProviderOutcomeUnknown("Razorpay order retrieval failed.") from exc
        payments = collection.get("items", [])
        captured = next((item for item in payments if item.get("status") == "captured"), None)
        failed = next((item for item in reversed(payments) if item.get("status") == "failed"), None)
        if captured or failed:
            return self._payment_result(
                captured or failed,
                merchant_reference=merchant_reference,
            )
        return self._order_result(order, expected_merchant_reference=merchant_reference)

    def verify_checkout_signature(
        self,
        *,
        provider_order_reference: str,
        provider_reference: str,
        signature: str,
    ) -> None:
        try:
            self.client.utility.verify_payment_signature(
                {
                    "razorpay_order_id": provider_order_reference,
                    "razorpay_payment_id": provider_reference,
                    "razorpay_signature": signature,
                }
            )
        except Exception as exc:
            raise ProviderProtocolError("The Razorpay checkout signature is invalid.") from exc

    def verify_webhook_signature(self, *, body: bytes, signature: str, secret: str) -> None:
        try:
            self.client.utility.verify_webhook_signature(body.decode("utf-8"), signature, secret)
        except Exception as exc:
            raise ProviderProtocolError("The Razorpay webhook signature is invalid.") from exc

    def initiate_refund(
        self,
        *,
        merchant_reference: UUID,
        payment_reference: str,
        amount: Decimal,
        currency: str,
    ) -> ProviderRefundResult:
        try:
            payload = self.client.payment.refund(
                payment_reference,
                {
                    "amount": _to_subunits(amount),
                    "notes": {"refund_id": str(merchant_reference)},
                    "receipt": f"refund_{merchant_reference.hex}"[:40],
                },
            )
        except razorpay.errors.BadRequestError as exc:
            raise ProviderProtocolError("Razorpay rejected the refund request.") from exc
        except Exception as exc:
            raise ProviderOutcomeUnknown("Razorpay refund outcome is unknown.") from exc
        return self._refund_result(
            payload,
            merchant_reference=merchant_reference,
            expected_currency=currency,
        )

    def retrieve_refund(
        self,
        *,
        merchant_reference: UUID,
        provider_reference: str,
    ) -> ProviderRefundResult:
        try:
            payload = self.client.refund.fetch(provider_reference)
        except razorpay.errors.BadRequestError as exc:
            raise ProviderProtocolError("Razorpay rejected the refund lookup.") from exc
        except Exception as exc:
            raise ProviderOutcomeUnknown("Razorpay refund retrieval failed.") from exc
        return self._refund_result(payload, merchant_reference=merchant_reference)

    def _order_result(
        self,
        order: dict,
        *,
        expected_merchant_reference: UUID,
    ) -> ProviderPaymentResult:
        merchant_reference = self._merchant_reference(order.get("receipt"))
        if merchant_reference != expected_merchant_reference:
            raise ProviderProtocolError("Razorpay returned a different merchant receipt.")
        order_reference = str(order.get("id", ""))
        currency = str(order.get("currency", ""))
        if not order_reference or not currency:
            raise ProviderProtocolError("Razorpay returned an incomplete order.")
        return ProviderPaymentResult(
            merchant_reference=merchant_reference,
            provider_reference=None,
            provider_order_reference=order_reference,
            status=PaymentStatus.PENDING,
            amount=_from_subunits(order.get("amount")),
            currency=currency,
        )

    @staticmethod
    def _payment_result(payment: dict, *, merchant_reference: UUID) -> ProviderPaymentResult:
        provider_reference = str(payment.get("id", ""))
        order_reference = str(payment.get("order_id", ""))
        currency = str(payment.get("currency", ""))
        if not provider_reference or not order_reference or not currency:
            raise ProviderProtocolError("Razorpay returned an incomplete payment.")
        raw_status = payment.get("status")
        status = {
            "captured": PaymentStatus.SUCCEEDED,
            # Refunds do not invalidate the historical capture or settlement.
            "refunded": PaymentStatus.SUCCEEDED,
            "failed": PaymentStatus.FAILED,
            "created": PaymentStatus.PENDING,
            "authorized": PaymentStatus.PENDING,
        }.get(raw_status)
        if status is None:
            raise ProviderProtocolError("Razorpay returned an unsupported payment status.")
        error = payment.get("error_code") or payment.get("error_reason")
        return ProviderPaymentResult(
            merchant_reference=merchant_reference,
            provider_reference=provider_reference,
            provider_order_reference=order_reference,
            status=status,
            amount=_from_subunits(payment.get("amount")),
            currency=currency,
            failure_code=str(error or "") or None,
        )

    @staticmethod
    def _refund_result(
        refund: dict,
        *,
        merchant_reference: UUID,
        expected_currency: str | None = None,
    ) -> ProviderRefundResult:
        reference = str(refund.get("id", ""))
        payment_reference = str(refund.get("payment_id", ""))
        currency = str(refund.get("currency") or expected_currency or "")
        if not reference or not payment_reference or not currency:
            raise ProviderProtocolError("Razorpay returned an incomplete refund.")
        raw_status = refund.get("status", "processed")
        status = {
            "processed": RefundStatus.SUCCEEDED,
            "pending": RefundStatus.PENDING,
            "failed": RefundStatus.FAILED,
        }.get(raw_status)
        if status is None:
            raise ProviderProtocolError("Razorpay returned an unsupported refund status.")
        return ProviderRefundResult(
            merchant_reference=merchant_reference,
            provider_reference=reference,
            payment_reference=payment_reference,
            status=status,
            amount=_from_subunits(refund.get("amount")),
            currency=currency,
            failure_code=str(refund.get("error_code") or "") or None,
        )
