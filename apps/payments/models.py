import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.payments.enums import (
    PaymentProviderName,
    PaymentStatus,
    SettlementMethod,
    SimulationScenario,
)
from apps.pricing.enums import Currency


class PaymentAttempt(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    quote = models.ForeignKey(
        "parking_pricing.CheckoutQuote",
        on_delete=models.PROTECT,
        related_name="payment_attempts",
    )
    provider = models.CharField(
        max_length=16,
        choices=PaymentProviderName.choices,
        default=PaymentProviderName.SIMULATED,
    )
    provider_reference = models.CharField(max_length=64, null=True, blank=True, unique=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, choices=Currency.choices)
    status = models.CharField(
        max_length=16,
        choices=PaymentStatus.choices,
        default=PaymentStatus.PENDING,
    )
    failure_code = models.CharField(max_length=64, blank=True, default="")
    initiated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="initiated_payment_attempts",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    _IMMUTABLE_FIELDS = (
        "id",
        "quote_id",
        "provider",
        "amount",
        "currency",
        "initiated_by_id",
    )

    class Meta:
        ordering = ("-created_at", "-id")
        constraints = [
            models.CheckConstraint(
                condition=models.Q(provider__in=PaymentProviderName.values),
                name="payment_attempt_provider_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=PaymentStatus.values),
                name="payment_attempt_status_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(amount__gt=0),
                name="payment_attempt_amount_positive",
            ),
            models.UniqueConstraint(
                fields=("quote",),
                condition=models.Q(status=PaymentStatus.PENDING),
                name="payment_attempt_one_pending_per_quote",
            ),
            models.UniqueConstraint(
                fields=("quote",),
                condition=models.Q(status=PaymentStatus.SUCCEEDED),
                name="payment_attempt_one_success_per_quote",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(status=PaymentStatus.PENDING, completed_at__isnull=True)
                    | (
                        models.Q(status__in=(PaymentStatus.SUCCEEDED, PaymentStatus.FAILED))
                        & models.Q(completed_at__isnull=False)
                    )
                ),
                name="payment_attempt_completion_consistent",
            ),
            models.CheckConstraint(
                condition=(models.Q(status=PaymentStatus.FAILED) | models.Q(failure_code="")),
                name="payment_attempt_failure_code_consistent",
            ),
        ]
        indexes = [
            models.Index(fields=("status", "created_at"), name="payment_status_created_idx"),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            original = type(self).objects.only(*self._IMMUTABLE_FIELDS).get(pk=self.pk)
            changed = [
                field
                for field in self._IMMUTABLE_FIELDS
                if getattr(original, field) != getattr(self, field)
            ]
            if changed:
                raise ValidationError(
                    {
                        field.removesuffix("_id"): "Payment financial fields are immutable."
                        for field in changed
                    }
                )
        return super().save(*args, **kwargs)


class Settlement(models.Model):
    quote = models.OneToOneField(
        "parking_pricing.CheckoutQuote",
        on_delete=models.PROTECT,
        related_name="settlement",
    )
    payment_attempt = models.OneToOneField(
        PaymentAttempt,
        on_delete=models.PROTECT,
        related_name="settlement",
        null=True,
        blank=True,
    )
    method = models.CharField(max_length=16, choices=SettlementMethod.choices)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, choices=Currency.choices)
    settled_at = models.DateTimeField()

    class Meta:
        ordering = ("-settled_at", "-id")
        constraints = [
            models.CheckConstraint(
                condition=models.Q(method__in=SettlementMethod.values),
                name="settlement_method_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(currency__in=Currency.values),
                name="settlement_currency_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(amount__gte=0),
                name="settlement_amount_nonnegative",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        method=SettlementMethod.PROVIDER,
                        payment_attempt__isnull=False,
                        amount__gt=0,
                    )
                    | models.Q(
                        method=SettlementMethod.ZERO_CHARGE,
                        payment_attempt__isnull=True,
                        amount=0,
                    )
                ),
                name="settlement_method_consistent",
            ),
        ]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("Settlements are immutable.")
        return super().save(*args, **kwargs)


class SimulatedPaymentRecord(models.Model):
    """Persistent provider-side state, intentionally separate from domain attempts."""

    merchant_reference = models.UUIDField(unique=True)
    provider_reference = models.CharField(max_length=64, unique=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3)
    status = models.CharField(max_length=16, choices=PaymentStatus.choices)
    failure_code = models.CharField(max_length=64, blank=True, default="")
    scenario = models.CharField(max_length=32, choices=SimulationScenario.choices)
    initiation_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("merchant_reference",)
