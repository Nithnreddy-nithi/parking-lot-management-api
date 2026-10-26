from django.urls import path

from apps.pricing.api.views import (
    PricingPolicyDetailView,
    PricingPolicyListCreateView,
    PricingPolicyRetireView,
)

urlpatterns = [
    path("pricing-policies/", PricingPolicyListCreateView.as_view(), name="pricing-policy-list"),
    path(
        "pricing-policies/<int:pk>/",
        PricingPolicyDetailView.as_view(),
        name="pricing-policy-detail",
    ),
    path(
        "pricing-policies/<int:pk>/retire/",
        PricingPolicyRetireView.as_view(),
        name="pricing-policy-retire",
    ),
]
