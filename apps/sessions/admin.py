from django.contrib import admin

from apps.sessions.models import ParkingSession


@admin.register(ParkingSession)
class ParkingSessionAdmin(admin.ModelAdmin):
    list_display = (
        "ticket_reference",
        "vehicle",
        "spot",
        "entry_gate",
        "exit_gate",
        "status",
        "entered_at",
    )
    list_filter = ("status", "vehicle_type_snapshot", "entered_at")
    search_fields = ("ticket_reference", "registration_number_snapshot")
    readonly_fields = (
        "ticket_reference",
        "entered_at",
        "registration_number_snapshot",
        "vehicle_type_snapshot",
        "exit_gate",
        "exited_by",
        "closed_at",
        "created_at",
        "updated_at",
    )
