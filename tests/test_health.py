from django.urls import reverse
from rest_framework import status


def test_live_health_endpoint_returns_expected_json(client):
    response = client.get(reverse("health-live"))

    assert response.status_code == status.HTTP_200_OK
    assert response.headers["Content-Type"].startswith("application/json")
    assert response.json() == {"status": "ok"}


def test_live_health_endpoint_rejects_post(client):
    response = client.post(reverse("health-live"))

    assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED
