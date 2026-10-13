import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.accounts.models import User

TEST_PASSWORD = "C0mpl3x!Parking-2026"


@pytest.fixture(autouse=True)
def clear_throttle_cache():
    cache.clear()


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def customer(db):
    return User.objects.create_user(username="customer", password=TEST_PASSWORD)


@pytest.fixture
def operator(db):
    return User.objects.create_user(
        username="operator",
        password=TEST_PASSWORD,
        role=User.Role.OPERATOR,
    )


@pytest.fixture
def app_admin(db):
    return User.objects.create_user(
        username="app-admin",
        password=TEST_PASSWORD,
        role=User.Role.ADMIN,
    )


def authenticate(api_client, user, password=TEST_PASSWORD):
    response = api_client.post(
        "/api/v1/auth/token/",
        {"username": user.username, "password": password},
        format="json",
    )
    assert response.status_code == 200
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")
    return response.data
