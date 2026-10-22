import pytest

from apps.parking.enums import GateType, SpotOperationalStatus, SpotType
from apps.parking.models import Floor, Gate, ParkingLot, ParkingSpot
from apps.parking.tests.conftest import authenticate

LOTS_URL = "/api/v1/parking-lots/"
FLOORS_URL = "/api/v1/floors/"
GATES_URL = "/api/v1/gates/"
SPOTS_URL = "/api/v1/spots/"


def lot_payload(**overrides):
    payload = {
        "code": "blr-central",
        "name": "Bengaluru Central",
        "address": "MG Road",
        "timezone": "Asia/Kolkata",
    }
    payload.update(overrides)
    return payload


@pytest.mark.django_db
def test_admin_can_create_and_update_configuration(api_client, app_admin):
    authenticate(api_client, app_admin)

    lot_response = api_client.post(LOTS_URL, lot_payload(), format="json")
    assert lot_response.status_code == 201
    assert lot_response.data["code"] == "BLR-CENTRAL"
    lot_id = lot_response.data["id"]

    floor_response = api_client.post(
        FLOORS_URL,
        {"parking_lot": lot_id, "code": "b1", "name": "Basement", "level": -1},
        format="json",
    )
    assert floor_response.status_code == 201
    assert floor_response.data["code"] == "B1"
    floor_id = floor_response.data["id"]

    gate_response = api_client.post(
        GATES_URL,
        {
            "parking_lot": lot_id,
            "code": "entry-a",
            "name": "Entry A",
            "gate_type": GateType.ENTRY,
        },
        format="json",
    )
    assert gate_response.status_code == 201
    assert gate_response.data["gate_type_display"] == "Entry"

    spot_response = api_client.post(
        SPOTS_URL,
        {"floor": floor_id, "number": "b1-c-01", "spot_type": SpotType.COMPACT},
        format="json",
    )
    assert spot_response.status_code == 201
    assert spot_response.data["number"] == "B1-C-01"

    updated = api_client.patch(
        f"{SPOTS_URL}{spot_response.data['id']}/",
        {"operational_status": SpotOperationalStatus.MAINTENANCE},
        format="json",
    )
    assert updated.status_code == 200
    assert updated.data["operational_status"] == SpotOperationalStatus.MAINTENANCE


@pytest.mark.django_db
def test_operator_has_read_only_configuration_access(api_client, operator, parking_lot):
    authenticate(api_client, operator)

    assert api_client.get(LOTS_URL).status_code == 200
    assert api_client.get(f"{LOTS_URL}{parking_lot.id}/").status_code == 200
    assert api_client.post(LOTS_URL, lot_payload(code="new"), format="json").status_code == 403
    assert (
        api_client.patch(
            f"{LOTS_URL}{parking_lot.id}/", {"name": "Forbidden"}, format="json"
        ).status_code
        == 403
    )


@pytest.mark.django_db
def test_customer_cannot_access_configuration(api_client, customer):
    authenticate(api_client, customer)
    assert api_client.get(LOTS_URL).status_code == 403


@pytest.mark.django_db
def test_unauthenticated_configuration_access_is_denied(api_client):
    assert api_client.get(LOTS_URL).status_code == 401


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("url", "payload", "field"),
    [
        (
            GATES_URL,
            {"parking_lot": 1, "code": "G1", "name": "Gate", "gate_type": "SIDE"},
            "gate_type",
        ),
        (SPOTS_URL, {"floor": 1, "number": "1", "spot_type": "TINY"}, "spot_type"),
        (
            SPOTS_URL,
            {"floor": 1, "number": "1", "spot_type": "COMPACT", "operational_status": "OCCUPIED"},
            "operational_status",
        ),
    ],
)
def test_invalid_configuration_enums_are_rejected(api_client, app_admin, url, payload, field):
    authenticate(api_client, app_admin)
    response = api_client.post(url, payload, format="json")
    assert response.status_code == 400
    assert field in response.data["error"]["fields"]


