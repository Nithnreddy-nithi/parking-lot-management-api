from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from apps.pricing.calculators import HourlyV1Calculator, resolve_calculator
from apps.pricing.enums import CalculatorVersion


@dataclass(frozen=True)
class Pricing:
    hourly_rate: Decimal = Decimal("30.00")
    grace_minutes: int = 15
    daily_cap: Decimal | None = Decimal("300.00")
    currency: str = "INR"
    calculator_version: str = CalculatorVersion.HOURLY_V1


ENTERED_AT = datetime(2026, 1, 1, tzinfo=UTC)


def calculate(duration: timedelta, pricing: Pricing | None = None):
    return HourlyV1Calculator().calculate(
        pricing=pricing or Pricing(),
        entered_at=ENTERED_AT,
        calculated_until=ENTERED_AT + duration,
    )


@pytest.mark.parametrize(
    ("duration", "expected"),
    [
        (timedelta(0), "0.00"),
        (timedelta(minutes=15), "0.00"),
        (timedelta(minutes=15, seconds=1), "30.00"),
        (timedelta(minutes=60), "30.00"),
        (timedelta(minutes=60, seconds=1), "60.00"),
        (timedelta(hours=10), "300.00"),
        (timedelta(hours=11), "300.00"),
        (timedelta(hours=24), "300.00"),
        (timedelta(hours=24, seconds=1), "330.00"),
        (timedelta(hours=25), "330.00"),
        (timedelta(days=2, hours=3), "690.00"),
    ],
)
def test_hourly_v1_boundaries(duration, expected):
    assert calculate(duration).amount == Decimal(expected)


def test_no_daily_cap_rounds_each_started_hour():
    pricing = Pricing(daily_cap=None)
    result = calculate(timedelta(hours=25, microseconds=1), pricing)
    assert result.amount == Decimal("780.00")
    assert result.breakdown["full_24_hour_blocks"]["count"] == 1
    assert result.breakdown["remainder"]["billable_hours"] == 2


def test_zero_grace_still_allows_zero_duration_only():
    pricing = Pricing(grace_minutes=0)
    assert calculate(timedelta(0), pricing).amount == Decimal("0.00")
    assert calculate(timedelta(microseconds=1), pricing).amount == Decimal("30.00")


def test_negative_duration_is_rejected():
    with pytest.raises(ValueError, match="cannot precede"):
        calculate(timedelta(microseconds=-1))


def test_timezone_aware_equivalent_instants_have_zero_duration():
    calculator = HourlyV1Calculator()
    entered = datetime(2026, 1, 1, 12, tzinfo=ZoneInfo("Asia/Kolkata"))
    until = datetime(2026, 1, 1, 6, 30, tzinfo=UTC)
    assert calculator.calculate(
        pricing=Pricing(), entered_at=entered, calculated_until=until
    ).amount == Decimal("0.00")


def test_elapsed_utc_duration_handles_daylight_saving_transition():
    calculator = HourlyV1Calculator()
    new_york = ZoneInfo("America/New_York")
    entered = datetime(2026, 3, 8, 1, 30, tzinfo=new_york)
    until = datetime(2026, 3, 8, 3, 30, tzinfo=new_york)
    result = calculator.calculate(
        pricing=Pricing(grace_minutes=0), entered_at=entered, calculated_until=until
    )
    assert result.amount == Decimal("30.00")
    assert result.breakdown["duration_seconds"] == "3600"


def test_large_duration_has_bounded_breakdown():
    result = calculate(timedelta(days=100_000, hours=1))
    assert result.breakdown["full_24_hour_blocks"]["count"] == 100_000
    assert len(result.breakdown) == 7
    assert isinstance(result.breakdown["full_24_hour_blocks"], dict)


def test_decimal_precision_is_stable():
    pricing = Pricing(hourly_rate=Decimal("0.10"), grace_minutes=0, daily_cap=None)
    result = calculate(timedelta(hours=2, microseconds=1), pricing)
    assert result.amount == Decimal("0.30")
    assert result.breakdown["total"] == "0.30"


def test_resolver_rejects_unknown_calculator_without_fallback():
    assert isinstance(resolve_calculator(CalculatorVersion.HOURLY_V1), HourlyV1Calculator)
    with pytest.raises(ValueError, match="Unsupported"):
        resolve_calculator("UNKNOWN")


def test_naive_timestamp_is_rejected():
    with pytest.raises(ValueError, match="timezone-aware"):
        HourlyV1Calculator().calculate(
            pricing=Pricing(),
            entered_at=datetime(2026, 1, 1),
            calculated_until=ENTERED_AT,
        )
