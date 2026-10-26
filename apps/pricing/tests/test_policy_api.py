from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.parking.enums import VehicleType
from apps.pricing.models import PricingPolicy
from apps.pricing.tests.conftest import authenticate

POLICIES_URL = "/api/v1/pricing-policies/"


def payload(lot_id, **overrides):
    return {
        "parking_lot": lot_id,
        "vehicle_type": VehicleType.CAR,
        "currency": "INR",
        "hourly_rate": "30.00",
        "grace_minutes": 15,
        "daily_cap": "300.00",
        **overrides,
    }


@pytest.mark.django_db
def test_admin_publishes_server_versioned_policy(api_client, app_admin, parking_lot):
    response = authenticate(api_client, app_admin).post(
        POLICIES_URL,
        payload(parking_lot.pk),
        format="json",
    )
    assert response.status_code == 201
    assert response.data["version"] == 1
    assert response.data["created_by"] == app_admin.pk
    assert response.data["is_active"] is True


@pytest.mark.django_db
@pytest.mark.parametrize("role_fixture", ["operator", "customer"])
def test_non_admin_cannot_manage_pricing(api_client, request, role_fixture, parking_lot):
    user = request.getfixturevalue(role_fixture)
    client = authenticate(api_client, user)
    assert client.get(POLICIES_URL).status_code == 403
    assert client.post(POLICIES_URL, payload(parking_lot.pk), format="json").status_code == 403


@pytest.mark.django_db
def test_publication_atomically_retires_previous_version(api_client, app_admin, parking_lot):
    client = authenticate(api_client, app_admin)
    first = client.post(POLICIES_URL, payload(parking_lot.pk), format="json")
    second = client.post(
        POLICIES_URL,
        payload(parking_lot.pk, hourly_rate="45.00", daily_cap="400.00"),
        format="json",
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert second.data["version"] == 2
    assert second.data["hourly_rate"] == "45.00"
    assert PricingPolicy.objects.get(pk=first.data["id"]).is_active is False
    assert PricingPolicy.objects.get(pk=second.data["id"]).is_active is True


@pytest.mark.django_db
def test_clients_cannot_choose_version_creator_or_active_state(api_client, app_admin, parking_lot):
    response = authenticate(api_client, app_admin).post(
        POLICIES_URL,
        payload(parking_lot.pk, version=99, created_by=999, is_active=False),
        format="json",
    )
    assert response.status_code == 400
    assert set(response.data["error"]["fields"]) == {"created_by", "is_active", "version"}


@pytest.mark.django_db
def test_policy_financial_fields_are_immutable(api_client, app_admin, parking_lot):
    response = authenticate(api_client, app_admin).post(
        POLICIES_URL,
        payload(parking_lot.pk),
        format="json",
    )
    policy = PricingPolicy.objects.get(pk=response.data["id"])
    policy.hourly_rate = Decimal("99.00")
    with pytest.raises(ValidationError):
        policy.save()
    assert (
        api_client.patch(
            f"{POLICIES_URL}{policy.pk}/",
            {"hourly_rate": "99.00"},
            format="json",
        ).status_code
        == 405
    )


@pytest.mark.django_db
def test_retire_is_idempotent_and_does_not_delete(api_client, app_admin, parking_lot):
    client = authenticate(api_client, app_admin)
    created = client.post(POLICIES_URL, payload(parking_lot.pk), format="json")
    url = f"{POLICIES_URL}{created.data['id']}/retire/"
    first = client.post(url, {}, format="json")
    second = client.post(url, {}, format="json")
    assert first.status_code == second.status_code == 200
    assert second.data["is_active"] is False
    assert PricingPolicy.objects.filter(pk=created.data["id"]).exists()


@pytest.mark.django_db
def test_inactive_lot_rejects_publication(api_client, app_admin, parking_lot):
    parking_lot.is_active = False
    parking_lot.save(update_fields=["is_active"])
    response = authenticate(api_client, app_admin).post(
        POLICIES_URL,
        payload(parking_lot.pk),
        format="json",
    )
    assert response.status_code == 409
    assert response.data["error"]["code"] == "LOT_INACTIVE"
    assert not PricingPolicy.objects.exists()


@pytest.mark.django_db
def test_policy_filters_are_strict_and_deterministic(api_client, app_admin, parking_lot):
    client = authenticate(api_client, app_admin)
    client.post(POLICIES_URL, payload(parking_lot.pk), format="json")
    client.post(
        POLICIES_URL,
        payload(parking_lot.pk, hourly_rate="40.00"),
        format="json",
    )
    response = client.get(
        POLICIES_URL,
        {"lot": parking_lot.pk, "vehicle_type": VehicleType.CAR, "is_active": "false"},
    )
    assert response.status_code == 200
    assert [item["version"] for item in response.data["results"]] == [1]
    assert client.get(f"{POLICIES_URL}?unknown=1").status_code == 400


@pytest.mark.django_db(transaction=True)
def test_database_enforces_one_active_policy_and_financial_constraints(app_admin, parking_lot):
    PricingPolicy.objects.create(
        parking_lot=parking_lot,
        vehicle_type=VehicleType.CAR,
        version=1,
        hourly_rate="30.00",
        grace_minutes=0,
        created_by=app_admin,
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        PricingPolicy.objects.create(
            parking_lot=parking_lot,
            vehicle_type=VehicleType.CAR,
            version=2,
            hourly_rate="40.00",
            grace_minutes=0,
            created_by=app_admin,
        )
    with pytest.raises(IntegrityError), transaction.atomic():
        PricingPolicy.objects.create(
            parking_lot=parking_lot,
            vehicle_type=VehicleType.TRUCK,
            version=1,
            hourly_rate="0.00",
            grace_minutes=0,
            created_by=app_admin,
        )
