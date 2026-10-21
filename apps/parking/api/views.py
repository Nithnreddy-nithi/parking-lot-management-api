from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiExample, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.generics import GenericAPIView
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.parking.api.serializers import (
    FloorCreateSerializer,
    FloorFilterSerializer,
    FloorOutputSerializer,
    FloorUpdateSerializer,
    GateCreateSerializer,
    GateFilterSerializer,
    GateOutputSerializer,
    GateUpdateSerializer,
    ParkingLotFilterSerializer,
    ParkingLotOutputSerializer,
    ParkingLotUpdateSerializer,
    ParkingLotWriteSerializer,
    ParkingSpotCreateSerializer,
    ParkingSpotFilterSerializer,
    ParkingSpotOutputSerializer,
    ParkingSpotUpdateSerializer,
    VehicleCreateSerializer,
    VehicleFilterSerializer,
    VehicleOutputSerializer,
    VehicleUpdateSerializer,
)
from apps.parking.models import Floor, Gate, ParkingLot, ParkingSpot, Vehicle
from apps.parking.permissions import CanReadOrManageParkingConfiguration
from apps.parking.selectors import (
    floor_list,
    gate_list,
    parking_lot_list,
    parking_spot_list,
    vehicle_list,
)
from apps.parking.services import (
    create_floor,
    create_gate,
    create_parking_lot,
    create_parking_spot,
    create_vehicle,
    update_floor,
    update_gate,
    update_parking_lot,
    update_parking_spot,
    update_vehicle,
)


class ParkingPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


CONFLICT_RESPONSE = OpenApiResponse(
    description="A normalized identifier conflicts with an existing resource."
)


def selector_filters(validated_data: dict) -> dict:
    return {key: value for key, value in validated_data.items() if key not in {"page", "page_size"}}


class ParkingLotListCreateView(GenericAPIView):
    permission_classes = [CanReadOrManageParkingConfiguration]
    pagination_class = ParkingPagination
    serializer_class = ParkingLotOutputSerializer

    @extend_schema(
        parameters=[ParkingLotFilterSerializer],
        responses={200: ParkingLotOutputSerializer(many=True)},
        description="ADMIN and OPERATOR can list lots; filters are validated.",
        tags=["Parking configuration"],
    )
    def get(self, request: Request) -> Response:
        query = ParkingLotFilterSerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        page = self.paginate_queryset(parking_lot_list(**selector_filters(query.validated_data)))
        return self.get_paginated_response(ParkingLotOutputSerializer(page, many=True).data)

    @extend_schema(
        request=ParkingLotWriteSerializer,
        responses={201: ParkingLotOutputSerializer, 409: CONFLICT_RESPONSE},
        examples=[
            OpenApiExample(
                "Create lot",
                value={
                    "code": "blr-central",
                    "name": "Bengaluru Central",
                    "address": "MG Road, Bengaluru",
                    "timezone": "Asia/Kolkata",
                },
                request_only=True,
            )
        ],
        description="ADMIN only. Codes are normalized to uppercase.",
        tags=["Parking configuration"],
    )
    def post(self, request: Request) -> Response:
        serializer = ParkingLotWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        parking_lot = create_parking_lot(data=serializer.validated_data)
        return Response(
            ParkingLotOutputSerializer(parking_lot).data,
            status=status.HTTP_201_CREATED,
        )


class ParkingLotDetailView(APIView):
    permission_classes = [CanReadOrManageParkingConfiguration]

    def get_object(self, pk: int) -> ParkingLot:
        return get_object_or_404(ParkingLot, pk=pk)

    @extend_schema(responses={200: ParkingLotOutputSerializer}, tags=["Parking configuration"])
    def get(self, request: Request, pk: int) -> Response:
        return Response(ParkingLotOutputSerializer(self.get_object(pk)).data)

    @extend_schema(
        request=ParkingLotUpdateSerializer,
        responses={200: ParkingLotOutputSerializer, 409: CONFLICT_RESPONSE},
        description="ADMIN only. Deactivation preserves all child configuration.",
        tags=["Parking configuration"],
    )
    def patch(self, request: Request, pk: int) -> Response:
        serializer = ParkingLotUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        parking_lot = update_parking_lot(
            parking_lot=self.get_object(pk), data=serializer.validated_data
        )
        return Response(ParkingLotOutputSerializer(parking_lot).data)


