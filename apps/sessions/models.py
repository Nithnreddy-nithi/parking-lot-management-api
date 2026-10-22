import secrets

from django.conf import settings
from django.db import models

from apps.parking.models import Gate, ParkingSpot, Vehicle
from apps.sessions.enums import OPEN_SESSION_STATUSES, SessionStatus


def generate_ticket_reference() -> str:
    """Return a URL-safe, server-generated reference with 192 bits of entropy."""
    return secrets.token_urlsafe(24)


class ParkingSession(models.Model):
    ticket_reference = models.CharField(
        max_length=32,
        unique=True,
        default=generate_ticket_reference,
        editable=False,
    )
    vehicle = models.ForeignKey(Vehicle, on_delete=models.PROTECT, related_name="parking_sessions")
    spot = models.ForeignKey(
        ParkingSpot,
        on_delete=models.PROTECT,
        related_name="parking_sessions",
    )
    entry_gate = models.ForeignKey(
        Gate,
        on_delete=models.PROTECT,
        related_name="entered_parking_sessions",
    )
    entered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="entered_parking_sessions",
    )
    entered_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=16,
        choices=SessionStatus.choices,
        default=SessionStatus.ACTIVE,
    )
    registration_number_snapshot = models.CharField(max_length=32)
    vehicle_type_snapshot = models.CharField(max_length=16)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-entered_at", "-id")
        constraints = [
            models.UniqueConstraint(
                fields=("spot",),
                condition=models.Q(status__in=OPEN_SESSION_STATUSES),
                name="session_one_open_per_spot",
            ),
            models.UniqueConstraint(
                fields=("vehicle",),
                condition=models.Q(status__in=OPEN_SESSION_STATUSES),
                name="session_one_open_per_vehicle",
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=SessionStatus.values),
                name="session_status_valid",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(status=SessionStatus.CLOSED, closed_at__isnull=False)
                    | (
                        models.Q(status__in=OPEN_SESSION_STATUSES)
                        & models.Q(closed_at__isnull=True)
                    )
                ),
                name="session_status_closed_at_consistent",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(closed_at__isnull=True)
                    | models.Q(closed_at__gte=models.F("entered_at"))
                ),
                name="session_closed_not_before_entry",
            ),
        ]
        indexes = [
            models.Index(fields=("status", "entered_at"), name="session_status_entered_idx"),
            models.Index(fields=("entered_at", "id"), name="session_entered_id_idx"),
        ]

    def __str__(self) -> str:
        return self.ticket_reference