@pytest.mark.django_db
def test_invalid_timezone_is_rejected(api_client, app_admin):
    authenticate(api_client, app_admin)
    response = api_client.post(
        LOTS_URL,
        lot_payload(timezone="Mars/Olympus_Mons"),
        format="json",
    )
    assert response.status_code == 400
    assert "timezone" in response.data["error"]["fields"]


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("resource", "protected_field", "value"),
    [("floor", "parking_lot", 999), ("gate", "parking_lot", 999), ("spot", "floor", 999)],
)
def test_parent_reassignment_is_rejected(
    api_client, app_admin, parking_lot, floor, parking_spot, resource, protected_field, value
):
    gate = Gate.objects.create(
        parking_lot=parking_lot,
        code="E1",
        name="Entry",
        gate_type=GateType.ENTRY,
    )
    targets = {
        "floor": (FLOORS_URL, floor.id),
        "gate": (GATES_URL, gate.id),
        "spot": (SPOTS_URL, parking_spot.id),
    }
    base_url, object_id = targets[resource]
    authenticate(api_client, app_admin)

    response = api_client.patch(
        f"{base_url}{object_id}/",
        {protected_field: value},
        format="json",
    )
    assert response.status_code == 400
    assert protected_field in response.data["error"]["fields"]


@pytest.mark.django_db
def test_inactive_parent_blocks_new_children(api_client, app_admin, parking_lot, floor):
    authenticate(api_client, app_admin)
    parking_lot.is_active = False
    parking_lot.save(update_fields=["is_active", "updated_at"])

    floor_response = api_client.post(
        FLOORS_URL,
        {"parking_lot": parking_lot.id, "code": "B1", "name": "B1", "level": -1},
        format="json",
    )
    gate_response = api_client.post(
        GATES_URL,
        {
            "parking_lot": parking_lot.id,
            "code": "X1",
            "name": "Exit",
            "gate_type": GateType.EXIT,
        },
        format="json",
    )
    spot_response = api_client.post(
        SPOTS_URL,
        {"floor": floor.id, "number": "G-02", "spot_type": SpotType.COMPACT},
        format="json",
    )

    assert floor_response.status_code == 400
    assert gate_response.status_code == 400
    assert spot_response.status_code == 400


@pytest.mark.django_db
def test_inactive_floor_blocks_new_spot(api_client, app_admin, floor):
    authenticate(api_client, app_admin)
    floor.is_active = False
    floor.save(update_fields=["is_active", "updated_at"])
    response = api_client.post(
        SPOTS_URL,
        {"floor": floor.id, "number": "G-02", "spot_type": SpotType.COMPACT},
        format="json",
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_parent_deactivation_preserves_children_but_makes_them_effectively_unavailable(
    api_client, operator, parking_lot, floor, parking_spot
):
    parking_lot.is_active = False
    parking_lot.save(update_fields=["is_active", "updated_at"])
    authenticate(api_client, operator)

    floor_response = api_client.get(f"{FLOORS_URL}{floor.id}/")
    spot_response = api_client.get(f"{SPOTS_URL}{parking_spot.id}/")

    assert floor_response.data["is_effectively_active"] is False
    assert spot_response.data["is_effectively_available"] is False
    assert Floor.objects.filter(pk=floor.id).exists()
    assert ParkingSpot.objects.filter(pk=parking_spot.id).exists()


@pytest.mark.django_db
def test_lists_are_paginated_and_filters_are_validated(api_client, operator, parking_lot):
    ParkingLot.objects.create(code="LOT-B", name="Second", address="B", is_active=False)
    authenticate(api_client, operator)

    filtered = api_client.get(LOTS_URL, {"is_active": "false", "search": "second", "page_size": 1})
    invalid = api_client.get(SPOTS_URL, {"operational_status": "OCCUPIED"})
    unknown = api_client.get(LOTS_URL, {"unrecognized_filter": "value"})

    assert filtered.status_code == 200
    assert filtered.data["count"] == 1
    assert len(filtered.data["results"]) == 1
    assert invalid.status_code == 400
    assert unknown.status_code == 400


@pytest.mark.django_db
@pytest.mark.parametrize("url", [LOTS_URL, FLOORS_URL, GATES_URL, SPOTS_URL])
def test_configuration_delete_is_not_exposed(api_client, app_admin, url):
    authenticate(api_client, app_admin)
    assert api_client.delete(f"{url}1/").status_code == 405


@pytest.mark.django_db
def test_spot_list_has_bounded_queries(api_client, operator, floor, django_assert_num_queries):
    ParkingSpot.objects.bulk_create(
        [
            ParkingSpot(floor=floor, number=f"G-{number}", spot_type=SpotType.COMPACT)
            for number in range(10, 15)
        ]
    )
    authenticate(api_client, operator)

    with django_assert_num_queries(2):
        response = api_client.get(SPOTS_URL)

    assert response.status_code == 200
    assert response.data["count"] == 5
