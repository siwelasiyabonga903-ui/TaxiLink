from django.contrib.auth import get_user_model

from rest_framework import generics
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import (AllowAny,BasePermission,IsAuthenticated,)
from django.conf import settings
from django.contrib.auth.tokens import (default_token_generator,)
from django.core.mail import send_mail
from django.utils.encoding import (force_bytes, force_str,)
from django.utils.http import (urlsafe_base64_encode, urlsafe_base64_decode,)
from django.shortcuts import redirect
from rest_framework.views import APIView
from rest_framework_simplejwt.views import (TokenObtainPairView,)
from .email_service import (send_driver_credentials_email,send_verification_email,)

from .serializers import (
    DriverPasswordChangeSerializer,
    DriverRegistrationSerializer,
    DriverManagementSerializer,
    PassengerRegistrationSerializer,
    UserProfileSerializer,
    generate_temporary_password,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    AccountPasswordChangeSerializer,
    TaxiLinkTokenObtainPairSerializer,
)


User = get_user_model()


class IsDispatcher(BasePermission):
    def has_permission(
        self,
        request,
        view,
    ):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.role
            == User.Role.DISPATCHER
        )


class PassengerRegistrationView(
    generics.CreateAPIView
):
    serializer_class = (
        PassengerRegistrationSerializer
    )

    permission_classes = [
        AllowAny
    ]
    def create(
        self,
        request,
        *args,
        **kwargs,
    ):
        serializer = self.get_serializer(
            data=request.data
        )

        serializer.is_valid(
            raise_exception=True
        )

        user = serializer.save()

        email_sent = (
            send_verification_email(
                user,
                request,
            )
        )

        response_data = dict(
            serializer.data
        )

        response_data.update(
            {
                "email_sent": email_sent,

                "detail": (
                    "Registration successful. "
                    "Check your email to confirm "
                    "your account."
                    if email_sent
                    else (
                        "Registration successful, "
                        "but the confirmation email "
                        "could not be sent. Request "
                        "another confirmation email."
                    )
                ),
            }
        )

        return Response(
            response_data,
            status=status.HTTP_201_CREATED,
            headers=self.get_success_headers(
                serializer.data
            ),
        )


class DriverRegistrationView(
    generics.CreateAPIView
):
    serializer_class = (
        DriverRegistrationSerializer
    )

    permission_classes = [
        IsAuthenticated,
        IsDispatcher,
    ]
    def create(
        self,
        request,
        *args,
        **kwargs,
    ):
        serializer = self.get_serializer(
            data=request.data
        )

        serializer.is_valid(
            raise_exception=True
        )

        driver = serializer.save()

        response_data = dict(
            serializer.data
        )

        temporary_password = (
            response_data[
                "temporary_password"
            ]
        )

        email_sent = (
            send_driver_credentials_email(
                driver,
                temporary_password,
                request,
            )
        )

        response_data[
            "email_sent"
        ] = email_sent

        response_data["detail"] = (
            "Driver created and credentials "
            "emailed successfully."
            if email_sent
            else (
                "Driver created, but the "
                "credential email could not be "
                "sent. Give the displayed "
                "temporary password to the "
                "driver securely."
            )
        )

        return Response(
            response_data,
            status=status.HTTP_201_CREATED,
            headers=self.get_success_headers(
                serializer.data
            ),
        )

class TaxiLinkTokenObtainPairView(
    TokenObtainPairView
):
    serializer_class = (
        TaxiLinkTokenObtainPairSerializer
    )


class EmailVerificationView(
    APIView
):
    permission_classes = [
        AllowAny
    ]

    def get(self, request):
        uid = request.query_params.get(
            "uid",
            "",
        )

        token = (
            request.query_params.get(
                "token",
                "",
            )
        )

        try:
            user_id = force_str(
                urlsafe_base64_decode(
                    uid
                )
            )

            user = User.objects.get(
                pk=user_id
            )
        except (
            TypeError,
            ValueError,
            OverflowError,
            User.DoesNotExist,
        ):
            return redirect(
                f"{settings.FRONTEND_URL}"
                "/login?verification=invalid"
            )

        if user.email_verified:
            return redirect(
                f"{settings.FRONTEND_URL}"
                "/login?verification=already"
            )

        if not (
            default_token_generator
            .check_token(
                user,
                token,
            )
        ):
            return redirect(
                f"{settings.FRONTEND_URL}"
                "/login?verification=invalid"
            )

        user.email_verified = True

        user.save(
            update_fields=[
                "email_verified"
            ]
        )

        return redirect(
            f"{settings.FRONTEND_URL}"
            "/login?verification=success"
        )


class EmailVerificationResendView(
    generics.GenericAPIView
):
    serializer_class = (
        PasswordResetRequestSerializer
    )

    permission_classes = [
        AllowAny
    ]

    def post(self, request):
        serializer = self.get_serializer(
            data=request.data
        )

        serializer.is_valid(
            raise_exception=True
        )

        user = User.objects.filter(
            email__iexact=(
                serializer.validated_data[
                    "email"
                ]
            ),
            is_active=True,
            email_verified=False,
        ).first()

        if user:
            email_sent = (
                send_verification_email(
                    user,
                    request,
                )
            )

            if not email_sent:
                return Response(
                    {
                        "detail": (
                            "Confirmation email "
                            "could not be sent right "
                            "now. Please try again later."
                        )
                    },
                    status=(
                        status
                        .HTTP_503_SERVICE_UNAVAILABLE
                    ),
                )

        return Response(
            {
                "detail": (
                    "If an unverified account "
                    "exists for this email, a "
                    "confirmation link has been sent."
                )
            }
        )

