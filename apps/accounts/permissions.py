from rest_framework.permissions import BasePermission

from apps.accounts.models import User


class IsAdminRole(BasePermission):
    message = "Administrator access is required."

    def has_permission(self, request, view) -> bool:
        user = request.user
        return bool(
            user.is_authenticated
            and user.is_active
            and (user.is_superuser or user.role == User.Role.ADMIN)
        )


class IsAdminOrOperatorRole(BasePermission):
    message = "Administrator or operator access is required."

    def has_permission(self, request, view) -> bool:
        user = request.user
        return bool(
            user.is_authenticated
            and user.is_active
            and (user.is_superuser or user.role in {User.Role.ADMIN, User.Role.OPERATOR})
        )
