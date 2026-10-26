from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Protocol

from apps.pricing.enums import CalculatorVersion

MONEY_QUANTUM = Decimal("0.01")
MICROSECONDS_PER_SECOND = 1_000_000
SECONDS_PER_HOUR = 3_600
SECONDS_PER_DAY = 86_400


class PricingInput(Protocol):
    currency: str
    hourly_rate: Decimal
    grace_minutes: int
    daily_cap: Decimal | None
    calculator_version: str


@dataclass(frozen=True)
class CalculationResult:
    amount: Decimal
    currency: str
    breakdown: dict


class FeeCalculator(Protocol):
    version: str

    def calculate(
        self,
        *,
        pricing: PricingInput,
        entered_at: datetime,
        calculated_until: datetime,
    ) -> CalculationResult: ...


class HourlyV1Calculator:
    version = CalculatorVersion.HOURLY_V1

    def calculate(
        self,
        *,
        pricing: PricingInput,
        entered_at: datetime,
        calculated_until: datetime,
    ) -> CalculationResult:
        if entered_at.utcoffset() is None or calculated_until.utcoffset() is None:
            raise ValueError("Pricing timestamps must be timezone-aware.")

        duration = calculated_until.astimezone(UTC) - entered_at.astimezone(UTC)
        duration_microseconds = (
            duration.days * SECONDS_PER_DAY * MICROSECONDS_PER_SECOND
            + duration.seconds * MICROSECONDS_PER_SECOND
            + duration.microseconds
        )
        if duration_microseconds < 0:
            raise ValueError("calculated_until cannot precede entered_at.")

        duration_seconds = _decimal_seconds(duration_microseconds)
        day_microseconds = SECONDS_PER_DAY * MICROSECONDS_PER_SECOND
        full_block_count, remainder_microseconds = divmod(duration_microseconds, day_microseconds)
        grace_microseconds = pricing.grace_minutes * 60 * MICROSECONDS_PER_SECOND
        if duration_microseconds <= grace_microseconds:
            zero = Decimal("0.00")
            return CalculationResult(
                amount=zero,
                currency=pricing.currency,
                breakdown=_breakdown(
                    duration_seconds=duration_seconds,
                    grace_applied=True,
                    full_block_count=full_block_count,
                    full_block_uncapped=zero,
                    full_block_amount=zero,
                    full_block_cap_applied=False,
                    remainder_seconds=_decimal_seconds(remainder_microseconds),
                    remainder_hours=0,
                    remainder_uncapped=zero,
                    remainder_amount=zero,
                    remainder_cap_applied=False,
                    total=zero,
                    currency=pricing.currency,
                ),
            )

        full_block_uncapped = _money(pricing.hourly_rate * 24)
        full_block_amount, full_cap_applied = _apply_cap(
            full_block_uncapped,
            pricing.daily_cap,
        )
        full_blocks_total = _money(full_block_amount * full_block_count)

        remainder_hours = _ceil_div(
            remainder_microseconds,
            SECONDS_PER_HOUR * MICROSECONDS_PER_SECOND,
        )
        remainder_uncapped = _money(pricing.hourly_rate * remainder_hours)
        remainder_amount, remainder_cap_applied = _apply_cap(
            remainder_uncapped,
            pricing.daily_cap,
        )
        total = _money(full_blocks_total + remainder_amount)

        return CalculationResult(
            amount=total,
            currency=pricing.currency,
            breakdown=_breakdown(
                duration_seconds=duration_seconds,
                grace_applied=False,
                full_block_count=full_block_count,
                full_block_uncapped=full_block_uncapped,
                full_block_amount=full_block_amount,
                full_block_cap_applied=full_cap_applied,
                remainder_seconds=_decimal_seconds(remainder_microseconds),
                remainder_hours=remainder_hours,
                remainder_uncapped=remainder_uncapped,
                remainder_amount=remainder_amount,
                remainder_cap_applied=remainder_cap_applied,
                total=total,
                currency=pricing.currency,
            ),
        )


def resolve_calculator(version: str) -> FeeCalculator:
    if version == CalculatorVersion.HOURLY_V1:
        return HourlyV1Calculator()
    raise ValueError(f"Unsupported calculator version: {version}")


def _ceil_div(value: int, divisor: int) -> int:
    return 0 if value == 0 else (value + divisor - 1) // divisor


def _money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def _apply_cap(amount: Decimal, cap: Decimal | None) -> tuple[Decimal, bool]:
    if cap is not None and amount > cap:
        return _money(cap), True
    return _money(amount), False


def _decimal_seconds(microseconds: int) -> Decimal:
    return (Decimal(microseconds) / MICROSECONDS_PER_SECOND).normalize()


def _breakdown(
    *,
    duration_seconds: Decimal,
    grace_applied: bool,
    full_block_count: int,
    full_block_uncapped: Decimal,
    full_block_amount: Decimal,
    full_block_cap_applied: bool,
    remainder_seconds: Decimal,
    remainder_hours: int,
    remainder_uncapped: Decimal,
    remainder_amount: Decimal,
    remainder_cap_applied: bool,
    total: Decimal,
    currency: str,
) -> dict:
    return {
        "duration_seconds": format(duration_seconds, "f"),
        "grace_applied": grace_applied,
        "full_24_hour_blocks": {
            "count": full_block_count,
            "uncapped_amount_per_block": str(_money(full_block_uncapped)),
            "amount_per_block": str(_money(full_block_amount)),
            "cap_applied": full_block_cap_applied,
            "total_amount": str(_money(full_block_amount * full_block_count)),
        },
        "remainder": {
            "duration_seconds": format(remainder_seconds, "f"),
            "billable_hours": remainder_hours,
            "uncapped_amount": str(_money(remainder_uncapped)),
            "amount": str(_money(remainder_amount)),
            "cap_applied": remainder_cap_applied,
        },
        "total": str(_money(total)),
        "currency": currency,
        "calculator_version": CalculatorVersion.HOURLY_V1,
    }
