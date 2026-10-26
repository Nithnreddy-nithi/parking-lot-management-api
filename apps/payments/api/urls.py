from django.urls import path

from apps.payments.api.views import (
    PaymentConfirmationView,
    PaymentDetailView,
    PaymentListCreateView,
    RazorpayWebhookView,
    RefundDetailView,
    RefundListCreateView,
)

urlpatterns = [
    path("payments/", PaymentListCreateView.as_view(), name="payment-list-create"),
    path("payments/<uuid:pk>/", PaymentDetailView.as_view(), name="payment-detail"),
    path(
        "payments/<uuid:pk>/confirm/",
        PaymentConfirmationView.as_view(),
        name="payment-confirm",
    ),
    path("refunds/", RefundListCreateView.as_view(), name="refund-list-create"),
    path("refunds/<uuid:pk>/", RefundDetailView.as_view(), name="refund-detail"),
    path(
        "payments/webhooks/razorpay/",
        RazorpayWebhookView.as_view(),
        name="razorpay-webhook",
    ),
]
