import pytest
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import User
from apps.accounts.tests.conftest import TEST_PASSWORD, authenticate

TOKEN_URL = "/api/v1/auth/token/"
REFRESH_URL = "/api/v1/auth/token/refresh/"
LOGOUT_URL = "/api/v1/auth/logout/"
ME_URL = "/api/v1/users/me/"


@pytest.mark.django_db
def test_login_and_authenticated_profile_access(api_client, customer):
    tokens = authenticate(api_client, customer)

    assert tokens["access"]
    assert tokens["refresh"]
    response = api_client.get(ME_URL)
    assert response.status_code == 200
    assert response.data["username"] == customer.username
    assert "password" not in response.data


@pytest.mark.django_db
def test_login_rejects_incorrect_credentials(api_client, customer):
    response = api_client.post(
        TOKEN_URL,
        {"username": customer.username, "password": "incorrect"},
        format="json",
    )

    assert response.status_code == 401


@pytest.mark.django_db
def test_login_rejects_inactive_user(api_client, customer):
    customer.is_active = False
    customer.save(update_fields=["is_active"])

    response = api_client.post(
        TOKEN_URL,
        {"username": customer.username, "password": TEST_PASSWORD},
        format="json",
    )

    assert response.status_code == 401


@pytest.mark.django_db
@pytest.mark.parametrize("authorization", [None, "Bearer invalid-token"])
def test_profile_rejects_missing_or_invalid_access_token(api_client, authorization):
    if authorization:
        api_client.credentials(HTTP_AUTHORIZATION=authorization)

    response = api_client.get(ME_URL)

    assert response.status_code == 401


@pytest.mark.django_db
def test_refresh_rotates_token_and_rejects_replaced_token(api_client, customer):
    tokens = authenticate(api_client, customer)
    original_refresh = tokens["refresh"]
    api_client.credentials()

    rotated = api_client.post(REFRESH_URL, {"refresh": original_refresh}, format="json")
    reused = api_client.post(REFRESH_URL, {"refresh": original_refresh}, format="json")

    assert rotated.status_code == 200
    assert rotated.data["refresh"] != original_refresh
    assert rotated.data["access"]
    assert reused.status_code == 401


@pytest.mark.django_db
def test_logout_blacklists_owned_refresh_token(api_client, customer):
    tokens = authenticate(api_client, customer)

    logout = api_client.post(LOGOUT_URL, {"refresh": tokens["refresh"]}, format="json")
    api_client.credentials()
    refreshed = api_client.post(REFRESH_URL, {"refresh": tokens["refresh"]}, format="json")

    assert logout.status_code == 204
    assert refreshed.status_code == 401


@pytest.mark.django_db
def test_user_cannot_logout_another_users_refresh_token(api_client, customer):
    other = User.objects.create_user(username="other", password=TEST_PASSWORD)
    other_refresh = str(RefreshToken.for_user(other))
    authenticate(api_client, customer)

    response = api_client.post(LOGOUT_URL, {"refresh": other_refresh}, format="json")

    assert response.status_code == 403
    api_client.credentials()
    assert (
        api_client.post(REFRESH_URL, {"refresh": other_refresh}, format="json").status_code == 200
    )
