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
]