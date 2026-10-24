from decimal import Decimal

from django.conf import settings
from rest_framework import serializers

from apps.parking.api.serializers import PaginationFilterSerializer, StrictInputMixin
from apps.payments.enums import PaymentStatus
from apps.payments.models import PaymentAttempt, Refund, Settlement


class PaymentInitiationSerializer(StrictInputMixin, serializers.Serializer):
    parking_session_id = serializers.IntegerField(min_value=1)


class PaymentAttemptOutputSerializer(serializers.ModelSerializer):
    quote_id = serializers.IntegerField(read_only=True)
    parking_session_id = serializers.IntegerField(
        source="quote.parking_session_id",
        read_only=True,
    )
    checkout_key_id = serializers.SerializerMethodField()

    def get_checkout_key_id(self, obj) -> str | None:
        if obj.provider == "RAZORPAY" and obj.status == PaymentStatus.PENDING:
            return settings.RAZORPAY_KEY_ID
        return None

    class Meta:
        model = PaymentAttempt
        fields = (
            "id",
            "quote_id",
            "parking_session_id",
            "provider",
            "provider_reference",
            "provider_order_reference",
            "checkout_key_id",
            "amount",
            "currency",
            "status",
            "failure_code",
            "created_at",
            "updated_at",
            "completed_at",
        )
        read_only_fields = fields


class PaymentConfirmationSerializer(StrictInputMixin, serializers.Serializer):
    razorpay_order_id = serializers.CharField(max_length=64)
    razorpay_payment_id = serializers.CharField(max_length=64)
    razorpay_signature = serializers.CharField(max_length=256)


class RefundInitiationSerializer(StrictInputMixin, serializers.Serializer):
    payment_attempt_id = serializers.UUIDField()
    amount = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("0.01"),
    )
    reason = serializers.CharField(min_length=3, max_length=255, trim_whitespace=True)


class RefundOutputSerializer(serializers.ModelSerializer):
    payment_attempt_id = serializers.UUIDField(
        source="settlement.payment_attempt_id", read_only=True
    )
    parking_session_id = serializers.IntegerField(
        source="settlement.quote.parking_session_id",
        read_only=True,
    )

    class Meta:
        model = Refund
        fields = (
            "id",
            "payment_attempt_id",
            "parking_session_id",
            "provider_reference",
            "amount",
            "currency",
            "status",
            "reason",
            "failure_code",
            "created_at",
            "updated_at",
            "completed_at",
        )
        read_only_fields = fields


class PaymentFilterSerializer(PaginationFilterSerializer):
    status = serializers.ChoiceField(choices=PaymentStatus.choices, required=False)
    session = serializers.IntegerField(min_value=1, required=False)


class EmptySettlementSerializer(StrictInputMixin, serializers.Serializer):
    pass


class SettlementOutputSerializer(serializers.ModelSerializer):
    quote_id = serializers.IntegerField(read_only=True)
    parking_session_id = serializers.IntegerField(
        source="quote.parking_session_id",
        read_only=True,
    )
    payment_attempt_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = Settlement
        fields = (
            "id",
            "quote_id",
            "parking_session_id",
            "payment_attempt_id",
            "method",
            "amount",
            "currency",
            "settled_at",
        )
        read_only_fields = fields
