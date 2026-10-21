from django.db import models


class GateType(models.TextChoices):
    ENTRY = "ENTRY", "Entry"
    EXIT = "EXIT", "Exit"
    BOTH = "BOTH", "Both"


class SpotType(models.TextChoices):
    MOTORCYCLE = "MOTORCYCLE", "Motorcycle"
    COMPACT = "COMPACT", "Compact"
    LARGE = "LARGE", "Large"


class SpotOperationalStatus(models.TextChoices):
    ENABLED = "ENABLED", "Enabled"
    MAINTENANCE = "MAINTENANCE", "Maintenance"
    DISABLED = "DISABLED", "Disabled"


class VehicleType(models.TextChoices):
    MOTORCYCLE = "MOTORCYCLE", "Motorcycle"
    CAR = "CAR", "Car"
    TRUCK = "TRUCK", "Truck"
