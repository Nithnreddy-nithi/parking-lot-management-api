from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.parking.models import ParkingLot
from apps.pricing.models import PricingPolicy, PricingSnapshot
from apps.pricing.services import create_snapshot
from apps.sessions.models import ParkingSession


class Command(BaseCommand):
    help = (
        "Backfill missing session pricing snapshots from one explicitly selected historical policy."
    )

    def add_arguments(self, parser):
        parser.add_argument("--policy-id", type=int, required=True)
        parser.add_argument(
            "--session-id",
            type=int,
            action="append",
            dest="session_ids",
            help="Limit to a session ID; repeat for multiple sessions.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        try:
            policy = PricingPolicy.objects.select_related("parking_lot").get(
                pk=options["policy_id"]
            )
        except PricingPolicy.DoesNotExist as exc:
            raise CommandError("Selected pricing policy does not exist.") from exc

        ParkingLot.objects.select_for_update().get(pk=policy.parking_lot_id)
        sessions = ParkingSession.objects.select_for_update().select_related(
            "spot__floor",
        )
        requested_ids = options.get("session_ids")
        if requested_ids:
            sessions = sessions.filter(pk__in=requested_ids)
            found_ids = set(sessions.values_list("pk", flat=True))
            missing_ids = sorted(set(requested_ids) - found_ids)
            if missing_ids:
                raise CommandError(f"Parking sessions not found: {missing_ids}")
        else:
            sessions = sessions.filter(
                spot__floor__parking_lot_id=policy.parking_lot_id,
                vehicle_type_snapshot=policy.vehicle_type,
            )

        created = 0
        skipped = 0
        for parking_session in sessions.order_by("pk"):
            if PricingSnapshot.objects.filter(parking_session=parking_session).exists():
                skipped += 1
                continue
            if parking_session.spot.floor.parking_lot_id != policy.parking_lot_id:
                raise CommandError(
                    f"Session {parking_session.pk} belongs to a different parking lot."
                )
            if parking_session.vehicle_type_snapshot != policy.vehicle_type:
                raise CommandError(
                    f"Session {parking_session.pk} has a different vehicle type snapshot."
                )
            create_snapshot(parking_session=parking_session, policy=policy)
            created += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Pricing snapshot backfill complete: created={created}, skipped={skipped}."
            )
        )
