from rest_framework import serializers

from apps.parking.api.serializers import PaginationFilterSerializer, StrictInputMixin
from apps.sessions.enums import SessionStatus
from apps.sessions.models import ParkingSession


class EntryRequestSerializer(StrictInputMixin, serializers.Serializer):
    vehicle_id = serializers.IntegerField(min_value=1)
    entry_gate_id = serializers.IntegerField(min_value=1)


class ExitRequestSerializer(StrictInputMixin, serializers.Serializer):
    exit_gate_id = serializers.IntegerField(min_value=1)


class ParkingSessionOutputSerializer(serializers.ModelSerializer):
    vehicle_registration = serializers.CharField(
        source="registration_number_snapshot", read_only=True
    )
    vehicle_type = serializers.CharField(source="vehicle_type_snapshot", read_only=True)
    parking_lot_id = serializers.IntegerField(source="spot.floor.parking_lot_id", read_only=True)
    parking_lot_code = serializers.CharField(source="spot.floor.parking_lot.code", read_only=True)
    floor_id = serializers.IntegerField(source="spot.floor_id", read_only=True)
    floor_code = serializers.CharField(source="spot.floor.code", read_only=True)
    spot_id = serializers.IntegerField(source="spot.id", read_only=True)
    spot_number = serializers.CharField(source="spot.number", read_only=True)
    spot_type = serializers.CharField(source="spot.spot_type", read_only=True)
    entry_gate_id = serializers.IntegerField(source="entry_gate.id", read_only=True)
    entry_gate_code = serializers.CharField(source="entry_gate.code", read_only=True)
    exit_gate_id = serializers.IntegerField(source="exit_gate.id", read_only=True)
    exit_gate_code = serializers.CharField(source="exit_gate.code", read_only=True)
    exited_by = serializers.IntegerField(source="exited_by_id", read_only=True)

    class Meta:
        model = ParkingSession
        fields = (
            "id",
            "ticket_reference",
            "vehicle_registration",
            "vehicle_type",
            "parking_lot_id",
            "parking_lot_code",
            "floor_id",
            "floor_code",
            "spot_id",
            "spot_number",
            "spot_type",
            "entry_gate_id",
            "entry_gate_code",
            "exit_gate_id",
            "exit_gate_code",
            "exited_by",
            "entered_at",
            "closed_at",
            "status",
        )
        read_only_fields = fields


class SessionFilterSerializer(PaginationFilterSerializer):
    status = serializers.ChoiceField(choices=SessionStatus.choices, required=False)
    lot = serializers.IntegerField(min_value=1, required=False)
    entry_date_from = serializers.DateField(required=False)
    entry_date_to = serializers.DateField(required=False)
    vehicle = serializers.IntegerField(min_value=1, required=False)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        start = attrs.get("entry_date_from")
        end = attrs.get("entry_date_to")
        if start and end and start > end:
            raise serializers.ValidationError(
                {"entry_date_to": "Must be on or after entry_date_from."}
            )
        return attrs


class AvailabilityCountSerializer(serializers.Serializer):
    spot_type = serializers.CharField()
    total = serializers.IntegerField()
    operationally_enabled = serializers.IntegerField()
    occupied = serializers.IntegerField()
    available = serializers.IntegerField()


class AvailabilitySerializer(serializers.Serializer):
    parking_lot_id = serializers.IntegerField()
    counts = AvailabilityCountSerializer(many=True)
