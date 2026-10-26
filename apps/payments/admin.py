from django.contrib import admin

from apps.payments.models import (
    PaymentAttempt,
    Refund,
    Settlement,
    SimulatedPaymentRecord,
    WebhookEvent,
)


@admin.register(PaymentAttempt)
class PaymentAttemptAdmin(admin.ModelAdmin):
    list_display = ("id", "quote", "provider", "amount", "currency", "status", "created_at")
    list_filter = ("provider", "status", "currency")
    search_fields = ("id", "provider_reference")
    readonly_fields = tuple(field.name for field in PaymentAttempt._meta.fields)

    def has_add_permission(self, request):
        return False


@admin.register(Settlement)
class SettlementAdmin(admin.ModelAdmin):
    list_display = ("id", "quote", "method", "amount", "currency", "settled_at")
    list_filter = ("method", "currency")
    readonly_fields = tuple(field.name for field in Settlement._meta.fields)

    def has_add_permission(self, request):
        return False


@admin.register(SimulatedPaymentRecord)
class SimulatedPaymentRecordAdmin(admin.ModelAdmin):
    list_display = ("merchant_reference", "status", "scenario", "updated_at")
    readonly_fields = tuple(field.name for field in SimulatedPaymentRecord._meta.fields)

    def has_add_permission(self, request):
        return False


@admin.register(Refund)
class RefundAdmin(admin.ModelAdmin):
    list_display = ("id", "settlement", "amount", "currency", "status", "created_at")
    list_filter = ("status", "currency")
    search_fields = ("id", "provider_reference")
    readonly_fields = tuple(field.name for field in Refund._meta.fields)

    def has_add_permission(self, request):
        return False


@admin.register(WebhookEvent)
class WebhookEventAdmin(admin.ModelAdmin):
    list_display = ("provider_event_id", "event_type", "status", "received_at")
    list_filter = ("provider", "status", "event_type")
    search_fields = ("provider_event_id",)
    readonly_fields = tuple(field.name for field in WebhookEvent._meta.fields)

    def has_add_permission(self, request):
        return False
