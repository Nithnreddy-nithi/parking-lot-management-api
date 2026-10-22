from django.db import models


class Currency(models.TextChoices):
    INR = "INR", "Indian rupee"


class CalculatorVersion(models.TextChoices):
    HOURLY_V1 = "HOURLY_V1", "Hourly V1"
