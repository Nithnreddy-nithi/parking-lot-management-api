import pytest

from apps.parking.enums import VehicleType
from apps.parking.models import Vehicle
from apps.parking.tests.conftest import authenticate

VEHICLES_URL = "/api/v1/vehicles/"


@pytest.mark.django_db
def test_vehicle_owner_is_authenticated_user_and_registration_is_normalized(api_client, customer):
    authenticate(api_client, customer)
    response = api_client.post(
        VEHICLES_URL,
        {"registration_number": "ka-01 ab 1234", "vehicle_type": VehicleType.CAR},
        format="json",
    )
    assert response.status_code == 201
    assert response.data["owner"] == customer.id
    assert response.data["registration_number"] == "KA01AB1234"
    assert Vehicle.objects.get(pk=response.data["id"]).owner == customer


@pytest.mark.django_db
def test_vehicle_owner_injection_is_rejected(api_client, customer, other_customer):
    authenticate(api_client, customer)
    response = api_client.post(
        VEHICLES_URL,
        {
            "owner": other_customer.id,
            "registration_number": "KA01AB1234",
            "vehicle_type": VehicleType.CAR,
        },
        format="json",
    )
    assert response.status_code == 400
    assert "owner" in response.data["error"]["fields"]


@pytest.mark.django_db
def test_duplicate_normalized_registration_returns_conflict(api_client, customer, other_customer):
    Vehicle.objects.create(
        owner=other_customer,
        registration_number="KA01AB1234",
        vehicle_type=VehicleType.CAR,
    )
    authenticate(api_client, customer)
    response = api_client.post(
        VEHICLES_URL,
        {"registration_number": "ka-01 ab-1234", "vehicle_type": VehicleType.CAR},
        format="json",
    )
    assert response.status_code == 409
    assert response.data["error"]["code"] == "conflict"


@pytest.mark.django_db
def test_vehicle_list_detail_and_update_are_owner_scoped(api_client, customer, other_customer):
    owned = Vehicle.objects.create(
        owner=customer,
        registration_number="KA01AA0001",
        vehicle_type=VehicleType.CAR,
    )
    hidden = Vehicle.objects.create(
        owner=other_customer,
        registration_number="KA01AA0002",
        vehicle_type=VehicleType.MOTORCYCLE,
    )
    authenticate(api_client, customer)
    assert Vehicle.objects.filter(owner=customer).count() == 1

    listing = api_client.get(VEHICLES_URL)
    assert listing.status_code == 200
    assert listing.data["count"] == 1
    assert [item["id"] for item in listing.data["results"]] == [owned.id]

    hidden_detail = api_client.get(f"{VEHICLES_URL}{hidden.id}/")
    hidden_update = api_client.patch(
        f"{VEHICLES_URL}{hidden.id}/", {"is_active": False}, format="json"
    )
    owned_update = api_client.patch(
        f"{VEHICLES_URL}{owned.id}/",
        {"vehicle_type": VehicleType.TRUCK, "is_active": False},
        format="json",
    )

    assert hidden_detail.status_code == 404
    assert hidden_update.status_code == 404
    assert owned_update.status_code == 200
    assert owned_update.data["vehicle_type"] == VehicleType.TRUCK


@pytest.mark.django_db
def test_operator_and_admin_do_not_receive_arbitrary_vehicle_access(
    api_client, operator, app_admin, customer
):
    vehicle = Vehicle.objects.create(
        owner=customer,
        registration_number="KA01AA0003",
        vehicle_type=VehicleType.CAR,
    )
    for user in (operator, app_admin):
        authenticate(api_client, user)
        assert api_client.get(VEHICLES_URL).data["count"] == 0
        assert api_client.get(f"{VEHICLES_URL}{vehicle.id}/").status_code == 404


@pytest.mark.django_db
def test_vehicle_update_rejects_owner_and_unsupported_fields(api_client, customer, other_customer):
    vehicle = Vehicle.objects.create(
        owner=customer,
        registration_number="KA01AA0004",
        vehicle_type=VehicleType.CAR,
    )
    authenticate(api_client, customer)
    response = api_client.patch(
        f"{VEHICLES_URL}{vehicle.id}/",
        {"owner": other_customer.id},
        format="json",
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_vehicle_filter_validation_pagination_and_delete(api_client, customer):
    Vehicle.objects.create(
        owner=customer,
        registration_number="KA01AA0005",
        vehicle_type=VehicleType.CAR,
        is_active=False,
    )
    authenticate(api_client, customer)
    filtered = api_client.get(VEHICLES_URL, {"is_active": "false", "page_size": 1})
    invalid = api_client.get(VEHICLES_URL, {"is_active": "not-a-boolean"})
    deleted = api_client.delete(f"{VEHICLES_URL}1/")
    assert filtered.status_code == 200
    assert filtered.data["count"] == 1
    assert invalid.status_code == 400
    assert deleted.status_code == 405
