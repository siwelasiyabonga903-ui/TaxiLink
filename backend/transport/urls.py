from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AvailableDriversView,
    CancelCurrentWaitingRequestView,
    CurrentWaitingRequestView,
    DispatchAssignmentViewSet,
    DriverAvailabilityView,
    PassengerCheckInView,
    RouteViewSet,
    WaitingSpotViewSet,
    RevalidateWaitingLocationView,
    NotificationListView,
    NotificationMarkReadView,
    NotificationMarkAllReadView,
    DeviceTokenRegisterView,
    DeviceTokenDeleteView,
)


router = DefaultRouter()

router.register(
    "routes",
    RouteViewSet,
    basename="route",
)

router.register(
    "waiting-spots",
    WaitingSpotViewSet,
    basename="waiting-spot",
)

router.register(
    "dispatches",
    DispatchAssignmentViewSet,
    basename="dispatch",
)


urlpatterns = [
    path("", include(router.urls)),
    path(
        "waiting-requests/check-in/",
        PassengerCheckInView.as_view(),
        name="passenger-check-in",
    ),
    path(
        "waiting-requests/current/",
        CurrentWaitingRequestView.as_view(),
        name="current-waiting-request",
    ),
    path(
        "waiting-requests/cancel/",
        CancelCurrentWaitingRequestView.as_view(),
        name="cancel-waiting-request",
    ),
    path(
        "drivers/availability/",
        DriverAvailabilityView.as_view(),
        name="driver-availability",
    ),

    path(
        "drivers/available/",
        AvailableDriversView.as_view(),
        name="available-drivers",
    ),

    path(
    "waiting-requests/revalidate-location/",
    RevalidateWaitingLocationView.as_view(),
    name="revalidate-waiting-location",
    ),

    path(
    "notifications/",
    NotificationListView.as_view(),
    name="notification-list",
    ),

    path(
        "notifications/<int:notification_id>/read/",
        NotificationMarkReadView.as_view(),
        name="notification-mark-read",
    ),

    path(
        "notifications/read-all/",
        NotificationMarkAllReadView.as_view(),
        name="notification-mark-all-read",
    ),

    path(
        "device-tokens/",
        DeviceTokenRegisterView.as_view(),
        name="device-token-register",
    ),

    path(
        "device-tokens/<int:token_id>/",
        DeviceTokenDeleteView.as_view(),
        name="device-token-delete",
    ),
]