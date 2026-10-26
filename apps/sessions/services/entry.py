from dataclasses import dataclass

from django.db import IntegrityError, transaction
from rest_framework.exceptions import NotFound

from apps.parking.enums import GateType
from apps.parking.models import Gate, Vehicle
from apps.pricing.exceptions import PricingConflict
from apps.pricing.services import create_snapshot, get_active_policy_for_entry
from apps.sessions.allocation import AllocationStrategy, DeterministicAllocationStrategy
from apps.sessions.exceptions import EntryConflict, vehicle_already_parked
from apps.sessions.models import ParkingSession
from apps.sessions.repositories import (
    create_active_session,
    has_open_session_for_vehicle,
    lock_gate,
    lock_lot,
    lock_preferred_spot,
    lock_vehicle,
)


def _constraint_name(exc: IntegrityError) -> str | None:
    cause = exc.__cause__
    diagnostics = getattr(cause, "diag", None)
    return getattr(diagnostics, "constraint_name", None)


@dataclass(frozen=True)
class EntryService:
    allocation_strategy: AllocationStrategy

    def enter(self, *, vehicle_id: int, entry_gate_id: int, actor) -> ParkingSession:
        try:
            gate_lot_id = Gate.objects.only("parking_lot_id").get(pk=entry_gate_id).parking_lot_id
        except Gate.DoesNotExist as exc:
            raise NotFound("Entry gate not found.") from exc

        try:
            with transaction.atomic():
                # Shared lock order: lot -> gate -> vehicle -> pricing policy -> spot.
                parking_lot = lock_lot(lot_id=gate_lot_id)
                gate = lock_gate(gate_id=entry_gate_id)
                try:
                    vehicle = lock_vehicle(vehicle_id=vehicle_id)
                except Vehicle.DoesNotExist as exc:
                    raise NotFound("Vehicle not found.") from exc

                if not parking_lot.is_active:
                    raise EntryConflict(code="LOT_INACTIVE", detail="The parking lot is inactive.")
                if not gate.is_active:
                    raise EntryConflict(
                        code="ENTRY_GATE_INACTIVE",
                        detail="The entry gate is inactive.",
                    )
                if gate.gate_type not in {GateType.ENTRY, GateType.BOTH}:
                    raise EntryConflict(
                        code="GATE_NOT_ENTRY_CAPABLE",
                        detail="The selected gate cannot admit vehicles.",
                    )
                if not vehicle.is_active:
                    raise EntryConflict(
                        code="VEHICLE_INACTIVE",
                        detail="The vehicle is inactive.",
                    )
                if has_open_session_for_vehicle(vehicle_id=vehicle.pk):
                    raise vehicle_already_parked()

                pricing_policy = get_active_policy_for_entry(
                    lot_id=parking_lot.pk,
                    vehicle_type=vehicle.vehicle_type,
                )
                if pricing_policy is None:
                    raise PricingConflict(
                        code="PRICING_NOT_CONFIGURED",
                        detail="No active pricing policy exists for this vehicle type and lot.",
                    )

                spot = lock_preferred_spot(
                    lot_id=parking_lot.pk,
                    vehicle_type=vehicle.vehicle_type,
                    strategy=self.allocation_strategy,
                )
                if spot is None:
                    raise EntryConflict(
                        code="NO_COMPATIBLE_SPOT",
                        detail="No compatible eligible parking spot is available.",
                    )

                parking_session = create_active_session(
                    vehicle=vehicle,
                    spot=spot,
                    entry_gate=gate,
                    entered_by=actor,
                )
                create_snapshot(parking_session=parking_session, policy=pricing_policy)
                return parking_session
        except IntegrityError as exc:
            constraint = _constraint_name(exc)
            if constraint == "session_one_open_per_vehicle":
                raise vehicle_already_parked() from exc
            if constraint == "session_one_open_per_spot":
                raise EntryConflict(
                    code="NO_COMPATIBLE_SPOT",
                    detail="The selected spot was allocated by another request.",
                ) from exc
            raise


def build_entry_service() -> EntryService:
    return EntryService(allocation_strategy=DeterministicAllocationStrategy())
