from django.urls import path

from apps.sessions.api.views import (
    ParkingAvailabilityView,
    ParkingEntryView,
    ParkingSessionCheckoutView,
    ParkingSessionDetailView,
    ParkingSessionExitView,
    ParkingSessionListView,
    ParkingSessionQuoteView,
    ParkingSessionZeroSettlementView,
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
        "parking-sessions/<int:pk>/checkout/",
        ParkingSessionCheckoutView.as_view(),
        name="parking-session-checkout",
    ),
    path(
        "parking-sessions/<int:pk>/quote/",
        ParkingSessionQuoteView.as_view(),
        name="parking-session-quote",
    ),
    path(
        "parking-sessions/<int:pk>/settle-zero/",
        ParkingSessionZeroSettlementView.as_view(),
        name="parking-session-settle-zero",
    ),
    path(
        "parking-sessions/<int:pk>/exit/",
        ParkingSessionExitView.as_view(),
        name="parking-session-exit",
    ),
    path(
        "parking-lots/<int:pk>/availability/",
        ParkingAvailabilityView.as_view(),
        name="parking-lot-availability",
    ),
]
