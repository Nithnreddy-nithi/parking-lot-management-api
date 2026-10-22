from django.db.models import Case, IntegerField, QuerySet, Value, When

from apps.parking.enums import SpotOperationalStatus
from apps.parking.models import Gate, ParkingLot, ParkingSpot, Vehicle
from apps.sessions.allocation import AllocationStrategy
from apps.sessions.enums import OPEN_SESSION_STATUSES
from apps.sessions.models import ParkingSession


def lock_lot(*, lot_id: int) -> ParkingLot:
    return ParkingLot.objects.select_for_update().get(pk=lot_id)


def lock_gate(*, gate_id: int) -> Gate:
    return Gate.objects.select_for_update().select_related("parking_lot").get(pk=gate_id)


def lock_vehicle(*, vehicle_id: int) -> Vehicle:
    return Vehicle.objects.select_for_update().get(pk=vehicle_id)


def has_open_session_for_vehicle(*, vehicle_id: int) -> bool:
    return ParkingSession.objects.filter(
        vehicle_id=vehicle_id,
        status__in=OPEN_SESSION_STATUSES,
    ).exists()


def eligible_spots(
    *,
    lot_id: int,
    vehicle_type: str,
    strategy: AllocationStrategy,
) -> QuerySet[ParkingSpot]:
    preferences = strategy.spot_type_preferences(vehicle_type)
    preference_order = Case(
        *[
            When(spot_type=spot_type, then=Value(index))
            for index, spot_type in enumerate(preferences)
        ],
        default=Value(len(preferences)),
        output_field=IntegerField(),
    )
    return (
        ParkingSpot.objects.select_for_update()
        .select_related("floor", "floor__parking_lot")
        .filter(
            floor__parking_lot_id=lot_id,
            floor__parking_lot__is_active=True,
            floor__is_active=True,
            operational_status=SpotOperationalStatus.ENABLED,
            spot_type__in=preferences,
        )
        .exclude(parking_sessions__status__in=OPEN_SESSION_STATUSES)
        .annotate(_compatibility_preference=preference_order)
        .order_by("_compatibility_preference", *strategy.ordering_fields())
    )


def lock_preferred_spot(
    *,
    lot_id: int,
    vehicle_type: str,
    strategy: AllocationStrategy,
) -> ParkingSpot | None:
    return eligible_spots(lot_id=lot_id, vehicle_type=vehicle_type, strategy=strategy).first()


def create_active_session(
    *,
    vehicle: Vehicle,
    spot: ParkingSpot,
    entry_gate: Gate,
    entered_by,
) -> ParkingSession:
    return ParkingSession.objects.create(
        vehicle=vehicle,
        spot=spot,
        entry_gate=entry_gate,
        entered_by=entered_by,
        registration_number_snapshot=vehicle.registration_number,
        vehicle_type_snapshot=vehicle.vehicle_type,
    )
