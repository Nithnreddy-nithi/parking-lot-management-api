from datetime import date

from django.db.models import Count, Exists, OuterRef, Q, QuerySet

from apps.parking.enums import SpotOperationalStatus, SpotType
from apps.parking.models import ParkingSpot
from apps.sessions.enums import OPEN_SESSION_STATUSES
from apps.sessions.models import ParkingSession


def session_list(
    *,
    owner_id: int | None,
    status: str | None = None,
    lot_id: int | None = None,
    entry_date_from: date | None = None,
    entry_date_to: date | None = None,
    vehicle_id: int | None = None,
) -> QuerySet[ParkingSession]:
    queryset = ParkingSession.objects.select_related(
        "vehicle",
        "spot",
        "spot__floor",
        "spot__floor__parking_lot",
        "entry_gate",
    )
    if owner_id is not None:
        queryset = queryset.filter(vehicle__owner_id=owner_id)
    if status is not None:
        queryset = queryset.filter(status=status)
    if lot_id is not None:
        queryset = queryset.filter(spot__floor__parking_lot_id=lot_id)
    if entry_date_from is not None:
        queryset = queryset.filter(entered_at__date__gte=entry_date_from)
    if entry_date_to is not None:
        queryset = queryset.filter(entered_at__date__lte=entry_date_to)
    if vehicle_id is not None:
        queryset = queryset.filter(vehicle_id=vehicle_id)
    return queryset.order_by("-entered_at", "-id")


def availability_by_spot_type(*, lot_id: int) -> list[dict]:
    open_sessions = ParkingSession.objects.filter(
        spot_id=OuterRef("pk"),
        status__in=OPEN_SESSION_STATUSES,
    )
    rows = list(
        ParkingSpot.objects.filter(floor__parking_lot_id=lot_id)
        .annotate(has_open_session=Exists(open_sessions))
        .values("spot_type")
        .annotate(
            total=Count("id"),
            operationally_enabled=Count(
                "id",
                filter=Q(operational_status=SpotOperationalStatus.ENABLED),
            ),
            occupied=Count("id", filter=Q(has_open_session=True)),
            available=Count(
                "id",
                filter=Q(
                    operational_status=SpotOperationalStatus.ENABLED,
                    floor__is_active=True,
                    floor__parking_lot__is_active=True,
                    has_open_session=False,
                ),
            ),
        )
        .order_by("spot_type")
    )
    by_type = {row["spot_type"]: row for row in rows}
    return [
        {
            "spot_type": spot_type,
            "total": by_type.get(spot_type, {}).get("total", 0),
            "operationally_enabled": by_type.get(spot_type, {}).get("operationally_enabled", 0),
            "occupied": by_type.get(spot_type, {}).get("occupied", 0),
            "available": by_type.get(spot_type, {}).get("available", 0),
        }
        for spot_type in SpotType.values
    ]
