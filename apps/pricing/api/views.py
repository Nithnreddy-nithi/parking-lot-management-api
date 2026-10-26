from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiExample, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.generics import GenericAPIView
from rest_framework.pagination import PageNumberPagination
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsAdminRole
from apps.pricing.api.serializers import (
    PricingPolicyCreateSerializer,
    PricingPolicyFilterSerializer,
    PricingPolicyOutputSerializer,
)
from apps.pricing.models import PricingPolicy
from apps.pricing.selectors import pricing_policy_list
from apps.pricing.services import publish_policy, retire_policy


class PricingPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


def _filters(data: dict) -> dict:
    return {
        "lot_id": data.get("lot"),
        "vehicle_type": data.get("vehicle_type"),
        "is_active": data.get("is_active"),
    }


class PricingPolicyListCreateView(GenericAPIView):
    permission_classes = [IsAdminRole]
    pagination_class = PricingPagination
    serializer_class = PricingPolicyOutputSerializer

    @extend_schema(
        parameters=[PricingPolicyFilterSerializer],
        responses={200: PricingPolicyOutputSerializer(many=True)},
        tags=["Pricing"],
    )
    def get(self, request: Request) -> Response:
        query = PricingPolicyFilterSerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        page = self.paginate_queryset(pricing_policy_list(**_filters(query.validated_data)))
        return self.get_paginated_response(PricingPolicyOutputSerializer(page, many=True).data)

    @extend_schema(
        request=PricingPolicyCreateSerializer,
        responses={
            201: PricingPolicyOutputSerializer,
            409: OpenApiResponse(description="Lot or concurrent publication conflict."),
        },
        examples=[
            OpenApiExample(
                "Publish car pricing",
                value={
                    "parking_lot": 1,
                    "vehicle_type": "CAR",
                    "currency": "INR",
                    "hourly_rate": "30.00",
                    "grace_minutes": 15,
                    "daily_cap": "300.00",
                },
                request_only=True,
            )
        ],
        description=(
            "ADMIN only. Publishes the next server-assigned version and atomically retires the "
            "previous active policy for the same lot and vehicle type."
        ),
        tags=["Pricing"],
    )
    def post(self, request: Request) -> Response:
        serializer = PricingPolicyCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        policy = publish_policy(data=serializer.validated_data, actor=request.user)
        return Response(PricingPolicyOutputSerializer(policy).data, status=status.HTTP_201_CREATED)


class PricingPolicyDetailView(APIView):
    permission_classes = [IsAdminRole]

    @extend_schema(responses={200: PricingPolicyOutputSerializer}, tags=["Pricing"])
    def get(self, request: Request, pk: int) -> Response:
        policy = get_object_or_404(
            PricingPolicy.objects.select_related("parking_lot"),
            pk=pk,
        )
        return Response(PricingPolicyOutputSerializer(policy).data)


class PricingPolicyRetireView(APIView):
    permission_classes = [IsAdminRole]

    @extend_schema(
        request=None,
        responses={200: PricingPolicyOutputSerializer},
        description=(
            "ADMIN only. Idempotently retires a policy without changing existing snapshots."
        ),
        tags=["Pricing"],
    )
    def post(self, request: Request, pk: int) -> Response:
        policy = retire_policy(policy_id=pk)
        return Response(PricingPolicyOutputSerializer(policy).data)
