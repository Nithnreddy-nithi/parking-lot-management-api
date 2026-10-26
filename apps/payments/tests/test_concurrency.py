from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier

import pytest
from django.db import close_old_connections
from django.test import override_settings
from django.utils import timezone
from rest_framework.exceptions import APIException

from apps.accounts.models import User
from apps.payments.composition import build_payment_initiation_service
from apps.payments.enums import PaymentStatus, SimulationScenario
from apps.payments.models import PaymentAttempt, Settlement
from apps.sessions.models import ParkingSession
from apps.sessions.services.exit import ExitService

pytestmark = pytest.mark.django_db(transaction=True)


def run_workers(*workers):
    barrier = Barrier(len(workers))

    def run(worker):
        close_old_connections()
        try:
            barrier.wait(timeout=5)
            return worker()
        except APIException as exc:
            return ("api_error", str(exc.detail))
        except Exception as exc:  # worker failures are returned and explicitly asserted
            return ("worker_error", type(exc).__name__, str(exc))
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=len(workers)) as executor:
        futures = [executor.submit(run, worker) for worker in workers]
        return [future.result(timeout=15) for future in futures]


@override_settings(SIMULATED_PAYMENT_SCENARIO=SimulationScenario.PENDING)
def test_concurrent_initiation_creates_one_pending_attempt(payment_context, operator):
    def worker():
        actor = User.objects.get(pk=operator.pk)
        attempt = build_payment_initiation_service().initiate(
            session_id=payment_context["session"].pk,
            actor=actor,
        )
        return ("attempt", str(attempt.pk))

    results = run_workers(worker, worker)

    assert not [result for result in results if result[0] == "worker_error"]
    assert [result[0] for result in results] == ["attempt", "attempt"]
    assert len({result[1] for result in results}) == 1
    assert (
        PaymentAttempt.objects.filter(
            quote=payment_context["quote"],
            status=PaymentStatus.PENDING,
        ).count()
        == 1
    )


def test_concurrent_exits_close_once_and_preserve_metadata(payment_context, operator):
    build_payment_initiation_service().initiate(
        session_id=payment_context["session"].pk,
        actor=operator,
    )
    first_time = timezone.now()
    second_time = first_time + timedelta(minutes=1)

    def worker(exit_time):
        def execute():
            actor = User.objects.get(pk=operator.pk)
            session = ExitService(clock=lambda: exit_time).exit(
                session_id=payment_context["session"].pk,
                exit_gate_id=payment_context["exit_gate"].pk,
                actor=actor,
            )
            return ("closed", session.closed_at.isoformat())

        return execute

    results = run_workers(worker(first_time), worker(second_time))

    assert not [result for result in results if result[0] == "worker_error"]
    assert [result[0] for result in results] == ["closed", "closed"]
    assert len({result[1] for result in results}) == 1
    session = ParkingSession.objects.get(pk=payment_context["session"].pk)
    assert session.status == "CLOSED"
    assert session.closed_at in {first_time, second_time}
    assert Settlement.objects.filter(quote=payment_context["quote"]).count() == 1
