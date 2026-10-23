from config.api.exceptions import Conflict


class EntryConflict(Conflict):
    def __init__(self, *, code: str, detail: str):
        super().__init__({"code": code, "detail": detail})


class ExitConflict(Conflict):
    def __init__(self, *, code: str, detail: str):
        super().__init__({"code": code, "detail": detail})


def vehicle_already_parked() -> EntryConflict:
    return EntryConflict(
        code="VEHICLE_ALREADY_PARKED",
        detail="The vehicle already has an open parking session.",
    )
