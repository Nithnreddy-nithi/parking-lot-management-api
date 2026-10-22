import pytest

from apps.parking.enums import GateType, SpotType
from apps.parking.models import Gate
from apps.parking.tests.conftest import authenticate


@pytest.mark.django_db
def test_duplicate_normalized_lot_code_returns_conflict(api_client, app_admin, parking_lot):
    authenticate(api_client, app_admin)
    response = api_client.post(
        "/api/v1/parking-lots/",
        {"code": " lot-a ", "name": "Duplicate", "address": "X"},
        format="json",
    )
    assert response.status_code == 409
    assert response.data["error"]["code"] == "conflict"


@pytest.mark.django_db
@pytest.mark.parametrize("duplicate", ["code", "level"])
def test_floor_scoped_uniqueness_returns_conflict(
    api_client, app_admin, parking_lot, floor, duplicate
):
    authenticate(api_client, app_admin)
    payload = {
        "parking_lot": parking_lot.id,
        "code": floor.code if duplicate == "code" else "B1",
        "name": "Duplicate",
        "level": floor.level if duplicate == "level" else -1,
    }
    response = api_client.post("/api/v1/floors/", payload, format="json")
    assert response.status_code == 409


@pytest.mark.django_db
def test_gate_scoped_uniqueness_returns_conflict(api_client, app_admin, parking_lot):
    Gate.objects.create(
        parking_lot=parking_lot,
        code="ENTRY",
        name="Entry",
        gate_type=GateType.ENTRY,
    )
    authenticate(api_client, app_admin)
    response = api_client.post(
        "/api/v1/gates/",
        {
            "parking_lot": parking_lot.id,
            "code": "entry",
            "name": "Duplicate",
            "gate_type": GateType.BOTH,
        },
        format="json",
    )
    assert response.status_code == 409


@pytest.mark.django_db
def test_spot_scoped_uniqueness_returns_conflict(api_client, app_admin, floor, parking_spot):
    authenticate(api_client, app_admin)
    response = api_client.post(
        "/api/v1/spots/",
        {"floor": floor.id, "number": "g-01", "spot_type": SpotType.LARGE},
        format="json",
    )
    assert response.status_code == 409
