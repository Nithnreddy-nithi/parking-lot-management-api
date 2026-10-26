from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiExample, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.generics import GenericAPIView
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.accounts.permissions import IsAdminOrOperatorRole
from apps.parking.models import ParkingLot
from apps.payments.api.serializers import EmptySettlementSerializer, SettlementOutputSerializer
from apps.payments.composition import build_zero_charge_settlement_service
from apps.pricing.api.serializers import CheckoutQuoteOutputSerializer, EmptyCheckoutSerializer
from apps.pricing.exceptions import QuoteNotFound
from apps.pricing.selectors import quote_for_session
from apps.sessions.api.serializers import (
    AvailabilitySerializer,
    EntryRequestSerializer,
    ExitRequestSerializer,
    ParkingSessionOutputSerializer,
    SessionFilterSerializer,
)
from apps.sessions.selectors import availability_by_spot_type, session_list
from apps.sessions.services import build_checkout_service, build_entry_service, build_exit_service


class SessionPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


def _is_staff_reader(user) -> bool:
    return user.is_superuser or user.role in {User.Role.ADMIN, User.Role.OPERATOR}


def _selector_filters(validated_data: dict) -> dict:
    return {
        "status": validated_data.get("status"),
        "lot_id": validated_data.get("lot"),
        "entry_date_from": validated_data.get("entry_date_from"),
        "entry_date_to": validated_data.get("entry_date_to"),
        "vehicle_id": validated_data.get("vehicle"),
    }


class ParkingEntryView(APIView):
    permission_classes = [IsAdminOrOperatorRole]

    @extend_schema(
        request=EntryRequestSerializer,
        responses={
            201: ParkingSessionOutputSerializer,
            409: OpenApiResponse(description="A stable parking-entry business conflict."),
        },
        examples=[
            OpenApiExample(
                "Admit registered vehicle",
                value={"vehicle_id": 7, "entry_gate_id": 2},
                request_only=True,
            )
        ],
        description=(
            "ADMIN or OPERATOR only. The server selects and locks a compatible spot, records "
            "snapshots, and issues an unguessable ticket. Repeating a successful request conflicts."
        ),
        tags=["Parking sessions"],
    )
    def post(self, request: Request) -> Response:
        serializer = EntryRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        parking_session = build_entry_service().enter(
            vehicle_id=serializer.validated_data["vehicle_id"],
            entry_gate_id=serializer.validated_data["entry_gate_id"],
            actor=request.user,
        )
        return Response(
            ParkingSessionOutputSerializer(parking_session).data,
            status=status.HTTP_201_CREATED,
        )


class ParkingSessionListView(GenericAPIView):
    permission_classes = [IsAuthenticated]
    pagination_class = SessionPagination
    serializer_class = ParkingSessionOutputSerializer

    @extend_schema(
        parameters=[SessionFilterSerializer],
        responses={200: ParkingSessionOutputSerializer(many=True)},
        description=(
            "ADMIN and OPERATOR see all sessions. CUSTOMER results are ownership-scoped before "
            "validated filters are applied. Only staff may filter by vehicle."
        ),
        tags=["Parking sessions"],
    )
    def get(self, request: Request) -> Response:
        query = SessionFilterSerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        staff_reader = _is_staff_reader(request.user)
        if not staff_reader and "vehicle" in query.validated_data:
            raise ValidationError({"vehicle": "This filter is available to staff only."})
        queryset = session_list(
            owner_id=None if staff_reader else request.user.pk,
            **_selector_filters(query.validated_data),
        )
        page = self.paginate_queryset(queryset)
        return self.get_paginated_response(ParkingSessionOutputSerializer(page, many=True).data)


class ParkingSessionDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        responses={200: ParkingSessionOutputSerializer},
        description="Customers receive 404 for sessions belonging to another account.",
        tags=["Parking sessions"],
    )
    def get(self, request: Request, pk: int) -> Response:
        owner_id = None if _is_staff_reader(request.user) else request.user.pk
        parking_session = get_object_or_404(session_list(owner_id=owner_id), pk=pk)
        return Response(ParkingSessionOutputSerializer(parking_session).data)


