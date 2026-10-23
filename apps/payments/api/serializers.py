from rest_framework import serializers

from apps.parking.api.serializers import PaginationFilterSerializer, StrictInputMixin
from apps.payments.enums import PaymentStatus
from apps.payments.models import PaymentAttempt, Settlement


class PaymentInitiationSerializer(StrictInputMixin, serializers.Serializer):
    parking_session_id = serializers.IntegerField(min_value=1)


class PaymentAttemptOutputSerializer(serializers.ModelSerializer):
    quote_id = serializers.IntegerField(read_only=True)
    parking_session_id = serializers.IntegerField(
        source="quote.parking_session_id",
        read_only=True,
    )

    class Meta:
        model = PaymentAttempt
        fields = (
            "id",
            "quote_id",
            "parking_session_id",
            "provider",
            "provider_reference",
            "amount",
            "currency",
            "status",
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
