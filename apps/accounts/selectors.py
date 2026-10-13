from django.db.models import QuerySet

from apps.accounts.models import User


def user_list(*, role: str | None = None, is_active: bool | None = None) -> QuerySet[User]:
    queryset = User.objects.order_by("id")
    if role is not None:
        queryset = queryset.filter(role=role)
    if is_active is not None:
        queryset = queryset.filter(is_active=is_active)
    return queryset