class ParkingSessionCheckoutView(APIView):
    permission_classes = [IsAdminOrOperatorRole]

    @extend_schema(
        request=EmptyCheckoutSerializer,
        responses={
            200: CheckoutQuoteOutputSerializer,
            409: OpenApiResponse(description="Pricing or session-state business conflict."),
        },
        description=(
            "ADMIN or OPERATOR only. Atomically freezes the fee quote and transitions ACTIVE to "
            "PAYMENT_PENDING. Repeated checkout returns the original quote."
        ),
        tags=["Parking sessions"],
    )
    def post(self, request: Request, pk: int) -> Response:
        serializer = EmptyCheckoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        quote = build_checkout_service().checkout(session_id=pk, actor=request.user)
        return Response(CheckoutQuoteOutputSerializer(quote).data)


class ParkingSessionQuoteView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        responses={200: CheckoutQuoteOutputSerializer},
        description=(
            "ADMIN and OPERATOR may read all quotes. Customers may read only quotes for sessions "
            "associated with their vehicles."
        ),
        tags=["Parking sessions"],
    )
    def get(self, request: Request, pk: int) -> Response:
        owner_id = None if _is_staff_reader(request.user) else request.user.pk
        parking_session = get_object_or_404(session_list(owner_id=owner_id), pk=pk)
        quote = quote_for_session(session_id=parking_session.pk)
        if quote is None:
            raise QuoteNotFound()
        return Response(CheckoutQuoteOutputSerializer(quote).data)


class ParkingSessionZeroSettlementView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=EmptySettlementSerializer,
        responses={
            200: SettlementOutputSerializer,
            409: OpenApiResponse(description="Settlement or session-state conflict."),
        },
        description=(
            "Settles a zero-amount frozen quote without creating a payment attempt or contacting "
            "the provider. Customers may settle only their own sessions."
        ),
        tags=["Payments"],
    )
    def post(self, request: Request, pk: int) -> Response:
        serializer = EmptySettlementSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        owner_id = None if _is_staff_reader(request.user) else request.user.pk
        get_object_or_404(session_list(owner_id=owner_id), pk=pk)
        settlement = build_zero_charge_settlement_service().settle(session_id=pk)
        return Response(SettlementOutputSerializer(settlement).data)


class ParkingSessionExitView(APIView):
    permission_classes = [IsAdminOrOperatorRole]

    @extend_schema(
        request=ExitRequestSerializer,
        responses={
            200: ParkingSessionOutputSerializer,
            409: OpenApiResponse(description="Exit or settlement-state conflict."),
        },
        examples=[
            OpenApiExample(
                "Record vehicle exit",
                value={"exit_gate_id": 3},
                request_only=True,
            )
        ],
        description=(
            "ADMIN or OPERATOR only. Requires a valid settlement, closes the session, and releases "
            "occupancy atomically. Repeating the same exit preserves its original metadata."
        ),
        tags=["Parking sessions"],
    )
    def post(self, request: Request, pk: int) -> Response:
        serializer = ExitRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        parking_session = build_exit_service().exit(
            session_id=pk,
            exit_gate_id=serializer.validated_data["exit_gate_id"],
            actor=request.user,
        )
        return Response(ParkingSessionOutputSerializer(parking_session).data)


class ParkingAvailabilityView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        responses={200: AvailabilitySerializer},
        description=(
            "Informational counts only. Availability does not reserve a spot; only the "
            "transactional entry endpoint performs allocation."
        ),
        tags=["Parking availability"],
    )
    def get(self, request: Request, pk: int) -> Response:
        parking_lot = get_object_or_404(ParkingLot.objects.only("id"), pk=pk)
        payload = {
            "parking_lot_id": parking_lot.pk,
            "counts": availability_by_spot_type(lot_id=parking_lot.pk),
        }
        return Response(AvailabilitySerializer(payload).data)
