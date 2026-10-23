from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction

from apps.parking.enums import GateType, SpotOperationalStatus, SpotType, VehicleType
from apps.parking.models import Gate, ParkingLot
from apps.payments.tests.conftest import authenticate
from apps.pricing.models import PricingPolicy
from apps.sessions.enums import SessionStatus
from apps.sessions.models import ParkingSession
from apps.sessions.selectors import availability_by_spot_type
from apps.sessions.services import build_entry_service


def pay(client, session):
    return client.post(
        "/api/v1/payments/",
        {"parking_session_id": session.pk},
        format="json",
    )


def exit_session(client, session, gate):
    return client.post(
        f"/api/v1/parking-sessions/{session.pk}/exit/",
        {"exit_gate_id": gate.pk},
        format="json",
    )


@pytest.mark.django_db
def test_exit_before_settlement_is_rejected(api_client, operator, payment_context):
    response = exit_session(
        authenticate(api_client, operator),
        payment_context["session"],
        payment_context["exit_gate"],
    )
    assert response.status_code == 409
    assert response.data["error"]["code"] == "SESSION_NOT_SETTLED"


@pytest.mark.django_db
def test_paid_remains_occupied_then_exit_closes_and_releases(api_client, operator, payment_context):
    client = authenticate(api_client, operator)
    assert pay(client, payment_context["session"]).status_code == 200
    before = availability_by_spot_type(lot_id=payment_context["lot"].pk)
    assert next(row for row in before if row["spot_type"] == SpotType.COMPACT)["occupied"] == 1

    response = exit_session(client, payment_context["session"], payment_context["exit_gate"])
    assert response.status_code == 200
    assert response.data["status"] == SessionStatus.CLOSED
    assert response.data["exit_gate_id"] == payment_context["exit_gate"].pk
    assert response.data["exited_by"] == operator.pk
    assert response.data["closed_at"] is not None
    after = availability_by_spot_type(lot_id=payment_context["lot"].pk)
    compact = next(row for row in after if row["spot_type"] == SpotType.COMPACT)
    assert compact["occupied"] == 0
    assert compact["available"] == 1


@pytest.mark.django_db
def test_exit_rejects_wrong_lot_inactive_and_entry_only_gates(
    api_client, operator, payment_context
):
    client = authenticate(api_client, operator)
    pay(client, payment_context["session"])
    other_lot = ParkingLot.objects.create(code="OTHER", name="Other", address="Address")
    wrong_lot = Gate.objects.create(
        parking_lot=other_lot,
        code="OUT",
        name="Wrong lot",
        gate_type=GateType.EXIT,
    )
    inactive = Gate.objects.create(
        parking_lot=payment_context["lot"],
        code="OFF",
        name="Inactive",
        gate_type=GateType.EXIT,
        is_active=False,
    )

    cases = (
        (wrong_lot, "EXIT_GATE_LOT_MISMATCH"),
        (inactive, "EXIT_GATE_INACTIVE"),
        (payment_context["entry_gate"], "GATE_NOT_EXIT_CAPABLE"),
    )
    for gate, code in cases:
        response = exit_session(client, payment_context["session"], gate)
        assert response.status_code == 409
        assert response.data["error"]["code"] == code


@pytest.mark.django_db
def test_inactive_lot_floor_and_maintenance_spot_do_not_trap_vehicle(
    api_client, operator, payment_context
):
    client = authenticate(api_client, operator)
    pay(client, payment_context["session"])
    payment_context["lot"].is_active = False
    payment_context["lot"].save(update_fields=["is_active"])
    payment_context["floor"].is_active = False
    payment_context["floor"].save(update_fields=["is_active"])
    payment_context["spot"].operational_status = SpotOperationalStatus.MAINTENANCE
    payment_context["spot"].save(update_fields=["operational_status"])

    response = exit_session(client, payment_context["session"], payment_context["exit_gate"])
    assert response.status_code == 200
    payment_context["spot"].refresh_from_db()
    assert payment_context["spot"].operational_status == SpotOperationalStatus.MAINTENANCE


@pytest.mark.django_db
def test_repeated_exit_preserves_metadata_and_different_gate_conflicts(
    api_client, operator, payment_context
):
    client = authenticate(api_client, operator)
    pay(client, payment_context["session"])
    first = exit_session(client, payment_context["session"], payment_context["exit_gate"])
    second = exit_session(client, payment_context["session"], payment_context["exit_gate"])
    another = Gate.objects.create(
        parking_lot=payment_context["lot"],
        code="OUT2",
        name="Second exit",
        gate_type=GateType.EXIT,
    )
    conflict = exit_session(client, payment_context["session"], another)

    assert first.status_code == second.status_code == 200
    assert first.data["closed_at"] == second.data["closed_at"]
    assert first.data["exited_by"] == second.data["exited_by"] == operator.pk
    assert conflict.status_code == 409
    assert conflict.data["error"]["code"] == "EXIT_ALREADY_RECORDED"


@pytest.mark.django_db
def test_exit_requires_staff(api_client, customer, payment_context):
    response = exit_session(
        authenticate(api_client, customer),
        payment_context["session"],
        payment_context["exit_gate"],
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_released_spot_and_vehicle_can_be_allocated_again(api_client, operator, payment_context):
    client = authenticate(api_client, operator)
    pay(client, payment_context["session"])
    exit_session(client, payment_context["session"], payment_context["exit_gate"])
    PricingPolicy.objects.create(
        parking_lot=payment_context["lot"],
        vehicle_type=VehicleType.CAR,
        version=1,
        hourly_rate=Decimal("30.00"),
        grace_minutes=15,
        daily_cap=Decimal("300.00"),
        created_by=operator,
    )

    new_session = build_entry_service().enter(
        vehicle_id=payment_context["vehicle"].pk,
        entry_gate_id=payment_context["entry_gate"].pk,
        actor=operator,
    )
    assert new_session.spot_id == payment_context["spot"].pk
    assert new_session.status == SessionStatus.ACTIVE


@pytest.mark.django_db(transaction=True)
def test_session_exit_metadata_database_constraint(operator, payment_context):
    with pytest.raises(IntegrityError), transaction.atomic():
        ParkingSession.objects.filter(pk=payment_context["session"].pk).update(
            status=SessionStatus.CLOSED,
            closed_at=None,
            exit_gate=payment_context["exit_gate"],
            exited_by=operator,
        )
