from collections.abc import Mapping

from django.db import IntegrityError, transaction

from apps.accounts.models import User
from apps.parking.models import Vehicle
from apps.parking.services.conflicts import translate_integrity_error


def _save(instance, *, update_fields: list[str] | None = None) -> Vehicle:
    try:
        with transaction.atomic():
            if update_fields:
                instance.save(update_fields=[*update_fields, "updated_at"])
            else:
                instance.save()
    except IntegrityError as exc:
        translate_integrity_error(exc)
    return instance


def create_vehicle(*, owner: User, data: Mapping) -> Vehicle:
    return _save(Vehicle(owner=owner, **dict(data)))


def update_vehicle(*, vehicle: Vehicle, data: Mapping) -> Vehicle:
    fields = []
    for field in ("registration_number", "vehicle_type", "is_active"):
        if field in data:
            setattr(vehicle, field, data[field])
            fields.append(field)
    return _save(vehicle, update_fields=fields) if fields else vehicle
