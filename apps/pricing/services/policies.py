from collections.abc import Mapping

from django.db import IntegrityError, transaction
from django.db.models import Max
from rest_framework.exceptions import NotFound

from apps.parking.models import ParkingLot
from apps.pricing.exceptions import PricingConflict
from apps.pricing.models import PricingPolicy


def _constraint_name(exc: IntegrityError) -> str | None:
    diagnostics = getattr(exc.__cause__, "diag", None)
    return getattr(diagnostics, "constraint_name", None)


def publish_policy(*, data: Mapping, actor) -> PricingPolicy:
    values = dict(data)
    supplied_lot = values.pop("parking_lot")
    try:
        with transaction.atomic():
            parking_lot = ParkingLot.objects.select_for_update().get(pk=supplied_lot.pk)
            if not parking_lot.is_active:
                raise PricingConflict(
                    code="LOT_INACTIVE",
                    detail="Pricing can be published only for an active parking lot.",
                )

            vehicle_type = values["vehicle_type"]
            previous = list(
                PricingPolicy.objects.select_for_update().filter(
                    parking_lot=parking_lot,
                    vehicle_type=vehicle_type,
                    is_active=True,
                )
            )
            max_version = (
                PricingPolicy.objects.filter(
                    parking_lot=parking_lot,
                    vehicle_type=vehicle_type,
                ).aggregate(max_version=Max("version"))["max_version"]
                or 0
            )
            if previous:
                PricingPolicy.objects.filter(pk__in=[item.pk for item in previous]).update(
                    is_active=False
                )
            return PricingPolicy.objects.create(
                parking_lot=parking_lot,
                version=max_version + 1,
                created_by=actor,
                is_active=True,
                **values,
            )
    except IntegrityError as exc:
        if _constraint_name(exc) in {
            "pricing_policy_lot_vehicle_version_unique",
            "pricing_policy_one_active",
        }:
            raise PricingConflict(
                code="PRICING_PUBLICATION_CONFLICT",
                detail="Pricing changed concurrently; retry the publication.",
            ) from exc
        raise


def retire_policy(*, policy_id: int) -> PricingPolicy:
    try:
        lot_id = PricingPolicy.objects.values_list("parking_lot_id", flat=True).get(pk=policy_id)
    except PricingPolicy.DoesNotExist as exc:
        raise NotFound("Pricing policy not found.") from exc

    with transaction.atomic():
        ParkingLot.objects.select_for_update().get(pk=lot_id)
        policy = (
            PricingPolicy.objects.select_for_update()
            .select_related("parking_lot")
            .get(pk=policy_id)
        )
        if policy.is_active:
            policy.is_active = False
            policy.save(update_fields=["is_active"])
        return policy