class FloorListCreateView(GenericAPIView):
    permission_classes = [CanReadOrManageParkingConfiguration]
    pagination_class = ParkingPagination
    serializer_class = FloorOutputSerializer

    @extend_schema(
        parameters=[FloorFilterSerializer],
        responses={200: FloorOutputSerializer(many=True)},
        tags=["Parking configuration"],
    )
    def get(self, request: Request) -> Response:
        query = FloorFilterSerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        page = self.paginate_queryset(floor_list(**selector_filters(query.validated_data)))
        return self.get_paginated_response(FloorOutputSerializer(page, many=True).data)

    @extend_schema(
        request=FloorCreateSerializer,
        responses={201: FloorOutputSerializer, 409: CONFLICT_RESPONSE},
        description=(
            "ADMIN only. The parent lot must be active; negative basement levels are valid."
        ),
        tags=["Parking configuration"],
    )
    def post(self, request: Request) -> Response:
        serializer = FloorCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        floor = create_floor(data=serializer.validated_data)
        return Response(FloorOutputSerializer(floor).data, status=status.HTTP_201_CREATED)


class FloorDetailView(APIView):
    permission_classes = [CanReadOrManageParkingConfiguration]

    def get_object(self, pk: int) -> Floor:
        return get_object_or_404(Floor.objects.select_related("parking_lot"), pk=pk)

    @extend_schema(responses={200: FloorOutputSerializer}, tags=["Parking configuration"])
    def get(self, request: Request, pk: int) -> Response:
        return Response(FloorOutputSerializer(self.get_object(pk)).data)

    @extend_schema(
        request=FloorUpdateSerializer,
        responses={200: FloorOutputSerializer, 409: CONFLICT_RESPONSE},
        description="ADMIN only. parking_lot is immutable.",
        tags=["Parking configuration"],
    )
    def patch(self, request: Request, pk: int) -> Response:
        serializer = FloorUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        floor = update_floor(floor=self.get_object(pk), data=serializer.validated_data)
        return Response(FloorOutputSerializer(floor).data)


class GateListCreateView(GenericAPIView):
    permission_classes = [CanReadOrManageParkingConfiguration]
    pagination_class = ParkingPagination
    serializer_class = GateOutputSerializer

    @extend_schema(
        parameters=[GateFilterSerializer],
        responses={200: GateOutputSerializer(many=True)},
        tags=["Parking configuration"],
    )
    def get(self, request: Request) -> Response:
        query = GateFilterSerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        page = self.paginate_queryset(gate_list(**selector_filters(query.validated_data)))
        return self.get_paginated_response(GateOutputSerializer(page, many=True).data)

    @extend_schema(
        request=GateCreateSerializer,
        responses={201: GateOutputSerializer, 409: CONFLICT_RESPONSE},
        description="ADMIN only. The parent lot must be active.",
        tags=["Parking configuration"],
    )
    def post(self, request: Request) -> Response:
        serializer = GateCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        gate = create_gate(data=serializer.validated_data)
        return Response(GateOutputSerializer(gate).data, status=status.HTTP_201_CREATED)


class GateDetailView(APIView):
    permission_classes = [CanReadOrManageParkingConfiguration]

    def get_object(self, pk: int) -> Gate:
        return get_object_or_404(Gate.objects.select_related("parking_lot"), pk=pk)

    @extend_schema(responses={200: GateOutputSerializer}, tags=["Parking configuration"])
    def get(self, request: Request, pk: int) -> Response:
        return Response(GateOutputSerializer(self.get_object(pk)).data)

    @extend_schema(
        request=GateUpdateSerializer,
        responses={200: GateOutputSerializer, 409: CONFLICT_RESPONSE},
        description="ADMIN only. parking_lot is immutable.",
        tags=["Parking configuration"],
    )
    def patch(self, request: Request, pk: int) -> Response:
        serializer = GateUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        gate = update_gate(gate=self.get_object(pk), data=serializer.validated_data)
        return Response(GateOutputSerializer(gate).data)


