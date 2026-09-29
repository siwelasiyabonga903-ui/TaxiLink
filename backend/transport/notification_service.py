import logging

from django.db import transaction

from .fcm_service import send_push_notification
from .models import Notification


logger = logging.getLogger(__name__)


def _schedule_push(notification):
    data = {
        "notification_id": notification.id,
        "notification_type": (
            notification.notification_type
        ),
    }

    if notification.dispatch_id:
        data["dispatch_id"] = (
            notification.dispatch_id
        )

    recipient = notification.recipient
    title = notification.title
    message = notification.message

    def send():
        try:
            send_push_notification(
                recipient=recipient,
                title=title,
                message=message,
                data=data,
            )
        except Exception:
            logger.exception(
                (
                    "Unexpected push failure "
                    "for notification_id=%s "
                    "recipient_id=%s"
                ),
                notification.id,
                notification.recipient_id,
            )

            # FCM must never break
            # the core TaxiLink workflow.

    transaction.on_commit(send)


def create_notification(
    *,
    recipient,
    notification_type,
    title,
    message,
    dispatch=None,
):
    notification = (
        Notification.objects.create(
            recipient=recipient,
            notification_type=notification_type,
            title=title,
            message=message,
            dispatch=dispatch,
        )
    )

    _schedule_push(notification)

    return notification


def create_notifications(
    *,
    recipients,
    notification_type,
    title,
    message,
    dispatch=None,
):
    notifications = []

    seen_user_ids = set()

    for recipient in recipients:
        if recipient.id in seen_user_ids:
            continue

        seen_user_ids.add(
            recipient.id
        )

        notifications.append(
            Notification(
                recipient=recipient,
                notification_type=(
                    notification_type
                ),
                title=title,
                message=message,
                dispatch=dispatch,
            )
        )

    created_notifications = (
        Notification.objects.bulk_create(
            notifications
        )
    )

    for notification in created_notifications:
        _schedule_push(
            notification
        )

    return created_notifications