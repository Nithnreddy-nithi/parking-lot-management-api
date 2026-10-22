from decimal import Decimal

from rest_framework import serializers

from apps.parking.api.serializers import (
    PaginationFilterSerializer,
    QueryBooleanField,
    StrictInputMixin,
)
from apps.parking.enums import VehicleType
from apps.parking.models import ParkingLot
from apps.pricing.enums import Currency
from apps.pricing.models import CheckoutQuote, PricingPolicy


class PricingPolicyCreateSerializer(StrictInputMixin, serializers.Serializer):
    parking_lot = serializers.PrimaryKeyRelatedField(queryset=ParkingLot.objects.all())
    vehicle_type = serializers.ChoiceField(choices=VehicleType.choices)
    currency = serializers.ChoiceField(choices=Currency.choices, default=Currency.INR)
    hourly_rate = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("0.01"),
    )
    grace_minutes = serializers.IntegerField(min_value=0, default=0)
    daily_cap = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("0.01"),
        required=False,
        allow_null=True,
    )


class PricingPolicyOutputSerializer(serializers.ModelSerializer):
    parking_lot = serializers.IntegerField(source="parking_lot_id", read_only=True)
    created_by = serializers.IntegerField(source="created_by_id", read_only=True)

    class Meta:
        model = PricingPolicy
        fields = (
            "id",
            "parking_lot",
            "vehicle_type",
            "version",
            "currency",
            "hourly_rate",
            "grace_minutes",
            "daily_cap",
            "is_active",
            "created_by",
            "created_at",
        )
        read_only_fields = fields


class PricingPolicyFilterSerializer(PaginationFilterSerializer):
    lot = serializers.IntegerField(min_value=1, required=False)
    vehicle_type = serializers.ChoiceField(choices=VehicleType.choices, required=False)
    is_active = QueryBooleanField(required=False)


class EmptyCheckoutSerializer(StrictInputMixin, serializers.Serializer):
    pass


class CheckoutQuoteOutputSerializer(serializers.ModelSerializer):
    parking_session = serializers.IntegerField(source="parking_session_id", read_only=True)

    class Meta:
        model = CheckoutQuote
        fields = (
            "id",
            "parking_session",
            "calculated_until",
            "amount",
            "currency",
            "calculation_breakdown",
            "created_at",
        )
        read_only_fields = fields
