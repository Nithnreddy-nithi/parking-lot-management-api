from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound

from apps.parking.models import ParkingLot
from apps.pricing.calculators import FeeCalculator, resolve_calculator
from apps.pricing.exceptions import PricingConflict
from apps.pricing.models import CheckoutQuote
from apps.sessions.enums import SessionStatus
from apps.sessions.models import ParkingSession

CalculatorResolver = Callable[[str], FeeCalculator]
Clock = Callable[[], datetime]


@dataclass(frozen=True)
class CheckoutService:
    calculator_resolver: CalculatorResolver
    clock: Clock

    def checkout(self, *, session_id: int, actor) -> CheckoutQuote:
        try:
            lot_id = ParkingSession.objects.values_list(
                "spot__floor__parking_lot_id",
                flat=True,
            ).get(pk=session_id)
        except ParkingSession.DoesNotExist as exc:
            raise NotFound("Parking session not found.") from exc

        with transaction.atomic():
            # Phase 5 extends the shared order with lot -> session for checkout.
            ParkingLot.objects.select_for_update().get(pk=lot_id)
            parking_session = ParkingSession.objects.select_for_update().get(pk=session_id)
            quote = CheckoutQuote.objects.filter(parking_session=parking_session).first()

            if parking_session.status == SessionStatus.PAYMENT_PENDING:
                if quote is None:
                    raise PricingConflict(
                        code="FINANCIAL_INTEGRITY_ERROR",
                        detail="The session state and checkout quote are inconsistent.",
                    )
                return quote

            if parking_session.status != SessionStatus.ACTIVE:
                raise PricingConflict(
                    code="INVALID_SESSION_STATE",
                    detail="Only an active session can be checked out.",
                )
            if quote is not None:
                raise PricingConflict(
                    code="FINANCIAL_INTEGRITY_ERROR",
                    detail="An active session cannot already have a checkout quote.",
                )

            try:
                snapshot = parking_session.pricing_snapshot
            except ObjectDoesNotExist as exc:
                raise PricingConflict(
                    code="SESSION_PRICING_NOT_CONFIGURED",
                    detail="The parking session has no pricing snapshot.",
                ) from exc

            try:
                calculator = self.calculator_resolver(snapshot.calculator_version)
            except ValueError as exc:
                raise PricingConflict(
                    code="UNSUPPORTED_CALCULATOR",
                    detail="The session references an unsupported pricing calculator.",
                ) from exc

            calculated_until = self.clock()
            try:
                result = calculator.calculate(
                    pricing=snapshot,
                    entered_at=parking_session.entered_at,
                    calculated_until=calculated_until,
                )
            except ValueError as exc:
                raise PricingConflict(
                    code="PRICING_CALCULATION_ERROR",
                    detail=str(exc),
                ) from exc

            quote = CheckoutQuote.objects.create(
                parking_session=parking_session,
                calculated_until=calculated_until,
                amount=result.amount,
                currency=result.currency,
                calculation_breakdown=result.breakdown,
                created_by=actor,
            )
            parking_session.status = SessionStatus.PAYMENT_PENDING
            parking_session.save(update_fields=["status", "updated_at"])
            return quote


def build_checkout_service() -> CheckoutService:
    return CheckoutService(calculator_resolver=resolve_calculator, clock=timezone.now)
