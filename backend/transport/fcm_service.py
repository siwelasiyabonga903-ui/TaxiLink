from firebase_admin import messaging

from .firebase import get_firebase_app
from .models import DeviceToken


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

        if isinstance(
            send_response.exception,
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