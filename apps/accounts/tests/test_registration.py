import pytest

from apps.accounts.models import User
from apps.accounts.tests.conftest import TEST_PASSWORD

REGISTER_URL = "/api/v1/auth/register/"


@pytest.mark.django_db
def test_registration_creates_customer_with_hashed_password(api_client):
    response = api_client.post(
        REGISTER_URL,
        {
            "username": "new-customer",
            "email": "new@example.com",
            "first_name": "New",
            "last_name": "Customer",
            "password": TEST_PASSWORD,
            "password_confirm": TEST_PASSWORD,
        },
        format="json",
    )

    assert response.status_code == 201
    assert response.data["role"] == User.Role.CUSTOMER
    assert "password" not in response.data
    user = User.objects.get(username="new-customer")
    assert user.check_password(TEST_PASSWORD)
    assert user.password != TEST_PASSWORD


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("overrides", "field"),
    [
        ({"password": "password", "password_confirm": "password"}, "password"),
        ({"password_confirm": "Different!Password-2026"}, "password_confirm"),
    ],
)
def test_registration_rejects_invalid_passwords(api_client, overrides, field):
    payload = {
        "username": "new-customer",
        "password": TEST_PASSWORD,
        "password_confirm": TEST_PASSWORD,
    }
    payload.update(overrides)

    response = api_client.post(REGISTER_URL, payload, format="json")

    assert response.status_code == 400
    assert field in response.data["error"]["fields"]


@pytest.mark.django_db
def test_registration_rejects_duplicate_username(api_client, customer):
    response = api_client.post(
        REGISTER_URL,
        {
            "username": customer.username,
            "password": TEST_PASSWORD,
            "password_confirm": TEST_PASSWORD,
        },
        format="json",
    )

    assert response.status_code == 400
    assert "username" in response.data["error"]["fields"]


@pytest.mark.django_db
@pytest.mark.parametrize("protected_field", ["role", "is_staff", "is_superuser", "is_active"])
def test_registration_rejects_privileged_field_injection(api_client, protected_field):
    response = api_client.post(
        REGISTER_URL,
        {
            "username": f"injection-{protected_field}",
            "password": TEST_PASSWORD,
            "password_confirm": TEST_PASSWORD,
            protected_field: True,
        },
        format="json",
    )

    assert response.status_code == 400
    assert protected_field in response.data["error"]["fields"]
