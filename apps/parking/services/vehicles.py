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


@transaction.atomic
def update_vehicle(*, vehicle: Vehicle, data: Mapping) -> Vehicle:
    from apps.sessions.enums import OPEN_SESSION_STATUSES
    from apps.sessions.exceptions import EntryConflict
    from apps.sessions.models import ParkingSession

    locked_vehicle = Vehicle.objects.select_for_update().get(pk=vehicle.pk)
    changes_protected_state = any(
        field in data and data[field] != getattr(locked_vehicle, field)
        for field in ("registration_number", "vehicle_type")
    ) or (data.get("is_active") is False and locked_vehicle.is_active)
    if (
        changes_protected_state
        and ParkingSession.objects.filter(
            vehicle_id=locked_vehicle.pk,
            status__in=OPEN_SESSION_STATUSES,
        ).exists()
    ):
        raise EntryConflict(
            code="VEHICLE_HAS_OPEN_SESSION",
            detail="An active parking session prevents this vehicle change.",
        )

    fields = []
    for field in ("registration_number", "vehicle_type", "is_active"):
        if field in data:
            setattr(locked_vehicle, field, data[field])
            fields.append(field)
    return _save(locked_vehicle, update_fields=fields) if fields else locked_vehicle
