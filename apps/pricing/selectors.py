from django.db.models import QuerySet

from apps.pricing.models import CheckoutQuote, PricingPolicy


def pricing_policy_list(
    *,
    lot_id: int | None = None,
    vehicle_type: str | None = None,
    is_active: bool | None = None,
) -> QuerySet[PricingPolicy]:
    queryset = PricingPolicy.objects.select_related("parking_lot").order_by(
        "parking_lot_id",
        "vehicle_type",
        "-version",
        "-id",
    )
    if lot_id is not None:
        queryset = queryset.filter(parking_lot_id=lot_id)
    if vehicle_type is not None:
        queryset = queryset.filter(vehicle_type=vehicle_type)
    if is_active is not None:
        queryset = queryset.filter(is_active=is_active)
    return queryset


def quote_for_session(*, session_id: int) -> CheckoutQuote | None:
    return CheckoutQuote.objects.filter(parking_session_id=session_id).first()
