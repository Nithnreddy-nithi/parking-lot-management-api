from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier

import pytest
from django import db
from django.db import close_old_connections
from rest_framework.exceptions import APIException

from apps.accounts.models import User
from apps.parking.enums import GateType, SpotType, VehicleType
from apps.parking.models import Floor, Gate, ParkingLot, ParkingSpot, Vehicle
from apps.parking.services.configuration import update_parking_spot
from apps.pricing.calculators import resolve_calculator
from apps.pricing.models import CheckoutQuote, PricingPolicy
from apps.sessions.models import ParkingSession
from apps.sessions.services import CheckoutService, build_entry_service

pytestmark = pytest.mark.django_db(transaction=True)


def _run_workers(*workers):
    barrier = Barrier(len(workers))

    def run(worker):
        close_old_connections()
        try:
            barrier.wait(timeout=5)
            return worker()
        except APIException as exc:
            code = (
                exc.detail.get("code", exc.default_code) if isinstance(exc.detail, dict) else None
            )
            return ("conflict", str(code))
        except Exception as exc:  # captured explicitly and asserted by each test
            return ("worker_error", type(exc).__name__, str(exc))
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=len(workers)) as executor:
        futures = [executor.submit(run, worker) for worker in workers]
        return [future.result(timeout=15) for future in futures]


def _entry_worker(*, vehicle_id, gate_id, actor_id):
    def worker():
        actor = User.objects.get(pk=actor_id)
        session = build_entry_service().enter(
            vehicle_id=vehicle_id,
            entry_gate_id=gate_id,
            actor=actor,
        )
        return ("created", session.pk)

    return worker


@pytest.fixture
def concurrent_setup():
    operator = User.objects.create_user(
        username="concurrent-operator",
        role=User.Role.OPERATOR,
    )
    customer = User.objects.create_user(username="concurrent-customer")
    lot = ParkingLot.objects.create(code="CONCURRENT", name="Concurrent", address="Address")
    floor = Floor.objects.create(parking_lot=lot, code="G", name="Ground", level=0)
    gate = Gate.objects.create(
        parking_lot=lot,
        code="IN",
        name="Entry",
        gate_type=GateType.ENTRY,
    )
    spot = ParkingSpot.objects.create(floor=floor, number="C-1", spot_type=SpotType.COMPACT)
    PricingPolicy.objects.create(
        parking_lot=lot,
        vehicle_type=VehicleType.CAR,
        version=1,
        hourly_rate="30.00",
        grace_minutes=15,
        daily_cap="300.00",
        created_by=operator,
    )
    return operator, customer, lot, floor, gate, spot


def test_two_vehicles_competing_for_one_spot_create_one_session(concurrent_setup):
    operator, customer, _lot, _floor, gate, spot = concurrent_setup
    first = Vehicle.objects.create(
        owner=customer, registration_number="RACE1", vehicle_type=VehicleType.CAR
    )
    second = Vehicle.objects.create(
        owner=customer, registration_number="RACE2", vehicle_type=VehicleType.CAR
    )

    results = _run_workers(
        _entry_worker(vehicle_id=first.pk, gate_id=gate.pk, actor_id=operator.pk),
        _entry_worker(vehicle_id=second.pk, gate_id=gate.pk, actor_id=operator.pk),
    )

    assert not [result for result in results if result[0] == "worker_error"]
    assert sorted(result[0] for result in results) == ["conflict", "created"]
    assert ParkingSession.objects.filter(spot=spot).count() == 1


def test_two_requests_for_same_vehicle_create_one_open_session(concurrent_setup):
    operator, customer, _lot, floor, gate, _spot = concurrent_setup
    ParkingSpot.objects.create(floor=floor, number="C-2", spot_type=SpotType.COMPACT)
    vehicle = Vehicle.objects.create(
        owner=customer, registration_number="SAMERACE", vehicle_type=VehicleType.CAR
    )

    worker = _entry_worker(vehicle_id=vehicle.pk, gate_id=gate.pk, actor_id=operator.pk)
    results = _run_workers(worker, worker)

    assert not [result for result in results if result[0] == "worker_error"]
    assert sorted(result[0] for result in results) == ["conflict", "created"]
    assert ParkingSession.objects.filter(vehicle=vehicle).count() == 1