class CurrentUserProfileView(
    generics.RetrieveUpdateAPIView
):
    serializer_class = (
        UserProfileSerializer
    )

    permission_classes = [
        IsAuthenticated
    ]

    def get_object(self):
        return self.request.user

class DriverPasswordChangeView(
    generics.GenericAPIView
):
    serializer_class = (
        DriverPasswordChangeSerializer
    )

    permission_classes = [
        IsAuthenticated
    ]

    def post(self, request):
        if request.user.role != User.Role.DRIVER:
            

            return Response(
                {
                    "detail": (
                        "Only drivers can use "
                        "this password-change endpoint."
                    )
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = self.get_serializer(
            data=request.data,
            context={
                "request": request,
            },
        )

        serializer.is_valid(
            raise_exception=True
        )

        serializer.save()

        return Response(
            {
                "detail": (
                    "Password changed successfully."
                ),
                "must_change_password": False,
            }
        )

class DriverTemporaryPasswordResetView(
    generics.GenericAPIView
):
    permission_classes = [
        IsAuthenticated,
        IsDispatcher,
    ]

    def post(self, request, pk):
        driver = User.objects.filter(
            pk=pk,
            role=User.Role.DRIVER,
        ).first()

        if driver is None:
            return Response(
                {
                    "detail": (
                        "Driver not found."
                    )
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        if not driver.must_change_password:
            return Response(
                {
                    "detail": (
                        "Temporary password can only "
                        "be reset before the driver "
                        "completes password setup."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        temporary_password = (
            generate_temporary_password()
        )

        driver.set_password(
            temporary_password
        )

        driver.must_change_password = True

        driver.save(
            update_fields=[
                "password",
                "must_change_password",
            ]
        )

        email_sent = (
            send_driver_credentials_email(
                driver,
                temporary_password,
                request,
            )
        )

        return Response(
            {
                "detail": (
                    "Temporary password reset and "
                    "emailed successfully."
                    if email_sent
                    else (
                        "Temporary password reset, but "
                        "the email could not be sent. "
                        "Give the displayed password to "
                        "the driver securely."
                    )
                ),

                "email_sent": email_sent,

                "driver_id": driver.id,

                "email": driver.email,

                "temporary_password": (
                    temporary_password
                ),
            }
        )

class DriverManagementListView(
    generics.ListAPIView
):
    serializer_class = (
        DriverManagementSerializer
    )

    permission_classes = [
        IsAuthenticated,
        IsDispatcher,
    ]

    def get_queryset(self):
        return User.objects.filter(
            role=User.Role.DRIVER
        ).order_by(
            "first_name",
            "last_name",
            "email",
        )

class PasswordResetRequestView(
    generics.GenericAPIView
):
    serializer_class = (
        PasswordResetRequestSerializer
    )

    permission_classes = [
        AllowAny
    ]

    def post(self, request):
        serializer = self.get_serializer(
            data=request.data
        )

        serializer.is_valid(
            raise_exception=True
        )

        email = serializer.validated_data[
            "email"
        ]

        user = User.objects.filter(
            email__iexact=email,
            is_active=True,
        ).first()

        if user:
            uid = urlsafe_base64_encode(
                force_bytes(user.pk)
            )

            token = (
                default_token_generator
                .make_token(user)
            )

            frontend_url = (
                settings.FRONTEND_URL.rstrip("/")
            )

            reset_url = (
                f"{frontend_url}"
                f"/reset-password"
                f"?uid={uid}"
                f"&token={token}"
            )

            send_mail(
                subject=(
                    "Reset your TaxiLink password"
                ),
                message=(
                    "A password reset was requested "
                    "for your TaxiLink account.\n\n"
                    "Use the link below to choose "
                    "a new password:\n\n"
                    f"{reset_url}\n\n"
                    "If you did not request this, "
                    "you can ignore this email."
                ),
                from_email=(
                    settings.DEFAULT_FROM_EMAIL
                ),
                recipient_list=[
                    user.email
                ],
                fail_silently=False,
            )

        return Response(
            {
                "detail": (
                    "If an account exists for "
                    "this email, password reset "
                    "instructions have been sent."
                )
            },
            status=status.HTTP_200_OK,
        )

class PasswordResetConfirmView(
    generics.GenericAPIView
):
    serializer_class = (
        PasswordResetConfirmSerializer
    )

    permission_classes = [
        AllowAny
    ]

    def post(self, request):
        serializer = self.get_serializer(
            data=request.data
        )

        serializer.is_valid(
            raise_exception=True
        )

        serializer.save()

        return Response(
            {
                "detail": (
                    "Password reset successfully. "
                    "You can now log in with your "
                    "new password."
                )
            },
            status=status.HTTP_200_OK,
        )

class AccountPasswordChangeView(
    generics.GenericAPIView
):
    serializer_class = (
        AccountPasswordChangeSerializer
    )

    permission_classes = [
        IsAuthenticated
    ]

    def post(self, request):
        if (
            request.user.role
            == User.Role.DRIVER
            and request.user.must_change_password
        ):
            return Response(
                {
                    "detail": (
                        "You must complete your "
                        "temporary password setup first."
                    )
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = self.get_serializer(
            data=request.data,
            context={
                "request": request,
            },
        )

        serializer.is_valid(
            raise_exception=True
        )

        serializer.save()

        return Response(
            {
                "detail": (
                    "Password changed successfully."
                )
            },
            status=status.HTTP_200_OK,
        )