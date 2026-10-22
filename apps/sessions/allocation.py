from typing import Protocol

from apps.parking.enums import SpotType, VehicleType


class AllocationStrategy(Protocol):
    """Defines candidate compatibility and preference; it does not reserve a spot."""

    def spot_type_preferences(self, vehicle_type: str) -> tuple[str, ...]: ...

    def ordering_fields(self) -> tuple[str, ...]: ...


class DeterministicAllocationStrategy:
    """Prefer compatibility, then floor level, spot number, and primary key."""

    _compatibility = {
        VehicleType.MOTORCYCLE: (SpotType.MOTORCYCLE,),
        VehicleType.CAR: (SpotType.COMPACT, SpotType.LARGE),
        VehicleType.TRUCK: (SpotType.LARGE,),
    }

    def spot_type_preferences(self, vehicle_type: str) -> tuple[str, ...]:
        return self._compatibility.get(vehicle_type, ())

    def ordering_fields(self) -> tuple[str, ...]:
        return ("floor__level", "number", "id")
