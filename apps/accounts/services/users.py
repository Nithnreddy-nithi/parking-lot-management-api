from collections.abc import Mapping

from django.db import transaction
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import User


@transaction.atomic
def register_customer(*, data: Mapping) -> User:
    values = dict(data)
    password = values.pop("password")
    user = User(**values, role=User.Role.CUSTOMER)
    user.set_password(password)
    user.save()
    return user


@transaction.atomic
def create_managed_user(*, data: Mapping) -> User:
    values = dict(data)
    password = values.pop("password")
    user = User(**values)
    user.set_password(password)
    user.save()
    return user


@transaction.atomic
def update_profile(*, user: User, data: Mapping) -> User:
    fields = []
    for field in ("first_name", "last_name"):
        if field in data:
            setattr(user, field, data[field])
            fields.append(field)
    if fields:
        user.save(update_fields=[*fields, "updated_at"])
    return user


@transaction.atomic
def update_managed_user(*, user: User, data: Mapping) -> User:
    if user.role == User.Role.ADMIN or user.is_superuser:
        raise ValidationError("Administrator and superuser accounts cannot be modified here.")

    fields = []
    for field in ("first_name", "last_name", "email", "role", "is_active"):
        if field in data:
            setattr(user, field, data[field])
            fields.append(field)
    if fields:
        user.save(update_fields=[*fields, "updated_at"])
    return user


@transaction.atomic
def change_password(*, user: User, new_password: str) -> User:
    user.set_password(new_password)
    user.save(update_fields=["password", "updated_at"])
    revoke_refresh_tokens(user=user)
    return user


def revoke_refresh_tokens(*, user: User) -> None:
    outstanding_tokens = OutstandingToken.objects.filter(user=user)
    for token in outstanding_tokens.iterator():
        BlacklistedToken.objects.get_or_create(token=token)


def blacklist_refresh_token(*, user: User, raw_token: str) -> None:
    try:
        token = RefreshToken(raw_token)
    except TokenError as exc:
        raise ValidationError({"refresh": "Refresh token is invalid or blacklisted."}) from exc

    token_user_id = token.payload.get(api_settings.USER_ID_CLAIM)
    if str(token_user_id) != str(user.pk):
        raise PermissionDenied("The refresh token does not belong to the authenticated user.")

    token.blacklist()
