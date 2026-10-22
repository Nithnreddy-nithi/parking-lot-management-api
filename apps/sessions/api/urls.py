from django.urls import path

from apps.sessions.api.views import (
    ParkingAvailabilityView,
    ParkingEntryView,
    ParkingSessionDetailView,
    ParkingSessionListView,
)

urlpatterns = [
    path("parking-sessions/", ParkingSessionListView.as_view(), name="parking-session-list"),
    path(
        "parking-sessions/entry/",
        ParkingEntryView.as_view(),
        name="parking-session-entry",
    ),
    path(
        "parking-sessions/<int:pk>/",
        ParkingSessionDetailView.as_view(),
        name="parking-session-detail",
    ),
    path(
        "parking-lots/<int:pk>/availability/",
        ParkingAvailabilityView.as_view(),
        name="parking-lot-availability",
    ),
]
