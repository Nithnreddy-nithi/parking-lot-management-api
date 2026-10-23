from django.urls import path

from apps.payments.api.views import PaymentDetailView, PaymentListCreateView

urlpatterns = [
    path("payments/", PaymentListCreateView.as_view(), name="payment-list-create"),
    path("payments/<uuid:pk>/", PaymentDetailView.as_view(), name="payment-detail"),
]
