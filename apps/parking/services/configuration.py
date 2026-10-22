from collections.abc import Mapping

from django.db import IntegrityError, transaction
from rest_framework.exceptions import ValidationError

from apps.parking.models import Floor, Gate, ParkingLot, ParkingSpot
from apps.parking.services.conflicts import translate_integrity_error


def _save(instance, *, update_fields: list[str] | None = None):
    try:
        with transaction.atomic():
            if update_fields:
                instance.save(update_fields=[*update_fields, "updated_at"])
            else:
                instance.save()
    except IntegrityError as exc:
        translate_integrity_error(exc)
    return instance


def _apply(instance, data: Mapping, fields: tuple[str, ...]):
    changed = []
    for field in fields:
        if field in data:
            setattr(instance, field, data[field])
            changed.append(field)
    return _save(instance, update_fields=changed) if changed else instance


def create_parking_lot(*, data: Mapping) -> ParkingLot:
    return _save(ParkingLot(**dict(data)))


@transaction.atomic
def update_parking_lot(*, parking_lot: ParkingLot, data: Mapping) -> ParkingLot:
    # Configuration and entry serialize on the lot row before locking descendants.
    locked_lot = ParkingLot.objects.select_for_update().get(pk=parking_lot.pk)
    return _apply(locked_lot, data, ("code", "name", "address", "timezone", "is_active"))


@transaction.atomic
def create_floor(*, data: Mapping) -> Floor:
    values = dict(data)
    parking_lot = ParkingLot.objects.select_for_update().get(pk=values.pop("parking_lot").pk)
    if not parking_lot.is_active:
        raise ValidationError({"parking_lot": "New floors require an active parking lot."})
    return _save(Floor(parking_lot=parking_lot, **values))


@transaction.atomic
def update_floor(*, floor: Floor, data: Mapping) -> Floor:
    ParkingLot.objects.select_for_update().get(pk=floor.parking_lot_id)
    locked_floor = Floor.objects.select_for_update().get(pk=floor.pk)
    return _apply(locked_floor, data, ("code", "name", "level", "is_active"))


@transaction.atomic
def create_gate(*, data: Mapping) -> Gate:
    values = dict(data)
    parking_lot = ParkingLot.objects.select_for_update().get(pk=values.pop("parking_lot").pk)
    if not parking_lot.is_active:
        raise ValidationError({"parking_lot": "New gates require an active parking lot."})
    return _save(Gate(parking_lot=parking_lot, **values))


@transaction.atomic
def update_gate(*, gate: Gate, data: Mapping) -> Gate:
    ParkingLot.objects.select_for_update().get(pk=gate.parking_lot_id)
    locked_gate = Gate.objects.select_for_update().get(pk=gate.pk)
    return _apply(locked_gate, data, ("code", "name", "gate_type", "is_active"))


@transaction.atomic
def create_parking_spot(*, data: Mapping) -> ParkingSpot:
    values = dict(data)
    supplied_floor = values.pop("floor")
    ParkingLot.objects.select_for_update().get(pk=supplied_floor.parking_lot_id)
    floor = (
        Floor.objects.select_for_update().select_related("parking_lot").get(pk=supplied_floor.pk)
    )
    if not floor.is_active or not floor.parking_lot.is_active:
        raise ValidationError({"floor": "New spots require an active floor and parking lot."})
    return _save(ParkingSpot(floor=floor, **values))


@transaction.atomic
def update_parking_spot(*, parking_spot: ParkingSpot, data: Mapping) -> ParkingSpot:
    from apps.sessions.enums import OPEN_SESSION_STATUSES
    from apps.sessions.exceptions import EntryConflict
    from apps.sessions.models import ParkingSession

    ParkingLot.objects.select_for_update().get(pk=parking_spot.floor.parking_lot_id)
    locked_spot = ParkingSpot.objects.select_for_update().get(pk=parking_spot.pk)
    protected_change = any(
        field in data and data[field] != getattr(locked_spot, field)
        for field in ("number", "spot_type")
    )
    if (
        protected_change
        and ParkingSession.objects.filter(
            spot_id=locked_spot.pk,
            status__in=OPEN_SESSION_STATUSES,
        ).exists()
    ):
        raise EntryConflict(
            code="SPOT_HAS_OPEN_SESSION",
            detail="Spot number and type cannot change while the spot is occupied.",
        )
    return _apply(locked_spot, data, ("number", "spot_type", "operational_status"))
