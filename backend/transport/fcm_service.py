import logging

from firebase_admin import messaging

from .firebase import get_firebase_app
from .models import DeviceToken


logger = logging.getLogger(__name__)


def send_push_notification(
    *,
    recipient,
    title,
    message,
    data=None,
):
    firebase_app = get_firebase_app()

    if firebase_app is None:
        return {
            "sent": 0,
            "failed": 0,
            "skipped": True,
        }

    tokens = list(
        DeviceToken.objects.filter(
            user=recipient,
            is_active=True,
        ).values_list(
            "token",
            flat=True,
        )
    )

    if not tokens:
        return {
            "sent": 0,
            "failed": 0,
            "skipped": True,
        }

    payload_data = {
        str(key): str(value)
        for key, value in (
            data or {}
        ).items()
    }

    push_message = messaging.MulticastMessage(
        notification=messaging.Notification(
            title=title,
            body=message,
        ),
        data=payload_data,
        tokens=tokens,
    )

    try:
        response = (
            messaging.send_each_for_multicast(
                push_message,
                app=firebase_app,
            )
        )
    except Exception:
        logger.exception(
            (
                "FCM multicast request failed "
                "for recipient_id=%s token_count=%s"
            ),
            recipient.id,
            len(tokens),
        )

        # Database notifications must continue
        # working even if Firebase is unavailable.
        return {
            "sent": 0,
            "failed": len(tokens),
            "skipped": False,
        }

    invalid_tokens = []

    for index, send_response in enumerate(
        response.responses
    ):
        if send_response.success:
            continue

        push_error = send_response.exception

        logger.error(
            (
                "FCM token delivery failed "
                "for recipient_id=%s "
                "error_type=%s error=%s"
            ),
            recipient.id,
            type(push_error).__name__,
            push_error,
        )

        if isinstance(
            push_error,
            messaging.UnregisteredError,
        ):
            invalid_tokens.append(
                tokens[index]
            )

    if invalid_tokens:
        DeviceToken.objects.filter(
            token__in=invalid_tokens
        ).update(
            is_active=False
        )

    return {
        "sent": response.success_count,
        "failed": response.failure_count,
        "skipped": False,
    }