def test_same_vehicle_cannot_enter_two_lots_simultaneously(concurrent_setup):
    operator, customer, _lot, _floor, first_gate, _spot = concurrent_setup
    second_lot = ParkingLot.objects.create(code="SECOND", name="Second", address="Address")
    second_floor = Floor.objects.create(parking_lot=second_lot, code="G", name="Ground", level=0)
    second_gate = Gate.objects.create(
        parking_lot=second_lot,
        code="IN",
        name="Entry",
        gate_type=GateType.ENTRY,
    )
    ParkingSpot.objects.create(floor=second_floor, number="C-1", spot_type=SpotType.COMPACT)
    PricingPolicy.objects.create(
        parking_lot=second_lot,
        vehicle_type=VehicleType.CAR,
        version=1,
        hourly_rate="30.00",
        grace_minutes=15,
        daily_cap="300.00",
        created_by=operator,
    )
    vehicle = Vehicle.objects.create(
        owner=customer, registration_number="CROSSLOT", vehicle_type=VehicleType.CAR
    )

    results = _run_workers(
        _entry_worker(vehicle_id=vehicle.pk, gate_id=first_gate.pk, actor_id=operator.pk),
        _entry_worker(vehicle_id=vehicle.pk, gate_id=second_gate.pk, actor_id=operator.pk),
    )

    assert not [result for result in results if result[0] == "worker_error"]
    assert sorted(result[0] for result in results) == ["conflict", "created"]
    assert ParkingSession.objects.filter(vehicle=vehicle).count() == 1


def test_spot_type_mutation_racing_entry_preserves_invariants(concurrent_setup):
    operator, customer, _lot, _floor, gate, spot = concurrent_setup
    vehicle = Vehicle.objects.create(
        owner=customer, registration_number="MUTATIONRACE", vehicle_type=VehicleType.CAR
    )

    def mutate():
        candidate = ParkingSpot.objects.select_related("floor__parking_lot").get(pk=spot.pk)
        updated = update_parking_spot(
            parking_spot=candidate,
            data={"spot_type": SpotType.MOTORCYCLE},
        )
        return ("mutated", updated.pk)

    results = _run_workers(
        _entry_worker(vehicle_id=vehicle.pk, gate_id=gate.pk, actor_id=operator.pk),
        mutate,
    )

    assert not [result for result in results if result[0] == "worker_error"]
    spot.refresh_from_db()
    sessions = ParkingSession.objects.filter(vehicle=vehicle)
    if sessions.exists():
        assert spot.spot_type == SpotType.COMPACT
        assert any(result[0] == "conflict" for result in results)
    else:
        assert spot.spot_type == SpotType.MOTORCYCLE
        assert any(result[0] == "conflict" for result in results)
    assert db.connections["default"].in_atomic_block is False


def test_concurrent_checkout_returns_one_persisted_quote(concurrent_setup):
    operator, customer, _lot, _floor, gate, _spot = concurrent_setup
    vehicle = Vehicle.objects.create(
        owner=customer,
        registration_number="CHECKOUTRACE",
        vehicle_type=VehicleType.CAR,
    )
    session = build_entry_service().enter(
        vehicle_id=vehicle.pk,
        entry_gate_id=gate.pk,
        actor=operator,
    )
    calculated_until = datetime(2026, 2, 2, tzinfo=UTC)
    ParkingSession.objects.filter(pk=session.pk).update(
        entered_at=calculated_until - timedelta(hours=2)
    )

    def checkout_worker():
        actor = User.objects.get(pk=operator.pk)
        quote = CheckoutService(
            calculator_resolver=resolve_calculator,
            clock=lambda: calculated_until,
        ).checkout(session_id=session.pk, actor=actor)
        return ("quoted", quote.pk)

    results = _run_workers(checkout_worker, checkout_worker)

    assert not [result for result in results if result[0] == "worker_error"]
    assert [result[0] for result in results] == ["quoted", "quoted"]
    assert len({result[1] for result in results}) == 1
    assert CheckoutQuote.objects.filter(parking_session=session).count() == 1
