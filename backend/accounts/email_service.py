import logging
from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth.tokens import (
    default_token_generator,
)
from django.core.mail import send_mail
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import (
    urlsafe_base64_encode,
)


logger = logging.getLogger(__name__)


def build_verification_url(
    user,
    request,
):
    query = urlencode(
        {
            "uid": urlsafe_base64_encode(
                force_bytes(user.pk)
            ),
            "token": (
                default_token_generator
                .make_token(user)
            ),
        }
    )

    path = reverse(
        "email-verify"
    )

    return request.build_absolute_uri(
        f"{path}?{query}"
    )


def send_verification_email(
    user,
    request,
):
    verification_url = (
        build_verification_url(
            user,
            request,
        )
    )

    try:
        send_mail(
            subject=(
                "Confirm your TaxiLink email"
            ),
            message=(
                f"Hello "
                f"{user.first_name or user.email},\n\n"
                "Confirm your TaxiLink email "
                "address using this link:\n\n"
                f"{verification_url}\n\n"
                "If you did not create this "
                "account, you can ignore this email."
            ),
            from_email=(
                settings.DEFAULT_FROM_EMAIL
            ),
            recipient_list=[
                user.email
            ],
            fail_silently=False,
        )
    except Exception:
        logger.exception(
            (
                "Email verification delivery "
                "failed for user %s."
            ),
            user.pk,
        )

        return False

    return True


def send_driver_credentials_email(
    user,
    temporary_password,
    request,
):
    verification_section = ""

    if not user.email_verified:
        verification_url = (
            build_verification_url(
                user,
                request,
            )
        )

        verification_section = (
            "\nConfirm your email address:\n"
            f"{verification_url}\n"
        )

    try:
        send_mail(
            subject=(
                "Your TaxiLink driver account"
            ),
            message=(
                f"Hello "
                f"{user.first_name or user.email},\n\n"
                "A TaxiLink driver account has "
                "been created for you.\n\n"
                f"Email: {user.email}\n"
                f"Temporary password: "
                f"{temporary_password}\n"
                f"{verification_section}\n"
                "You must change the temporary "
                "password after signing in."
            ),
            from_email=(
                settings.DEFAULT_FROM_EMAIL
            ),
            recipient_list=[
                user.email
            ],
            fail_silently=False,
        )
    except Exception:
        logger.exception(
            (
                "Driver credential email delivery "
                "failed for user %s."
            ),
            user.pk,
        )

        return False

    return True