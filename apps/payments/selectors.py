from django.db.models import QuerySet

from apps.payments.models import PaymentAttempt


def payment_attempts(
    *,
    owner_id: int | None,
    status: str | None = None,
    session_id: int | None = None,
) -> QuerySet[PaymentAttempt]:
    queryset = PaymentAttempt.objects.select_related(
        "quote",
        "quote__parking_session",
        "initiated_by",
    )
    if owner_id is not None:
        queryset = queryset.filter(quote__parking_session__vehicle__owner_id=owner_id)
    if status is not None:
        queryset = queryset.filter(status=status)
    if session_id is not None:
        queryset = queryset.filter(quote__parking_session_id=session_id)
    return queryset.order_by("-created_at", "-id")
