import pytest

from apps.accounts.tests.conftest import TEST_PASSWORD, authenticate

ME_URL = "/api/v1/users/me/"
CHANGE_PASSWORD_URL = "/api/v1/users/me/change-password/"
REFRESH_URL = "/api/v1/auth/token/refresh/"
NEW_PASSWORD = "N3w!Parking-Password-2026"


@pytest.mark.django_db
def test_user_can_update_supported_profile_fields(api_client, customer):
    authenticate(api_client, customer)

    response = api_client.patch(
        ME_URL,
        {"first_name": "Updated", "last_name": "Name"},
        format="json",
    )

    assert response.status_code == 200
    customer.refresh_from_db()
    assert (customer.first_name, customer.last_name) == ("Updated", "Name")


@pytest.mark.django_db
@pytest.mark.parametrize(
    "field", ["username", "email", "password", "role", "is_active", "is_staff"]
)
def test_user_profile_rejects_protected_fields(api_client, customer, field):
    authenticate(api_client, customer)

    response = api_client.patch(ME_URL, {field: "forbidden"}, format="json")

    assert response.status_code == 400
    assert field in response.data["error"]["fields"]


@pytest.mark.django_db
def test_password_change_requires_current_password(api_client, customer):
    authenticate(api_client, customer)

    response = api_client.post(
        CHANGE_PASSWORD_URL,
        {"new_password": NEW_PASSWORD, "new_password_confirm": NEW_PASSWORD},
        format="json",
    )

    assert response.status_code == 400
    assert "current_password" in response.data["error"]["fields"]


@pytest.mark.django_db
def test_password_change_rejects_incorrect_current_password(api_client, customer):
    authenticate(api_client, customer)

    response = api_client.post(
        CHANGE_PASSWORD_URL,
        {
            "current_password": "Incorrect!Password-2026",
            "new_password": NEW_PASSWORD,
            "new_password_confirm": NEW_PASSWORD,
        },
        format="json",
    )

    assert response.status_code == 400
    assert "current_password" in response.data["error"]["fields"]


@pytest.mark.django_db
def test_password_change_rejects_weak_password(api_client, customer):
    authenticate(api_client, customer)

    response = api_client.post(
        CHANGE_PASSWORD_URL,
        {
            "current_password": TEST_PASSWORD,
            "new_password": "password",
            "new_password_confirm": "password",
        },
        format="json",
    )

    assert response.status_code == 400
    assert "new_password" in response.data["error"]["fields"]


@pytest.mark.django_db
def test_password_change_updates_login_and_revokes_outstanding_refresh_tokens(api_client, customer):
    tokens = authenticate(api_client, customer)

    response = api_client.post(
        CHANGE_PASSWORD_URL,
        {
            "current_password": TEST_PASSWORD,
            "new_password": NEW_PASSWORD,
            "new_password_confirm": NEW_PASSWORD,
        },
        format="json",
    )

    assert response.status_code == 204
    customer.refresh_from_db()
    assert customer.check_password(NEW_PASSWORD)
    assert not customer.check_password(TEST_PASSWORD)
    api_client.credentials()
    assert (
        api_client.post(REFRESH_URL, {"refresh": tokens["refresh"]}, format="json").status_code
        == 401
    )
    assert (
        api_client.post(
            "/api/v1/auth/token/",
            {"username": customer.username, "password": TEST_PASSWORD},
            format="json",
        ).status_code
        == 401
    )
