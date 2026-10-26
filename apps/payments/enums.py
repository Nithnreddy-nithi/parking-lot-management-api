from django.db import models


class PaymentProviderName(models.TextChoices):
    SIMULATED = "SIMULATED", "Simulated"
    RAZORPAY = "RAZORPAY", "Razorpay"


class PaymentStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    SUCCEEDED = "SUCCEEDED", "Succeeded"
    FAILED = "FAILED", "Failed"


class SettlementMethod(models.TextChoices):
    PROVIDER = "PROVIDER", "Provider"
    ZERO_CHARGE = "ZERO_CHARGE", "Zero charge"


class SimulationScenario(models.TextChoices):
    SUCCESS = "SUCCESS", "Success"
    FAILURE = "FAILURE", "Failure"
    PENDING = "PENDING", "Pending"
    TIMEOUT_AFTER_SUCCESS = "TIMEOUT_AFTER_SUCCESS", "Timeout after success"


class RefundStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    SUCCEEDED = "SUCCEEDED", "Succeeded"
    FAILED = "FAILED", "Failed"


class WebhookEventStatus(models.TextChoices):
    RECEIVED = "RECEIVED", "Received"
    PROCESSED = "PROCESSED", "Processed"
    IGNORED = "IGNORED", "Ignored"
    FAILED = "FAILED", "Failed"
