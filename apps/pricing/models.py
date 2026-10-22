from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.parking.enums import VehicleType
from apps.parking.models import ParkingLot
from apps.pricing.enums import CalculatorVersion, Currency


class PricingPolicy(models.Model):
    parking_lot = models.ForeignKey(
        ParkingLot,
        on_delete=models.PROTECT,
        related_name="pricing_policies",
    )
    vehicle_type = models.CharField(max_length=16, choices=VehicleType.choices)
    version = models.PositiveIntegerField()
    currency = models.CharField(max_length=3, choices=Currency.choices, default=Currency.INR)
    hourly_rate = models.DecimalField(max_digits=12, decimal_places=2)
    grace_minutes = models.PositiveIntegerField(default=0)
    daily_cap = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_pricing_policies",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    _IMMUTABLE_FIELDS = (
        "parking_lot_id",
        "vehicle_type",
        "version",
        "currency",
        "hourly_rate",
        "grace_minutes",
        "daily_cap",
        "created_by_id",
    )

    class Meta:
        ordering = ("parking_lot_id", "vehicle_type", "-version", "-id")
        constraints = [
            models.UniqueConstraint(
                fields=("parking_lot", "vehicle_type", "version"),
                name="pricing_policy_lot_vehicle_version_unique",
            ),
            models.UniqueConstraint(
                fields=("parking_lot", "vehicle_type"),
                condition=models.Q(is_active=True),
                name="pricing_policy_one_active",
            ),
            models.CheckConstraint(
                condition=models.Q(vehicle_type__in=VehicleType.values),
                name="pricing_policy_vehicle_type_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(currency__in=Currency.values),
                name="pricing_policy_currency_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(version__gt=0),
                name="pricing_policy_version_positive",
            ),
            models.CheckConstraint(
                condition=models.Q(hourly_rate__gt=0),
                name="pricing_policy_hourly_rate_positive",
            ),
            models.CheckConstraint(
                condition=models.Q(grace_minutes__gte=0),
                name="pricing_policy_grace_nonnegative",
            ),
            models.CheckConstraint(
                condition=models.Q(daily_cap__isnull=True) | models.Q(daily_cap__gt=0),
                name="pricing_policy_daily_cap_positive",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.parking_lot.code}/{self.vehicle_type}/v{self.version}"

    def save(self, *args, **kwargs):
        if self.pk:
            original = type(self).objects.only(*self._IMMUTABLE_FIELDS).get(pk=self.pk)
            changed = [
                field
                for field in self._IMMUTABLE_FIELDS
                if getattr(original, field) != getattr(self, field)
            ]
            if changed:
                raise ValidationError(
                    {
                        field.removesuffix("_id"): "Published pricing is immutable."
                        for field in changed
                    }
                )
        return super().save(*args, **kwargs)


class PricingSnapshot(models.Model):
    parking_session = models.OneToOneField(
        "parking_sessions.ParkingSession",
        on_delete=models.PROTECT,
        related_name="pricing_snapshot",
    )
    pricing_policy = models.ForeignKey(
        PricingPolicy,
        on_delete=models.PROTECT,
        related_name="snapshots",
    )
    policy_version = models.PositiveIntegerField()
    currency = models.CharField(max_length=3, choices=Currency.choices)
    hourly_rate = models.DecimalField(max_digits=12, decimal_places=2)
    grace_minutes = models.PositiveIntegerField()
    daily_cap = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    calculator_version = models.CharField(max_length=24, choices=CalculatorVersion.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(policy_version__gt=0),
                name="pricing_snapshot_version_positive",
            ),
            models.CheckConstraint(
                condition=models.Q(currency__in=Currency.values),
                name="pricing_snapshot_currency_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(hourly_rate__gt=0),
                name="pricing_snapshot_hourly_rate_positive",
            ),
            models.CheckConstraint(
                condition=models.Q(grace_minutes__gte=0),
                name="pricing_snapshot_grace_nonnegative",
            ),
            models.CheckConstraint(
                condition=models.Q(daily_cap__isnull=True) | models.Q(daily_cap__gt=0),
                name="pricing_snapshot_daily_cap_positive",
            ),
            models.CheckConstraint(
                condition=models.Q(calculator_version__in=CalculatorVersion.values),
                name="pricing_snapshot_calculator_valid",
            ),
        ]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("Pricing snapshots are immutable.")
        return super().save(*args, **kwargs)


class CheckoutQuote(models.Model):
    parking_session = models.OneToOneField(
        "parking_sessions.ParkingSession",
        on_delete=models.PROTECT,
        related_name="checkout_quote",
    )
    calculated_until = models.DateTimeField()
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, choices=Currency.choices)
    calculation_breakdown = models.JSONField()
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_checkout_quotes",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gte=0),
                name="checkout_quote_amount_nonnegative",
            ),
            models.CheckConstraint(
                condition=models.Q(currency__in=Currency.values),
                name="checkout_quote_currency_valid",
            ),
        ]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("Checkout quotes are immutable.")
        return super().save(*args, **kwargs)
