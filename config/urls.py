from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from config.api.views import live_health

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", include("apps.accounts.api.urls")),
    path("api/v1/health/live/", live_health, name="health-live"),
    path("api/v1/schema/", SpectacularAPIView.as_view(), name="openapi-schema"),
    path(
        "api/v1/docs/",
        SpectacularSwaggerView.as_view(url_name="openapi-schema"),
        name="swagger-ui",
    ),
]
