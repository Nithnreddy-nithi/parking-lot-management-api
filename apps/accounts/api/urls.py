from django.urls import path

from apps.accounts.api.views import (
    AdminUserDetailView,
    AdminUserListCreateView,
    ChangePasswordView,
    LoginView,
    LogoutView,
    MeView,
    RefreshView,
    RegistrationView,
)

urlpatterns = [
    path("auth/register/", RegistrationView.as_view(), name="auth-register"),
    path("auth/token/", LoginView.as_view(), name="auth-token"),
    path("auth/token/refresh/", RefreshView.as_view(), name="auth-token-refresh"),
    path("auth/logout/", LogoutView.as_view(), name="auth-logout"),
    path("users/me/", MeView.as_view(), name="user-me"),
    path("users/me/change-password/", ChangePasswordView.as_view(), name="user-change-password"),
    path("users/", AdminUserListCreateView.as_view(), name="user-list"),
    path("users/<int:user_id>/", AdminUserDetailView.as_view(), name="user-detail"),
]
