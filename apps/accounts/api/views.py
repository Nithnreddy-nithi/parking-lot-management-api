from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiExample, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.generics import GenericAPIView
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.serializers import (
    TokenObtainPairSerializer,
    TokenRefreshSerializer,
)
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from apps.accounts.api.serializers import (
    AccessTokenResponseSerializer,
    AdminUserCreateSerializer,
    AdminUserUpdateSerializer,
    ChangePasswordSerializer,
    LogoutSerializer,
    ProfileUpdateSerializer,
    RegistrationSerializer,
    SafeUserSerializer,
    TokenPairResponseSerializer,
    UserListQuerySerializer,
)
from apps.accounts.api.throttles import RegistrationThrottle, TokenThrottle
from apps.accounts.models import User
from apps.accounts.permissions import IsAdminRole
from apps.accounts.selectors import user_list
from apps.accounts.services import (
    blacklist_refresh_token,
    change_password,
    create_managed_user,
    register_customer,
    update_managed_user,
    update_profile,
)


class UserPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class RegistrationView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [RegistrationThrottle]

    @extend_schema(
        request=RegistrationSerializer,
        responses={201: SafeUserSerializer},
        description=(
            "Register a CUSTOMER account. Application role, Django privilege flags, and active "
            "status cannot be supplied."
        ),
        examples=[
            OpenApiExample(
                "Customer registration",
                value={
                    "username": "alice",
                    "email": "alice@example.com",
                    "first_name": "Alice",
                    "last_name": "Example",
                    "password": "C0mpl3x!Parking-2026",
                    "password_confirm": "C0mpl3x!Parking-2026",
                },
                request_only=True,
            ),
        ],
        tags=["Authentication"],
    )
    def post(self, request: Request) -> Response:
        serializer = RegistrationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = register_customer(data=serializer.validated_data)
        return Response(SafeUserSerializer(user).data, status=status.HTTP_201_CREATED)


class LoginView(TokenObtainPairView):
    permission_classes = [AllowAny]
    throttle_classes = [TokenThrottle]
    serializer_class = TokenObtainPairSerializer

    @extend_schema(
        request=TokenObtainPairSerializer,
        responses={200: TokenPairResponseSerializer},
        description="Authenticate with username and password and receive an access/refresh pair.",
        examples=[
            OpenApiExample(
                "Username login",
                value={"username": "alice", "password": "C0mpl3x!Parking-2026"},
                request_only=True,
            )
        ],
        tags=["Authentication"],
    )
    def post(self, request: Request, *args, **kwargs) -> Response:
        return super().post(request, *args, **kwargs)


class RefreshView(TokenRefreshView):
    permission_classes = [AllowAny]
    throttle_classes = [TokenThrottle]
    serializer_class = TokenRefreshSerializer

    @extend_schema(
        request=TokenRefreshSerializer,
        responses={200: AccessTokenResponseSerializer},
        description=(
            "Rotate a refresh token and return a new access and refresh token. The replaced "
            "refresh token is blacklisted."
        ),
        examples=[
            OpenApiExample(
                "Rotate refresh token",
                value={"refresh": "<refresh-token>"},
                request_only=True,
            )
        ],
        tags=["Authentication"],
    )
    def post(self, request: Request, *args, **kwargs) -> Response:
        return super().post(request, *args, **kwargs)


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=LogoutSerializer,
        responses={204: OpenApiResponse(description="Refresh token blacklisted.")},
        description=(
            "Blacklist a refresh token belonging to the authenticated user. Already issued "
            "access tokens remain valid until their short expiry."
        ),
        examples=[
            OpenApiExample(
                "Logout",
                value={"refresh": "<refresh-token>"},
                request_only=True,
            )
        ],
        tags=["Authentication"],
    )
    def post(self, request: Request) -> Response:
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        blacklist_refresh_token(
            user=request.user,
            raw_token=serializer.validated_data["refresh"],
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: SafeUserSerializer}, tags=["Users"])
    def get(self, request: Request) -> Response:
        return Response(SafeUserSerializer(request.user).data)

    @extend_schema(
        request=ProfileUpdateSerializer,
        responses={200: SafeUserSerializer},
        description=(
            "Update first_name and last_name only. Username, password, role, active status, and "
            "Django privilege flags are protected."
        ),
        examples=[
            OpenApiExample(
                "Profile names",
                value={"first_name": "Alicia", "last_name": "Example"},
                request_only=True,
            )
        ],
        tags=["Users"],
    )
    def patch(self, request: Request) -> Response:
        serializer = ProfileUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        user = update_profile(user=request.user, data=serializer.validated_data)
        return Response(SafeUserSerializer(user).data)


class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=ChangePasswordSerializer,
        responses={204: OpenApiResponse(description="Password changed.")},
        description=(
            "Change the password after verifying the current password and revoke every outstanding "
            "refresh token. Existing access tokens remain usable until their short expiry."
        ),
        tags=["Users"],
    )
    def post(self, request: Request) -> Response:
        serializer = ChangePasswordSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        change_password(user=request.user, new_password=serializer.validated_data["new_password"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class AdminUserListCreateView(GenericAPIView):
    permission_classes = [IsAdminRole]
    pagination_class = UserPagination
    serializer_class = SafeUserSerializer

    @extend_schema(
        parameters=[UserListQuerySerializer],
        responses={200: SafeUserSerializer(many=True)},
        description="List users with optional role and active-status filters.",
        tags=["User administration"],
    )
    def get(self, request: Request) -> Response:
        query = UserListQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        queryset = user_list(**query.validated_data)
        page = self.paginate_queryset(queryset)
        serializer = SafeUserSerializer(page, many=True)
        return self.get_paginated_response(serializer.data)

    @extend_schema(
        request=AdminUserCreateSerializer,
        responses={201: SafeUserSerializer},
        description=(
            "Create a CUSTOMER or OPERATOR. ADMIN accounts must be bootstrapped with the "
            "documented management command or Django admin."
        ),
        tags=["User administration"],
    )
    def post(self, request: Request) -> Response:
        serializer = AdminUserCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = create_managed_user(data=serializer.validated_data)
        return Response(SafeUserSerializer(user).data, status=status.HTTP_201_CREATED)


class AdminUserDetailView(APIView):
    permission_classes = [IsAdminRole]

    def get_user(self, user_id: int) -> User:
        return get_object_or_404(User, pk=user_id)

    @extend_schema(responses={200: SafeUserSerializer}, tags=["User administration"])
    def get(self, request: Request, user_id: int) -> Response:
        return Response(SafeUserSerializer(self.get_user(user_id)).data)

    @extend_schema(
        request=AdminUserUpdateSerializer,
        responses={200: SafeUserSerializer},
        description=(
            "Update profile fields, switch between CUSTOMER and OPERATOR, or change active status. "
            "ADMIN and superuser accounts cannot be edited through this endpoint."
        ),
        tags=["User administration"],
    )
    def patch(self, request: Request, user_id: int) -> Response:
        serializer = AdminUserUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        user = update_managed_user(
            user=self.get_user(user_id),
            data=serializer.validated_data,
        )
        return Response(SafeUserSerializer(user).data)
