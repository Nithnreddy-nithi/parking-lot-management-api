from apps.pricing.enums import CalculatorVersion
from apps.pricing.models import PricingPolicy, PricingSnapshot


def get_active_policy_for_entry(*, lot_id: int, vehicle_type: str) -> PricingPolicy | None:
    return (
        PricingPolicy.objects.select_for_update()
        .filter(
            parking_lot_id=lot_id,
            vehicle_type=vehicle_type,
            is_active=True,
        )
        .first()
    )


def create_snapshot(*, parking_session, policy: PricingPolicy) -> PricingSnapshot:
    return PricingSnapshot.objects.create(
        parking_session=parking_session,
        pricing_policy=policy,
        policy_version=policy.version,
        currency=policy.currency,
        hourly_rate=policy.hourly_rate,
        grace_minutes=policy.grace_minutes,
        daily_cap=policy.daily_cap,
        calculator_version=CalculatorVersion.HOURLY_V1,
    )
