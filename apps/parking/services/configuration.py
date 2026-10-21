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


def create_parking_lot(*, data: Mapping) -> ParkingLot:
    return _save(ParkingLot(**dict(data)))


def update_parking_lot(*, parking_lot: ParkingLot, data: Mapping) -> ParkingLot:
    fields = []
    for field in ("code", "name", "address", "timezone", "is_active"):
        if field in data:
            setattr(parking_lot, field, data[field])
            fields.append(field)
    return _save(parking_lot, update_fields=fields) if fields else parking_lot


@transaction.atomic
def create_floor(*, data: Mapping) -> Floor:
    values = dict(data)
    parking_lot = ParkingLot.objects.select_for_update().get(pk=values.pop("parking_lot").pk)
    if not parking_lot.is_active:
        raise ValidationError({"parking_lot": "New floors require an active parking lot."})
    return _save(Floor(parking_lot=parking_lot, **values))


def update_floor(*, floor: Floor, data: Mapping) -> Floor:
    fields = []
    for field in ("code", "name", "level", "is_active"):
        if field in data:
            setattr(floor, field, data[field])
            fields.append(field)
    return _save(floor, update_fields=fields) if fields else floor


@transaction.atomic
def create_gate(*, data: Mapping) -> Gate:
    values = dict(data)
    parking_lot = ParkingLot.objects.select_for_update().get(pk=values.pop("parking_lot").pk)
    if not parking_lot.is_active:
        raise ValidationError({"parking_lot": "New gates require an active parking lot."})
    return _save(Gate(parking_lot=parking_lot, **values))


def update_gate(*, gate: Gate, data: Mapping) -> Gate:
    fields = []
    for field in ("code", "name", "gate_type", "is_active"):
        if field in data:
            setattr(gate, field, data[field])
            fields.append(field)
    return _save(gate, update_fields=fields) if fields else gate


@transaction.atomic
def create_parking_spot(*, data: Mapping) -> ParkingSpot:
    values = dict(data)
    floor = (
        Floor.objects.select_for_update()
        .select_related("parking_lot")
        .get(pk=values.pop("floor").pk)
    )
    if not floor.is_active or not floor.parking_lot.is_active:
        raise ValidationError({"floor": "New spots require an active floor and parking lot."})
    return _save(ParkingSpot(floor=floor, **values))


def update_parking_spot(*, parking_spot: ParkingSpot, data: Mapping) -> ParkingSpot:
    fields = []
    for field in ("number", "spot_type", "operational_status"):
        if field in data:
            setattr(parking_spot, field, data[field])
            fields.append(field)
    return _save(parking_spot, update_fields=fields) if fields else parking_spot
