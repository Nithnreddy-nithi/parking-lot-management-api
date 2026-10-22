from django.db import models


class SessionStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "Active"
    PAYMENT_PENDING = "PAYMENT_PENDING", "Payment pending"
    PAID = "PAID", "Paid"
    CLOSED = "CLOSED", "Closed"


OPEN_SESSION_STATUSES = (
    SessionStatus.ACTIVE,
    SessionStatus.PAYMENT_PENDING,
    SessionStatus.PAID,
)
