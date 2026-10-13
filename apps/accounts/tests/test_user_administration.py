import pytest

from apps.accounts.models import User
from apps.accounts.tests.conftest import TEST_PASSWORD, authenticate

USERS_URL = "/api/v1/users/"


@pytest.mark.django_db
@pytest.mark.parametrize("fixture_name", ["customer", "operator"])
def test_non_admin_roles_cannot_manage_users(api_client, request, fixture_name):
    authenticate(api_client, request.getfixturevalue(fixture_name))

    response = api_client.get(USERS_URL)

    assert response.status_code == 403


@pytest.mark.django_db
def test_admin_can_create_customer_or_operator(api_client, app_admin):
    authenticate(api_client, app_admin)

    response = api_client.post(
        USERS_URL,
        {
            "username": "managed-operator",
            "role": User.Role.OPERATOR,
            "password": TEST_PASSWORD,
            "password_confirm": TEST_PASSWORD,
        },
        format="json",
    )

    assert response.status_code == 201
    user = User.objects.get(username="managed-operator")
    assert user.role == User.Role.OPERATOR
    assert user.check_password(TEST_PASSWORD)
    assert not user.is_staff
    assert not user.is_superuser


@pytest.mark.django_db
@pytest.mark.parametrize(
    "field,value", [("role", User.Role.ADMIN), ("is_staff", True), ("is_superuser", True)]
)
def test_admin_api_rejects_privilege_escalation(api_client, app_admin, field, value):
    authenticate(api_client, app_admin)
    payload = {
        "username": f"escalation-{field}",
        "password": TEST_PASSWORD,
        "password_confirm": TEST_PASSWORD,
        field: value,
    }

    response = api_client.post(USERS_URL, payload, format="json")

    assert response.status_code == 400
    assert field in response.data["error"]["fields"]


@pytest.mark.django_db
def test_admin_can_filter_paginated_user_list(api_client, app_admin, customer, operator):
    authenticate(api_client, app_admin)

    response = api_client.get(USERS_URL, {"role": User.Role.OPERATOR, "is_active": "true"})

    assert response.status_code == 200
    assert response.data["count"] == 1
    assert response.data["results"][0]["id"] == operator.id


@pytest.mark.django_db
def test_admin_can_read_and_update_permitted_user(api_client, app_admin, customer):
    authenticate(api_client, app_admin)
    detail_url = f"{USERS_URL}{customer.id}/"

    read = api_client.get(detail_url)
    updated = api_client.patch(
        detail_url,
        {"first_name": "Managed", "role": User.Role.OPERATOR, "is_active": False},
        format="json",
    )

    assert read.status_code == 200
    assert updated.status_code == 200
    customer.refresh_from_db()
    assert customer.first_name == "Managed"
    assert customer.role == User.Role.OPERATOR
    assert customer.is_active is False


@pytest.mark.django_db
@pytest.mark.parametrize("target_kind", ["admin", "superuser"])
def test_admin_and_superuser_targets_are_protected(api_client, app_admin, target_kind):
    authenticate(api_client, app_admin)
    if target_kind == "admin":
        target = User.objects.create_user(
            username="other-admin", password=TEST_PASSWORD, role=User.Role.ADMIN
        )
    else:
        target = User.objects.create_superuser(username="superuser", password=TEST_PASSWORD)

    response = api_client.patch(
        f"{USERS_URL}{target.id}/",
        {"first_name": "Forbidden"},
        format="json",
    )

    assert response.status_code == 400
    target.refresh_from_db()
    assert target.first_name == ""


@pytest.mark.django_db
def test_role_change_applies_to_existing_access_token(api_client, app_admin):
    authenticate(api_client, app_admin)
    app_admin.role = User.Role.OPERATOR
    app_admin.save(update_fields=["role"])

    response = api_client.get(USERS_URL)

    assert response.status_code == 403


@pytest.mark.django_db
def test_deactivation_blocks_existing_access_token(api_client, customer):
    authenticate(api_client, customer)
    customer.is_active = False
    customer.save(update_fields=["is_active"])

    response = api_client.get("/api/v1/users/me/")

    assert response.status_code == 401


@pytest.mark.django_db
def test_missing_user_returns_not_found(api_client, app_admin):
    authenticate(api_client, app_admin)

    response = api_client.get(f"{USERS_URL}999999/")

    assert response.status_code == 404