class ParkingSpotListCreateView(GenericAPIView):
    permission_classes = [CanReadOrManageParkingConfiguration]
    pagination_class = ParkingPagination
    serializer_class = ParkingSpotOutputSerializer

    @extend_schema(
        parameters=[ParkingSpotFilterSerializer],
        responses={200: ParkingSpotOutputSerializer(many=True)},
        description=(
            "Lists configured spots. ENABLED is an operational state, not live occupancy or "
            "availability."
        ),
        tags=["Parking configuration"],
    )
    def get(self, request: Request) -> Response:
        query = ParkingSpotFilterSerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        page = self.paginate_queryset(parking_spot_list(**selector_filters(query.validated_data)))
        return self.get_paginated_response(ParkingSpotOutputSerializer(page, many=True).data)

    @extend_schema(
        request=ParkingSpotCreateSerializer,
        responses={201: ParkingSpotOutputSerializer, 409: CONFLICT_RESPONSE},
        description="ADMIN only. The floor and its lot must both be active.",
        tags=["Parking configuration"],
    )
    def post(self, request: Request) -> Response:
        serializer = ParkingSpotCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        parking_spot = create_parking_spot(data=serializer.validated_data)
        return Response(
            ParkingSpotOutputSerializer(parking_spot).data,
            status=status.HTTP_201_CREATED,
        )


class ParkingSpotDetailView(APIView):
    permission_classes = [CanReadOrManageParkingConfiguration]

    def get_object(self, pk: int) -> ParkingSpot:
        return get_object_or_404(
            ParkingSpot.objects.select_related("floor", "floor__parking_lot"), pk=pk
        )

    @extend_schema(responses={200: ParkingSpotOutputSerializer}, tags=["Parking configuration"])
    def get(self, request: Request, pk: int) -> Response:
        return Response(ParkingSpotOutputSerializer(self.get_object(pk)).data)

    @extend_schema(
        request=ParkingSpotUpdateSerializer,
        responses={200: ParkingSpotOutputSerializer, 409: CONFLICT_RESPONSE},
        description=(
            "ADMIN only. floor is immutable. Restrictions for occupied spots belong to Phase 4."
        ),
        tags=["Parking configuration"],
    )
    def patch(self, request: Request, pk: int) -> Response:
        serializer = ParkingSpotUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        parking_spot = update_parking_spot(
            parking_spot=self.get_object(pk), data=serializer.validated_data
        )
        return Response(ParkingSpotOutputSerializer(parking_spot).data)


class VehicleListCreateView(GenericAPIView):
    permission_classes = [IsAuthenticated]
    pagination_class = ParkingPagination
    serializer_class = VehicleOutputSerializer

    @extend_schema(
        parameters=[VehicleFilterSerializer],
        responses={200: VehicleOutputSerializer(many=True)},
        description="List only vehicles associated with the authenticated account.",
        tags=["Vehicles"],
    )
    def get(self, request: Request) -> Response:
        query = VehicleFilterSerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        page = self.paginate_queryset(
            vehicle_list(owner_id=request.user.pk, **selector_filters(query.validated_data))
        )
        return self.get_paginated_response(VehicleOutputSerializer(page, many=True).data)

    @extend_schema(
        request=VehicleCreateSerializer,
        responses={201: VehicleOutputSerializer, 409: CONFLICT_RESPONSE},
        examples=[
            OpenApiExample(
                "Associate vehicle",
                value={"registration_number": "ka-01 ab 1234", "vehicle_type": "CAR"},
                request_only=True,
            )
        ],
        description=(
            "Associate a vehicle with the authenticated account. This is not verification of legal "
            "ownership; owner is assigned from the access token."
        ),
        tags=["Vehicles"],
    )
    def post(self, request: Request) -> Response:
        serializer = VehicleCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        vehicle = create_vehicle(owner=request.user, data=serializer.validated_data)
        return Response(VehicleOutputSerializer(vehicle).data, status=status.HTTP_201_CREATED)


class VehicleDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get_object(self, *, owner_id: int, pk: int) -> Vehicle:
        return get_object_or_404(
            Vehicle.objects.select_related("owner"),
            owner_id=owner_id,
            pk=pk,
        )

    @extend_schema(responses={200: VehicleOutputSerializer}, tags=["Vehicles"])
    def get(self, request: Request, pk: int) -> Response:
        vehicle = self.get_object(owner_id=request.user.pk, pk=pk)
        return Response(VehicleOutputSerializer(vehicle).data)

    @extend_schema(
        request=VehicleUpdateSerializer,
        responses={200: VehicleOutputSerializer, 409: CONFLICT_RESPONSE},
        description="Update an owned vehicle. owner cannot be supplied or changed.",
        tags=["Vehicles"],
    )
    def patch(self, request: Request, pk: int) -> Response:
        serializer = VehicleUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        vehicle = update_vehicle(
            vehicle=self.get_object(owner_id=request.user.pk, pk=pk),
            data=serializer.validated_data,
        )
        return Response(VehicleOutputSerializer(vehicle).data)
