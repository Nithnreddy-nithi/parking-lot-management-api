from django.urls import path

from apps.parking.api.views import (
    FloorDetailView,
    FloorListCreateView,
    GateDetailView,
    GateListCreateView,
    ParkingLotDetailView,
    ParkingLotListCreateView,
    ParkingSpotDetailView,
    ParkingSpotListCreateView,
    VehicleDetailView,
    VehicleListCreateView,
)

urlpatterns = [
    path("parking-lots/", ParkingLotListCreateView.as_view(), name="parking-lot-list"),
    path("parking-lots/<int:pk>/", ParkingLotDetailView.as_view(), name="parking-lot-detail"),
    path("floors/", FloorListCreateView.as_view(), name="floor-list"),
    path("floors/<int:pk>/", FloorDetailView.as_view(), name="floor-detail"),
    path("gates/", GateListCreateView.as_view(), name="gate-list"),
    path("gates/<int:pk>/", GateDetailView.as_view(), name="gate-detail"),
    path("spots/", ParkingSpotListCreateView.as_view(), name="parking-spot-list"),
    path("spots/<int:pk>/", ParkingSpotDetailView.as_view(), name="parking-spot-detail"),
    path("vehicles/", VehicleListCreateView.as_view(), name="vehicle-list"),
    path("vehicles/<int:pk>/", VehicleDetailView.as_view(), name="vehicle-detail"),
]
