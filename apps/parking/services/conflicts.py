from django.db import IntegrityError

from config.api.exceptions import Conflict

CONFLICT_MESSAGES = {
    "parking_lot_code_unique": "A parking lot with this code already exists.",
    "floor_lot_code_unique": "This floor code already exists in the parking lot.",
    "floor_lot_level_unique": "This floor level already exists in the parking lot.",
    "gate_lot_code_unique": "This gate code already exists in the parking lot.",
    "spot_floor_number_unique": "This spot number already exists on the floor.",
    "vehicle_registration_unique": "A vehicle with this registration number already exists.",
}


def translate_integrity_error(exc: IntegrityError) -> None:
    cause = exc.__cause__
    diagnostic = getattr(cause, "diag", None)
    constraint_name = getattr(diagnostic, "constraint_name", None)
    if constraint_name in CONFLICT_MESSAGES:
        raise Conflict(CONFLICT_MESSAGES[constraint_name]) from exc
    raise exc
