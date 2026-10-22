from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from rest_framework import serializers
from rest_framework.fields import empty

from apps.parking.enums import GateType, SpotOperationalStatus, SpotType, VehicleType
from apps.parking.models import (
    Floor,
    Gate,
    ParkingLot,
    ParkingSpot,
    Vehicle,
    normalize_identifier,
    normalize_registration_number,
)


class StrictInputMixin:
    def validate(self, attrs):
        unsupported = set(self.initial_data) - set(self.fields)
        if unsupported:
            raise serializers.ValidationError(
                {field: "This field may not be supplied." for field in sorted(unsupported)}
            )
        return super().validate(attrs)


class PaginationFilterSerializer(StrictInputMixin, serializers.Serializer):
    page = serializers.IntegerField(min_value=1, required=False)
    page_size = serializers.IntegerField(min_value=1, max_value=100, required=False)


class QueryBooleanField(serializers.BooleanField):
    """Keep an omitted query parameter absent instead of treating it as HTML false."""

    def get_value(self, dictionary):
        if self.field_name not in dictionary:
            return empty
        return super().get_value(dictionary)


class ParkingLotOutputSerializer(serializers.ModelSerializer):
    class Meta:
        model = ParkingLot
        fields = (
            "id",
            "code",
            "name",
            "address",
            "timezone",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class ParkingLotWriteSerializer(StrictInputMixin, serializers.Serializer):
    code = serializers.CharField(max_length=32)
    name = serializers.CharField(max_length=120)
    address = serializers.CharField()
    timezone = serializers.CharField(max_length=64, default="Asia/Kolkata")
    is_active = serializers.BooleanField(default=True)

    def validate_code(self, value: str) -> str:
        return normalize_identifier(value)

    def validate_timezone(self, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise serializers.ValidationError("Enter a valid IANA timezone name.") from exc
        return value


class ParkingLotUpdateSerializer(ParkingLotWriteSerializer):
    code = serializers.CharField(max_length=32, required=False)
    name = serializers.CharField(max_length=120, required=False)
    address = serializers.CharField(required=False)
    timezone = serializers.CharField(max_length=64, required=False)
    is_active = serializers.BooleanField(required=False)


class ParkingLotFilterSerializer(PaginationFilterSerializer):
    is_active = QueryBooleanField(required=False)
    search = serializers.CharField(max_length=120, required=False, allow_blank=True)


class FloorOutputSerializer(serializers.ModelSerializer):
    parking_lot = serializers.IntegerField(source="parking_lot_id", read_only=True)
    is_effectively_active = serializers.BooleanField(read_only=True)

    class Meta:
        model = Floor
        fields = (
            "id",
            "parking_lot",
            "code",
            "name",
            "level",
            "is_active",
            "is_effectively_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class FloorCreateSerializer(StrictInputMixin, serializers.Serializer):
    parking_lot = serializers.PrimaryKeyRelatedField(queryset=ParkingLot.objects.all())
    code = serializers.CharField(max_length=32)
    name = serializers.CharField(max_length=120)
    level = serializers.IntegerField()
    is_active = serializers.BooleanField(default=True)

    def validate_code(self, value: str) -> str:
        return normalize_identifier(value)


class FloorUpdateSerializer(StrictInputMixin, serializers.Serializer):
    code = serializers.CharField(max_length=32, required=False)
    name = serializers.CharField(max_length=120, required=False)
    level = serializers.IntegerField(required=False)
    is_active = serializers.BooleanField(required=False)

    def validate_code(self, value: str) -> str:
        return normalize_identifier(value)


class FloorFilterSerializer(PaginationFilterSerializer):
    parking_lot = serializers.IntegerField(min_value=1, required=False)
    is_active = QueryBooleanField(required=False)


class GateOutputSerializer(serializers.ModelSerializer):
    parking_lot = serializers.IntegerField(source="parking_lot_id", read_only=True)
    gate_type_display = serializers.CharField(source="get_gate_type_display", read_only=True)
    is_effectively_active = serializers.BooleanField(read_only=True)

    class Meta:
        model = Gate
        fields = (
            "id",
            "parking_lot",
            "code",
            "name",
            "gate_type",
            "gate_type_display",
            "is_active",
            "is_effectively_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class GateCreateSerializer(StrictInputMixin, serializers.Serializer):
    parking_lot = serializers.PrimaryKeyRelatedField(queryset=ParkingLot.objects.all())
    code = serializers.CharField(max_length=32)
    name = serializers.CharField(max_length=120)
    gate_type = serializers.ChoiceField(choices=GateType.choices)
    is_active = serializers.BooleanField(default=True)

    def validate_code(self, value: str) -> str:
        return normalize_identifier(value)


class GateUpdateSerializer(StrictInputMixin, serializers.Serializer):
    code = serializers.CharField(max_length=32, required=False)
    name = serializers.CharField(max_length=120, required=False)
    gate_type = serializers.ChoiceField(choices=GateType.choices, required=False)
    is_active = serializers.BooleanField(required=False)

    def validate_code(self, value: str) -> str:
        return normalize_identifier(value)


class GateFilterSerializer(PaginationFilterSerializer):
    parking_lot = serializers.IntegerField(min_value=1, required=False)
    gate_type = serializers.ChoiceField(choices=GateType.choices, required=False)
    is_active = QueryBooleanField(required=False)


class ParkingSpotOutputSerializer(serializers.ModelSerializer):
    floor = serializers.IntegerField(source="floor_id", read_only=True)
    parking_lot = serializers.IntegerField(source="floor.parking_lot_id", read_only=True)
    spot_type_display = serializers.CharField(source="get_spot_type_display", read_only=True)
    operational_status_display = serializers.CharField(
        source="get_operational_status_display", read_only=True
    )
    is_effectively_available = serializers.BooleanField(read_only=True)

    class Meta:
        model = ParkingSpot
        fields = (
            "id",
            "floor",
            "parking_lot",
            "number",
            "spot_type",
            "spot_type_display",
            "operational_status",
            "operational_status_display",
            "is_effectively_available",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class ParkingSpotCreateSerializer(StrictInputMixin, serializers.Serializer):
    floor = serializers.PrimaryKeyRelatedField(queryset=Floor.objects.all())
    number = serializers.CharField(max_length=32)
    spot_type = serializers.ChoiceField(choices=SpotType.choices)
    operational_status = serializers.ChoiceField(
        choices=SpotOperationalStatus.choices,
        default=SpotOperationalStatus.ENABLED,
    )

    def validate_number(self, value: str) -> str:
        return normalize_identifier(value)


class ParkingSpotUpdateSerializer(StrictInputMixin, serializers.Serializer):
    number = serializers.CharField(max_length=32, required=False)
    spot_type = serializers.ChoiceField(choices=SpotType.choices, required=False)
    operational_status = serializers.ChoiceField(
        choices=SpotOperationalStatus.choices,
        required=False,
    )

    def validate_number(self, value: str) -> str:
        return normalize_identifier(value)


class ParkingSpotFilterSerializer(PaginationFilterSerializer):
    floor = serializers.IntegerField(min_value=1, required=False)
    parking_lot = serializers.IntegerField(min_value=1, required=False)
    spot_type = serializers.ChoiceField(choices=SpotType.choices, required=False)
    operational_status = serializers.ChoiceField(
        choices=SpotOperationalStatus.choices,
        required=False,
    )


class VehicleOutputSerializer(serializers.ModelSerializer):
    owner = serializers.IntegerField(source="owner_id", read_only=True)
    vehicle_type_display = serializers.CharField(source="get_vehicle_type_display", read_only=True)

    class Meta:
        model = Vehicle
        fields = (
            "id",
            "owner",
            "registration_number",
            "vehicle_type",
            "vehicle_type_display",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class VehicleCreateSerializer(StrictInputMixin, serializers.Serializer):
    registration_number = serializers.CharField(max_length=32)
    vehicle_type = serializers.ChoiceField(choices=VehicleType.choices)
    is_active = serializers.BooleanField(default=True)

    def validate_registration_number(self, value: str) -> str:
        normalized = normalize_registration_number(value)
        if not normalized:
            raise serializers.ValidationError("This field may not be blank.")
        return normalized


class VehicleUpdateSerializer(VehicleCreateSerializer):
    registration_number = serializers.CharField(max_length=32, required=False)
    vehicle_type = serializers.ChoiceField(choices=VehicleType.choices, required=False)
    is_active = serializers.BooleanField(required=False)


class VehicleFilterSerializer(PaginationFilterSerializer):
    is_active = QueryBooleanField(required=False)
