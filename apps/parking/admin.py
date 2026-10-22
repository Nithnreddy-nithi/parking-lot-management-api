from django.contrib import admin

from apps.parking.models import Floor, Gate, ParkingLot, ParkingSpot, Vehicle


@admin.register(ParkingLot)
class ParkingLotAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "timezone", "is_active")
    list_filter = ("is_active",)
    search_fields = ("code", "name")


@admin.register(Floor)
class FloorAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "parking_lot", "level", "is_active")
    list_filter = ("parking_lot", "is_active")


@admin.register(Gate)
class GateAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "parking_lot", "gate_type", "is_active")
    list_filter = ("parking_lot", "gate_type", "is_active")


@admin.register(ParkingSpot)
class ParkingSpotAdmin(admin.ModelAdmin):
    list_display = ("number", "floor", "spot_type", "operational_status")
    list_filter = ("floor", "spot_type", "operational_status")


@admin.register(Vehicle)
class VehicleAdmin(admin.ModelAdmin):
    list_display = ("registration_number", "owner", "vehicle_type", "is_active")
    list_filter = ("vehicle_type", "is_active")
    search_fields = ("registration_number", "owner__username")
