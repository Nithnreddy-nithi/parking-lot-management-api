from django.db.models import Q, QuerySet

from apps.parking.models import Floor, Gate, ParkingLot, ParkingSpot, Vehicle


def parking_lot_list(*, is_active: bool | None = None, search: str = "") -> QuerySet[ParkingLot]:
    queryset = ParkingLot.objects.order_by("id")
    if is_active is not None:
        queryset = queryset.filter(is_active=is_active)
    if search:
        queryset = queryset.filter(Q(code__icontains=search) | Q(name__icontains=search))
    return queryset


def floor_list(*, parking_lot: int | None = None, is_active: bool | None = None) -> QuerySet[Floor]:
    queryset = Floor.objects.select_related("parking_lot").order_by("id")
    if parking_lot is not None:
        queryset = queryset.filter(parking_lot_id=parking_lot)
    if is_active is not None:
        queryset = queryset.filter(is_active=is_active)
    return queryset


def gate_list(
    *,
    parking_lot: int | None = None,
    gate_type: str | None = None,
    is_active: bool | None = None,
) -> QuerySet[Gate]:
    queryset = Gate.objects.select_related("parking_lot").order_by("id")
    if parking_lot is not None:
        queryset = queryset.filter(parking_lot_id=parking_lot)
    if gate_type is not None:
        queryset = queryset.filter(gate_type=gate_type)
    if is_active is not None:
        queryset = queryset.filter(is_active=is_active)
    return queryset


def parking_spot_list(
    *,
    floor: int | None = None,
    parking_lot: int | None = None,
    spot_type: str | None = None,
    operational_status: str | None = None,
) -> QuerySet[ParkingSpot]:
    queryset = ParkingSpot.objects.select_related("floor", "floor__parking_lot").order_by("id")
    if floor is not None:
        queryset = queryset.filter(floor_id=floor)
    if parking_lot is not None:
        queryset = queryset.filter(floor__parking_lot_id=parking_lot)
    if spot_type is not None:
        queryset = queryset.filter(spot_type=spot_type)
    if operational_status is not None:
        queryset = queryset.filter(operational_status=operational_status)
    return queryset


def vehicle_list(*, owner_id: int, is_active: bool | None = None) -> QuerySet[Vehicle]:
    queryset = Vehicle.objects.filter(owner_id=owner_id).select_related("owner").order_by("id")
    if is_active is not None:
        queryset = queryset.filter(is_active=is_active)
    return queryset
