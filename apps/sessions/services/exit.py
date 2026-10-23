from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound

from apps.parking.enums import GateType
from apps.parking.models import Gate, ParkingSpot
from apps.payments.models import PaymentAttempt, Settlement
from apps.payments.services import validate_settlement
from apps.pricing.models import CheckoutQuote
from apps.sessions.enums import SessionStatus
from apps.sessions.exceptions import ExitConflict
from apps.sessions.models import ParkingSession

Clock = Callable[[], datetime]


@dataclass(frozen=True)
class ExitService:
    clock: Clock

    def exit(self, *, session_id: int, exit_gate_id: int, actor) -> ParkingSession:
        with transaction.atomic():
            # Exit lock order: session -> gate -> spot -> quote -> settlement -> attempt.
            try:
                parking_session = ParkingSession.objects.select_for_update().get(pk=session_id)
            except ParkingSession.DoesNotExist as exc:
                raise NotFound("Parking session not found.") from exc

            if parking_session.status == SessionStatus.CLOSED:
                if parking_session.exit_gate_id == exit_gate_id:
                    return parking_session
                raise ExitConflict(
                    code="EXIT_ALREADY_RECORDED",
                    detail="The session was already closed through a different exit gate.",
                )
            if parking_session.status != SessionStatus.PAID:
                raise ExitConflict(
                    code="SESSION_NOT_SETTLED",
                    detail="The parking session must be paid before exit.",
                )

            try:
                gate = Gate.objects.select_for_update().get(pk=exit_gate_id)
            except Gate.DoesNotExist as exc:
                raise NotFound("Exit gate not found.") from exc
            ParkingSpot.objects.select_for_update().get(pk=parking_session.spot_id)

            lot_id = parking_session.spot.floor.parking_lot_id
            if gate.parking_lot_id != lot_id:
                raise ExitConflict(
                    code="EXIT_GATE_LOT_MISMATCH",
                    detail="The exit gate belongs to a different parking lot.",
                )
            if not gate.is_active:
                raise ExitConflict(
                    code="EXIT_GATE_INACTIVE",
                    detail="The selected exit gate is inactive.",
                )
            if gate.gate_type not in {GateType.EXIT, GateType.BOTH}:
                raise ExitConflict(
                    code="GATE_NOT_EXIT_CAPABLE",
                    detail="The selected gate cannot release vehicles.",
                )

            try:
                quote = CheckoutQuote.objects.select_for_update().get(
                    parking_session=parking_session
                )
                settlement = Settlement.objects.select_for_update().get(quote=quote)
            except (CheckoutQuote.DoesNotExist, Settlement.DoesNotExist, ObjectDoesNotExist) as exc:
                raise ExitConflict(
                    code="SESSION_NOT_SETTLED",
                    detail="The parking session has no valid settlement.",
                ) from exc
            if settlement.payment_attempt_id is not None:
                settlement.payment_attempt = PaymentAttempt.objects.select_for_update().get(
                    pk=settlement.payment_attempt_id
                )
            validate_settlement(settlement=settlement, quote=quote)

            parking_session.status = SessionStatus.CLOSED
            parking_session.exit_gate = gate
            parking_session.exited_by = actor
            parking_session.closed_at = self.clock()
            parking_session.save(
                update_fields=[
                    "status",
                    "exit_gate",
                    "exited_by",
                    "closed_at",
                    "updated_at",
                ]
            )
            return parking_session


def build_exit_service() -> ExitService:
    return ExitService(clock=timezone.now)
