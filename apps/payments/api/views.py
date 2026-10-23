from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiExample, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.generics import GenericAPIView
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.payments.api.serializers import (
    PaymentAttemptOutputSerializer,
    PaymentFilterSerializer,
    PaymentInitiationSerializer,
)
from apps.payments.composition import build_payment_initiation_service
from apps.payments.enums import PaymentStatus
from apps.payments.selectors import payment_attempts
from apps.sessions.selectors import session_list


def _is_staff(user) -> bool:
    return user.is_superuser or user.role in {User.Role.ADMIN, User.Role.OPERATOR}


class PaymentPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class PaymentListCreateView(GenericAPIView):
    permission_classes = [IsAuthenticated]
    pagination_class = PaymentPagination
    serializer_class = PaymentAttemptOutputSerializer

    @extend_schema(
        request=PaymentInitiationSerializer,
        responses={
            200: PaymentAttemptOutputSerializer,
            202: PaymentAttemptOutputSerializer,
            409: OpenApiResponse(description="Payment or session-state conflict."),
        },
        examples=[
            OpenApiExample(
                "Initiate payment",
                value={"parking_session_id": 42},
                request_only=True,
            )
        ],
        description=(
            "Creates or reuses a payment attempt for a positive frozen quote. Provider calls occur "
            "outside database transactions. A pending or uncertain result returns 202."
        ),
        tags=["Payments"],
    )
    def post(self, request: Request) -> Response:
        serializer = PaymentInitiationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        session_id = serializer.validated_data["parking_session_id"]
        owner_id = None if _is_staff(request.user) else request.user.pk
        get_object_or_404(session_list(owner_id=owner_id), pk=session_id)
        attempt = build_payment_initiation_service().initiate(
            session_id=session_id,
            actor=request.user,
        )
        response_status = (
            status.HTTP_202_ACCEPTED
            if attempt.status == PaymentStatus.PENDING
            else status.HTTP_200_OK
        )
        return Response(PaymentAttemptOutputSerializer(attempt).data, status=response_status)

    @extend_schema(
        parameters=[PaymentFilterSerializer],
        responses={200: PaymentAttemptOutputSerializer(many=True)},
        description=(
            "Staff can inspect all attempts. Customer queries are ownership-scoped before "
            "validated status and session filters are applied."
        ),
        tags=["Payments"],
    )
    def get(self, request: Request) -> Response:
        filters = PaymentFilterSerializer(data=request.query_params)
        filters.is_valid(raise_exception=True)
        owner_id = None if _is_staff(request.user) else request.user.pk
        queryset = payment_attempts(
            owner_id=owner_id,
            status=filters.validated_data.get("status"),
            session_id=filters.validated_data.get("session"),
        )
        page = self.paginate_queryset(queryset)
        return self.get_paginated_response(PaymentAttemptOutputSerializer(page, many=True).data)


class PaymentDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        responses={200: PaymentAttemptOutputSerializer},
        description="Customers receive 404 for payment attempts belonging to another account.",
        tags=["Payments"],
    )
    def get(self, request: Request, pk) -> Response:
        owner_id = None if _is_staff(request.user) else request.user.pk
        attempt = get_object_or_404(payment_attempts(owner_id=owner_id), pk=pk)
        return Response(PaymentAttemptOutputSerializer(attempt).data)
