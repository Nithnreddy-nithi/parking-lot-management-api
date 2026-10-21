from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.parking.enums import GateType, SpotOperationalStatus, SpotType, VehicleType


def normalize_identifier(value: str) -> str:
    return value.strip().upper()


def normalize_registration_number(value: str) -> str:
    """Uppercase a registration and remove spaces and hyphens for stable comparison."""
    return value.strip().upper().replace(" ", "").replace("-", "")


def validate_iana_timezone(value: str) -> None:
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValidationError("Enter a valid IANA timezone name.") from exc


class TimestampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class ParkingLot(TimestampedModel):
    code = models.CharField(max_length=32)
    name = models.CharField(max_length=120)
    address = models.TextField()
    timezone = models.CharField(
        max_length=64,
        default="Asia/Kolkata",
        validators=[validate_iana_timezone],
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("id",)
        constraints = [
            models.UniqueConstraint(fields=("code",), name="parking_lot_code_unique"),
            models.CheckConstraint(condition=~models.Q(code=""), name="parking_lot_code_nonblank"),
        ]

    def __str__(self) -> str:
        return f"{self.code} — {self.name}"

    def save(self, *args, **kwargs):
        self.code = normalize_identifier(self.code)
        return super().save(*args, **kwargs)


class Floor(TimestampedModel):
    parking_lot = models.ForeignKey(
        ParkingLot,
        on_delete=models.PROTECT,
        related_name="floors",
    )
    code = models.CharField(max_length=32)
    name = models.CharField(max_length=120)
    level = models.IntegerField()
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("id",)
        constraints = [
            models.UniqueConstraint(
                fields=("parking_lot", "code"),
                name="floor_lot_code_unique",
            ),
            models.UniqueConstraint(
                fields=("parking_lot", "level"),
                name="floor_lot_level_unique",
            ),
            models.CheckConstraint(condition=~models.Q(code=""), name="floor_code_nonblank"),
        ]

    def __str__(self) -> str:
        return f"{self.parking_lot.code}/{self.code}"

    def save(self, *args, **kwargs):
        self.code = normalize_identifier(self.code)
        return super().save(*args, **kwargs)

    @property
    def is_effectively_active(self) -> bool:
        return self.is_active and self.parking_lot.is_active


class Gate(TimestampedModel):
    parking_lot = models.ForeignKey(
        ParkingLot,
        on_delete=models.PROTECT,
        related_name="gates",
    )
    code = models.CharField(max_length=32)
    name = models.CharField(max_length=120)
    gate_type = models.CharField(max_length=8, choices=GateType.choices)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("id",)
        constraints = [
            models.UniqueConstraint(
                fields=("parking_lot", "code"),
                name="gate_lot_code_unique",
            ),
            models.CheckConstraint(condition=~models.Q(code=""), name="gate_code_nonblank"),
            models.CheckConstraint(
                condition=models.Q(gate_type__in=GateType.values),
                name="gate_type_valid",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.parking_lot.code}/{self.code}"

    def save(self, *args, **kwargs):
        self.code = normalize_identifier(self.code)
        return super().save(*args, **kwargs)

    @property
    def is_effectively_active(self) -> bool:
        return self.is_active and self.parking_lot.is_active


class ParkingSpot(TimestampedModel):
    floor = models.ForeignKey(Floor, on_delete=models.PROTECT, related_name="spots")
    number = models.CharField(max_length=32)
    spot_type = models.CharField(max_length=16, choices=SpotType.choices)
    operational_status = models.CharField(
        max_length=16,
        choices=SpotOperationalStatus.choices,
        default=SpotOperationalStatus.ENABLED,
    )

    class Meta:
        ordering = ("id",)
        constraints = [
            models.UniqueConstraint(
                fields=("floor", "number"),
                name="spot_floor_number_unique",
            ),
            models.CheckConstraint(condition=~models.Q(number=""), name="spot_number_nonblank"),
            models.CheckConstraint(
                condition=models.Q(spot_type__in=SpotType.values),
                name="spot_type_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(operational_status__in=SpotOperationalStatus.values),
                name="spot_operational_status_valid",
            ),
        ]
        indexes = [
            models.Index(
                fields=("floor", "operational_status", "spot_type"),
                name="spot_floor_status_type_idx",
            )
        ]

    def __str__(self) -> str:
        return f"{self.floor}/{self.number}"

    def save(self, *args, **kwargs):
        self.number = normalize_identifier(self.number)
        return super().save(*args, **kwargs)

    @property
    def is_effectively_available(self) -> bool:
        return (
            self.operational_status == SpotOperationalStatus.ENABLED
            and self.floor.is_effectively_active
        )


class Vehicle(TimestampedModel):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="vehicles",
    )
    registration_number = models.CharField(max_length=32)
    vehicle_type = models.CharField(max_length=16, choices=VehicleType.choices)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("id",)
        constraints = [
            models.UniqueConstraint(
                fields=("registration_number",),
                name="vehicle_registration_unique",
            ),
            models.CheckConstraint(
                condition=~models.Q(registration_number=""),
                name="vehicle_registration_nonblank",
            ),
            models.CheckConstraint(
                condition=models.Q(vehicle_type__in=VehicleType.values),
                name="vehicle_type_valid",
            ),
        ]
        indexes = [models.Index(fields=("owner", "is_active"), name="vehicle_owner_active_idx")]

    def __str__(self) -> str:
        return self.registration_number

    def save(self, *args, **kwargs):
        self.registration_number = normalize_registration_number(self.registration_number)
        return super().save(*args, **kwargs)
