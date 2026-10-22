from django.contrib import admin

from apps.pricing.models import CheckoutQuote, PricingPolicy, PricingSnapshot


@admin.register(PricingPolicy)
class PricingPolicyAdmin(admin.ModelAdmin):
    list_display = ("parking_lot", "vehicle_type", "version", "hourly_rate", "is_active")
    list_filter = ("vehicle_type", "currency", "is_active")

    def get_readonly_fields(self, request, obj=None):
        if obj is None:
            return ("version", "created_by", "created_at")
        return tuple(
            field.name for field in PricingPolicy._meta.fields if field.name != "is_active"
        )


@admin.register(PricingSnapshot)
class PricingSnapshotAdmin(admin.ModelAdmin):
    list_display = ("parking_session", "pricing_policy", "policy_version", "hourly_rate")
    readonly_fields = [field.name for field in PricingSnapshot._meta.fields]


@admin.register(CheckoutQuote)
class CheckoutQuoteAdmin(admin.ModelAdmin):
    list_display = ("parking_session", "amount", "currency", "calculated_until")
    readonly_fields = [field.name for field in CheckoutQuote._meta.fields]
