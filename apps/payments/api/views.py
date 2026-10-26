import json

from django.conf import settings
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiExample, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.exceptions import PermissionDenied
from rest_framework.generics import GenericAPIView
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.payments.api.serializers import (
    PaymentAttemptOutputSerializer,
    PaymentConfirmationSerializer,
    PaymentFilterSerializer,
    PaymentInitiationSerializer,
    RefundInitiationSerializer,
    RefundOutputSerializer,
)
from apps.payments.composition import (
    build_payment_confirmation_service,
    build_payment_initiation_service,
    build_payment_provider,
    build_razorpay_webhook_service,
    build_refund_initiation_service,
)
from apps.payments.enums import PaymentStatus, RefundStatus
from apps.payments.exceptions import ProviderOutcomeUnknown, ProviderProtocolError
from apps.payments.selectors import payment_attempts, refunds
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


class PaymentConfirmationView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=PaymentConfirmationSerializer,
        responses={
            200: PaymentAttemptOutputSerializer,
            409: OpenApiResponse(description="Invalid or pending confirmation."),
        },
        description=(
            "Verifies the Razorpay Checkout signature, then fetches the payment from Razorpay. "
            "Only a captured payment can settle the frozen quote."
        ),
        tags=["Payments"],
    )
    def post(self, request: Request, pk) -> Response:
        owner_id = None if _is_staff(request.user) else request.user.pk
        attempt = get_object_or_404(payment_attempts(owner_id=owner_id), pk=pk)
        serializer = PaymentConfirmationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = build_payment_confirmation_service(provider_name=attempt.provider).confirm(
            attempt_id=attempt.pk,
            provider_order_reference=serializer.validated_data["razorpay_order_id"],
            provider_reference=serializer.validated_data["razorpay_payment_id"],
            signature=serializer.validated_data["razorpay_signature"],
        )
        response_status = (
            status.HTTP_202_ACCEPTED
            if result.status == PaymentStatus.PENDING
            else status.HTTP_200_OK
        )
        return Response(PaymentAttemptOutputSerializer(result).data, status=response_status)


class RefundListCreateView(GenericAPIView):
    permission_classes = [IsAuthenticated]
    pagination_class = PaymentPagination
    serializer_class = RefundOutputSerializer

    @extend_schema(
        request=RefundInitiationSerializer,
        responses={200: RefundOutputSerializer, 202: RefundOutputSerializer},
        description=(
            "Admins can create full or partial Razorpay refunds. Pending refunds reserve their "
            "amount so concurrent requests cannot over-refund a settlement."
        ),
        tags=["Refunds"],
    )
    def post(self, request: Request) -> Response:
        if not (request.user.is_superuser or request.user.role == User.Role.ADMIN):
            raise PermissionDenied("Only administrators can issue refunds.")
        serializer = RefundInitiationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        refund = build_refund_initiation_service().initiate(
            actor=request.user,
            **serializer.validated_data,
        )
        response_status = (
            status.HTTP_202_ACCEPTED
            if refund.status == RefundStatus.PENDING
            else status.HTTP_200_OK
        )
        return Response(RefundOutputSerializer(refund).data, status=response_status)

    @extend_schema(responses={200: RefundOutputSerializer(many=True)}, tags=["Refunds"])
    def get(self, request: Request) -> Response:
        owner_id = None if _is_staff(request.user) else request.user.pk
        page = self.paginate_queryset(refunds(owner_id=owner_id))
        return self.get_paginated_response(RefundOutputSerializer(page, many=True).data)


class RefundDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: RefundOutputSerializer}, tags=["Refunds"])
    def get(self, request: Request, pk) -> Response:
        owner_id = None if _is_staff(request.user) else request.user.pk
        refund = get_object_or_404(refunds(owner_id=owner_id), pk=pk)
        return Response(RefundOutputSerializer(refund).data)


class RazorpayWebhookView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(
        request=None,
        responses={200: OpenApiResponse(description="Webhook accepted or deduplicated.")},
        description=(
            "Razorpay-only endpoint. Verifies HMAC over the exact raw body before parsing and "
            "deduplicates deliveries using X-Razorpay-Event-Id."
        ),
        tags=["Payment webhooks"],
    )
    def post(self, request: Request) -> Response:
        signature = request.headers.get("X-Razorpay-Signature", "")
        event_id = request.headers.get("X-Razorpay-Event-Id", "")
        if not signature or not event_id:
            return Response(
                {
                    "error": {
                        "code": "INVALID_WEBHOOK",
                        "detail": "Required Razorpay headers are missing.",
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        body = request.body
        provider = build_payment_provider("RAZORPAY")
        try:
            provider.verify_webhook_signature(
                body=body,
                signature=signature,
                secret=settings.RAZORPAY_WEBHOOK_SECRET,
            )
            payload = json.loads(body)
            event = build_razorpay_webhook_service().process(
                event_id=event_id,
                body=body,
                payload=payload,
            )
        except (ProviderProtocolError, json.JSONDecodeError):
            return Response(
                {
                    "error": {
                        "code": "INVALID_WEBHOOK",
                        "detail": "Webhook verification failed.",
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        except ProviderOutcomeUnknown:
            return Response(
                {
                    "error": {
                        "code": "PROVIDER_UNAVAILABLE",
                        "detail": "Retry this webhook later.",
                    }
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response({"status": event.status})
