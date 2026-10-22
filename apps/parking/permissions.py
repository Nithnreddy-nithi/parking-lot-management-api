from rest_framework.permissions import SAFE_METHODS, BasePermission

from apps.accounts.models import User


class CanReadOrManageParkingConfiguration(BasePermission):
    message = "Administrator or operator access is required."

    def has_permission(self, request, view) -> bool:
        user = request.user
        if not user.is_authenticated or not user.is_active:
            return False
        if user.is_superuser or user.role == User.Role.ADMIN:
            return True
        return request.method in SAFE_METHODS and user.role == User.Role.OPERATOR
