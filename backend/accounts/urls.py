from django.urls import path

from rest_framework_simplejwt.views import (
    TokenBlacklistView,
    TokenObtainPairView,
    TokenRefreshView,
)

from .views import (
    CurrentUserProfileView,
    DriverRegistrationView,
    PassengerRegistrationView,
    DriverPasswordChangeView,
    DriverTemporaryPasswordResetView,
    DriverManagementListView,
    PasswordResetConfirmView,
    PasswordResetRequestView,
    AccountPasswordChangeView,
    EmailVerificationResendView,
    EmailVerificationView,
    TaxiLinkTokenObtainPairView,
)


urlpatterns = [
    path(
    "change-password/",
    AccountPasswordChangeView.as_view(),
    name="account-change-password",
    ),

    path(
    "verify-email/",
    EmailVerificationView.as_view(),
    name="email-verify",
    ),

    path(
        "verify-email/resend/",
        EmailVerificationResendView.as_view(),
        name="email-verification-resend",
    ),

    path(
    "password-reset/",
    PasswordResetRequestView.as_view(),
    name="password-reset",
    ),

    path(
    "password-reset/confirm/",
    PasswordResetConfirmView.as_view(),
    name="password-reset-confirm",
    ),
    path(
    "drivers/",
    DriverManagementListView.as_view(),
    name="driver-management-list",
    ),

    path(
    "drivers/<int:pk>/reset-temporary-password/",
    DriverTemporaryPasswordResetView.as_view(),
    name="driver-reset-temporary-password",
    ),

    path(
        "register/",
        PassengerRegistrationView.as_view(),
        name="passenger-register",
    ),

    path(
        "drivers/register/",
        DriverRegistrationView.as_view(),
        name="driver-register",
    ),

    path(
        "login/",
        TaxiLinkTokenObtainPairView.as_view(),
        name="token-obtain-pair",
    ),

    path(
        "token/refresh/",
        TokenRefreshView.as_view(),
        name="token-refresh",
    ),

    path(
        "logout/",
        TokenBlacklistView.as_view(),
        name="token-blacklist",
    ),

    path(
        "me/",
        CurrentUserProfileView.as_view(),
        name="current-user-profile",
    ),

    path(
    "drivers/change-password/",
    DriverPasswordChangeView.as_view(),
    name="driver-change-password",
    ),
]