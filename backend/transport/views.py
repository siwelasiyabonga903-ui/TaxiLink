from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.db.models import IntegerField, Prefetch, Q, Sum, Value
from django.utils import timezone
from django.db.models.functions import Coalesce
from .services import calculate_distance_meters
from .notification_service import create_notification
from .routing_service import (RoutingServiceError, get_route_geojson, get_coordinates_geojson)
from decimal import Decimal, InvalidOperation

from rest_framework.permissions import IsAuthenticated
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from math import ceil
from .models import (
    DispatchAssignment,
    DispatchRequest,
    DriverAvailability,
    DriverLocation,
    Route,
    Trip,
    WaitingRequest,
    WaitingSpot,
    Notification,
    DeviceToken,
)
from .permissions import (
    IsDispatcher,
    IsDispatcherOrReadOnly,
    IsDriver,
    IsDriverOrDispatcher,
    IsPassenger,
)
from .serializers import (
    AvailableDriverSerializer,
    DispatchAssignmentSerializer,
    DriverAvailabilitySerializer,
    PassengerCheckInSerializer,
    RouteSerializer,
    WaitingRequestSerializer,
    WaitingSpotSerializer,
    PassengerLocationRevalidationSerializer,
    NotificationSerializer,
    DeviceTokenSerializer,
)


User = get_user_model()
GEOFENCE_EXIT_GRACE_SECONDS = 60


def waiting_spot_queryset():
    assigned_request_ids = (
        DispatchRequest.objects.filter(
            dispatch__status__in=[
                DispatchAssignment.Status.PENDING,
                DispatchAssignment.Status.ACCEPTED,
                DispatchAssignment.Status.EN_ROUTE,
            ]
        ).values("waiting_request_id")
    )

    return WaitingSpot.objects.select_related("route").annotate(
        active_waiting_count=Coalesce(
            Sum(
                "waiting_requests__party_size",
                filter=(
                    Q(
                        waiting_requests__status=(
                            WaitingRequest.Status.WAITING
                        )
                    )
                    & ~Q(
                        waiting_requests__id__in=assigned_request_ids
                    )
                ),
            ),
            Value(0),
            output_field=IntegerField(),
        )
    )


class RouteViewSet(viewsets.ModelViewSet):
    serializer_class = RouteSerializer
    permission_classes = [IsDispatcherOrReadOnly]

    def get_queryset(self):
        routes = Route.objects.all()
        spots = waiting_spot_queryset()

        if self.request.user.role != "DISPATCHER":
            routes = routes.filter(is_active=True)
            spots = spots.filter(is_active=True)

        return routes.prefetch_related(
            Prefetch(
                "waiting_spots",
                queryset=spots,
            )
        )

    @action(
    detail=True,
    methods=["get"],
    url_path="road-route",
    )
    def road_route(
        self,
        request,
        pk=None,
    ):
        route = self.get_object()

        try:
            geojson = get_route_geojson(
                route
            )

        except RoutingServiceError as exc:
            return Response(
                {
                    "detail": str(exc)
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            geojson,
            status=status.HTTP_200_OK,
        )


class WaitingSpotViewSet(viewsets.ModelViewSet):
    serializer_class = WaitingSpotSerializer
    permission_classes = [IsDispatcherOrReadOnly]

    def get_queryset(self):
        spots = waiting_spot_queryset()

        if self.request.user.role != "DISPATCHER":
            spots = spots.filter(
                is_active=True,
                route__is_active=True,
            )

        return spots


class PassengerCheckInView(APIView):
    permission_classes = [IsPassenger]

    def post(self, request):
        serializer = PassengerCheckInSerializer(
            data=request.data,
            context={"request": request},
        )

        serializer.is_valid(raise_exception=True)

        try:
            with transaction.atomic():
                waiting_request = serializer.save()
        except IntegrityError:
            return Response(
                {
                    "detail": (
                        "You already have an active waiting request."
                    )
                },
                status=status.HTTP_409_CONFLICT,
            )

        return Response(
            WaitingRequestSerializer(
                waiting_request
            ).data,
            status=status.HTTP_201_CREATED,
        )


class CurrentWaitingRequestView(APIView):
    permission_classes = [IsPassenger]

    def get(self, request):
        waiting_request = (
            WaitingRequest.objects
            .select_related(
                "passenger",
                "waiting_spot",
                "waiting_spot__route",
            )
            .filter(
                passenger=request.user,
                status=WaitingRequest.Status.WAITING,
            )
            .first()
        )

        if waiting_request is None:
            return Response(
                {
                    "active": False,
                    "request": None,
                    "dispatch": None,
                }
            )

        active_statuses = [
            DispatchAssignment.Status.PENDING,
            DispatchAssignment.Status.ACCEPTED,
            DispatchAssignment.Status.EN_ROUTE,
        ]

        dispatch_link = (
            DispatchRequest.objects
            .select_related(
                "dispatch",
                "dispatch__driver",
            )
            .filter(
                waiting_request=waiting_request,
                dispatch__status__in=active_statuses,
            )
            .order_by(
                "-dispatch__created_at"
            )
            .first()
        )

        dispatch_data = None

        if dispatch_link:
            assignment = dispatch_link.dispatch

            dispatch_data = {
                "id": assignment.id,
                "route_id": assignment.route_id,
                "assigned": True,
                "status": assignment.status,
                "status_display": (
                    assignment.get_status_display()
                ),
                "message": (
                    "Taxi assigned. Waiting for "
                    "driver to accept."
                ),
                "driver": None,
            }

            if assignment.status in [
                DispatchAssignment.Status.ACCEPTED,
                DispatchAssignment.Status.EN_ROUTE,
            ]:
                driver = assignment.driver

                full_name = (
                    driver.get_full_name().strip()
                )

                dispatch_data["message"] = (
                    "Your taxi is on the way."
                )

                dispatch_data["driver"] = {
                    "name": (
                        full_name
                        or driver.username
                    ),
                    "number_plate": (
                        driver.number_plate
                    ),
                }

        return Response(
            {
                "active": True,
                "request": (
                    WaitingRequestSerializer(
                        waiting_request
                    ).data
                ),
                "dispatch": dispatch_data,
            }
        )


class CancelCurrentWaitingRequestView(APIView):
    permission_classes = [IsPassenger]

    def post(self, request):
        with transaction.atomic():
            waiting_request = (
                WaitingRequest.objects
                .select_for_update()
                .filter(
                    passenger=request.user,
                    status=(
                        WaitingRequest.Status.WAITING
                    ),
                )
                .first()
            )

            if waiting_request is None:
                return Response(
                    {
                        "detail": (
                            "You do not have an "
                            "active waiting request."
                        )
                    },
                    status=(
                        status.HTTP_400_BAD_REQUEST
                    ),
                )

            pending_assignment_ids = list(
                DispatchRequest.objects
                .filter(
                    waiting_request=waiting_request,
                    dispatch__status=(
                        DispatchAssignment
                        .Status
                        .PENDING
                    ),
                )
                .values_list(
                    "dispatch_id",
                    flat=True,
                )
            )

            pending_assignments = list(
                DispatchAssignment.objects
                .select_for_update()
                .filter(
                    pk__in=pending_assignment_ids,
                    status=(
                        DispatchAssignment
                        .Status
                        .PENDING
                    ),
                )
                .select_related(
                    "driver"
                )
            )

            waiting_request.status = (
                WaitingRequest.Status.CANCELLED
            )

            waiting_request.ended_at = (
                timezone.now()
            )

            waiting_request.save(
                update_fields=[
                    "status",
                    "ended_at",
                ]
            )

            for assignment in (
                pending_assignments
            ):
                remaining_count = sum(
                    dispatch_request
                    .waiting_request
                    .party_size
                    for dispatch_request
                    in (
                        assignment
                        .dispatch_requests
                        .select_related(
                            "waiting_request"
                        )
                        .filter(
                            waiting_request__status=(
                                WaitingRequest
                                .Status
                                .WAITING
                            )
                        )
                    )
                )

                if remaining_count > 0:
                    assignment.passenger_count = (
                        remaining_count
                    )

                    assignment.save(
                        update_fields=[
                            "passenger_count",
                        ]
                    )

                    continue

                assignment.status = (
                    DispatchAssignment
                    .Status
                    .CANCELLED
                )

                assignment.save(
                    update_fields=[
                        "status",
                    ]
                )

                availability, _ = (
                    DriverAvailability.objects
                    .select_for_update()
                    .get_or_create(
                        driver=(
                            assignment.driver
                        )
                    )
                )

                availability.is_available = (
                    True
                )

                availability.save(
                    update_fields=[
                        "is_available",
                        "updated_at",
                    ]
                )

        return Response(
            WaitingRequestSerializer(
                waiting_request
            ).data
        )

class RevalidateWaitingLocationView(APIView):
    permission_classes = [IsPassenger]

    def post(self, request):
        serializer = (
            PassengerLocationRevalidationSerializer(
                data=request.data
            )
        )

        serializer.is_valid(
            raise_exception=True
        )

        latitude = (
            serializer.validated_data[
                "latitude"
            ]
        )

        longitude = (
            serializer.validated_data[
                "longitude"
            ]
        )

        with transaction.atomic():
            waiting_request = (
                WaitingRequest.objects
                .select_for_update()
                .select_related(
                    "waiting_spot"
                )
                .filter(
                    passenger=request.user,
                    status=(
                        WaitingRequest
                        .Status
                        .WAITING
                    ),
                )
                .first()
            )

            if waiting_request is None:
                return Response(
                    {
                        "active": False,
                        "cancelled": False,
                        "grace_period_active": False,
                        "grace_seconds_remaining": 0,
                        "detail": (
                            "You do not have an "
                            "active waiting request."
                        ),
                    }
                )

            waiting_spot = (
                waiting_request.waiting_spot
            )

            distance = (
                calculate_distance_meters(
                    latitude,
                    longitude,
                    waiting_spot.latitude,
                    waiting_spot.longitude,
                )
            )

            now = timezone.now()

            inside_geofence = (
                distance
                <= waiting_spot
                .geofence_radius_meters
            )

            if inside_geofence:
                if (
                    waiting_request
                    .outside_geofence_since
                    is not None
                ):
                    waiting_request\
                        .outside_geofence_since = None

                    waiting_request.save(
                        update_fields=[
                            "outside_geofence_since",
                        ]
                    )

                return Response(
                    {
                        "active": True,
                        "cancelled": False,
                        "inside_geofence": True,
                        "grace_period_active": False,
                        "grace_seconds_remaining": 0,
                        "distance_meters": round(
                            distance,
                            2,
                        ),
                    }
                )

            if (
                waiting_request
                .outside_geofence_since
                is None
            ):
                waiting_request\
                    .outside_geofence_since = now

                waiting_request.save(
                    update_fields=[
                        "outside_geofence_since",
                    ]
                )

                create_notification(
                    recipient=request.user,
                    notification_type=(
                        Notification.Type.WAITING_SPOT_EXIT
                    ),
                    title="Return to your waiting spot",
                    message=(
                        "You have left the waiting spot. "
                        f"Return within {GEOFENCE_EXIT_GRACE_SECONDS} seconds "
                        "to keep your waiting request active."
                    ),
                )

                return Response(
                    {
                        "active": True,
                        "cancelled": False,
                        "inside_geofence": False,
                        "grace_period_active": True,
                        "grace_seconds_remaining": (
                            GEOFENCE_EXIT_GRACE_SECONDS
                        ),
                        "distance_meters": round(
                            distance,
                            2,
                        ),
                    }
                )

            outside_seconds = (
                now
                - waiting_request
                .outside_geofence_since
            ).total_seconds()

            if (
                outside_seconds
                < GEOFENCE_EXIT_GRACE_SECONDS
            ):
                return Response(
                    {
                        "active": True,
                        "cancelled": False,
                        "inside_geofence": False,
                        "grace_period_active": True,
                        "grace_seconds_remaining": max(
                            0,
                            ceil(
                                GEOFENCE_EXIT_GRACE_SECONDS
                                - outside_seconds
                            ),
                        ),
                        "distance_meters": round(
                            distance,
                            2,
                        ),
                    }
                )

            pending_assignment_ids = list(
                DispatchRequest.objects
                .filter(
                    waiting_request=waiting_request,
                    dispatch__status=(
                        DispatchAssignment
                        .Status
                        .PENDING
                    ),
                )
                .values_list(
                    "dispatch_id",
                    flat=True,
                )
            )

            pending_assignments = list(
                DispatchAssignment.objects
                .select_for_update()
                .filter(
                    pk__in=pending_assignment_ids,
                    status=(
                        DispatchAssignment
                        .Status
                        .PENDING
                    ),
                )
                .select_related(
                    "driver"
                )
            )

            waiting_request.status = (
                WaitingRequest.Status.CANCELLED
            )

            waiting_request.ended_at = now

            waiting_request.save(
                update_fields=[
                    "status",
                    "ended_at",
                ]
            )

            for assignment in pending_assignments:
                remaining_count = sum(
                    dispatch_request
                    .waiting_request
                    .party_size
                    for dispatch_request
                    in (
                        assignment
                        .dispatch_requests
                        .select_related(
                            "waiting_request"
                        )
                        .filter(
                            waiting_request__status=(
                                WaitingRequest
                                .Status
                                .WAITING
                            )
                        )
                    )
                )

                if remaining_count > 0:
                    assignment.passenger_count = (
                        remaining_count
                    )

                    assignment.save(
                        update_fields=[
                            "passenger_count",
                        ]
                    )

                    continue

                assignment.status = (
                    DispatchAssignment
                    .Status
                    .CANCELLED
                )

                assignment.save(
                    update_fields=[
                        "status",
                    ]
                )

                availability, _ = (
                    DriverAvailability.objects
                    .select_for_update()
                    .get_or_create(
                        driver=assignment.driver
                    )
                )

                availability.is_available = True

                availability.save(
                    update_fields=[
                        "is_available",
                        "updated_at",
                    ]
                )

            return Response(
                {
                    "active": False,
                    "cancelled": True,
                    "inside_geofence": False,
                    "grace_period_active": False,
                    "grace_seconds_remaining": 0,
                    "distance_meters": round(
                        distance,
                        2,
                    ),
                    "detail": (
                        "Your waiting request was "
                        "cancelled because you left "
                        "the waiting spot."
                    ),
                }
            )

class DriverAvailabilityView(APIView):
    permission_classes = [IsDriver]

    def get(self, request):
        availability, _ = (
            DriverAvailability.objects
            .get_or_create(
                driver=request.user
            )
        )

        return Response(
            DriverAvailabilitySerializer(
                availability
            ).data
        )

    def patch(self, request):
        availability, _ = (
            DriverAvailability.objects
            .get_or_create(
                driver=request.user
            )
        )

        requested_status = (
            request.data.get(
                "is_available"
            )
        )

        if not isinstance(
            requested_status,
            bool,
        ):
            return Response(
                {
                    "is_available": (
                        "This field must be true or false."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        active_dispatch_exists = (
            DispatchAssignment.objects
            .filter(
                driver=request.user,
                status__in=[
                    DispatchAssignment.Status.PENDING,
                    DispatchAssignment.Status.ACCEPTED,
                    DispatchAssignment.Status.EN_ROUTE,
                ],
            )
            .exists()
        )

        if (
            requested_status
            and active_dispatch_exists
        ):
            return Response(
                {
                    "detail": (
                        "You cannot become available while you have "
                        "an active dispatch assignment."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        availability.is_available = (
            requested_status
        )

        availability.save(
            update_fields=[
                "is_available",
                "updated_at",
            ]
        )

        return Response(
            DriverAvailabilitySerializer(
                availability
            ).data
        )


class AvailableDriversView(APIView):
    permission_classes = [IsDispatcher]

    def get(self, request):
        drivers = User.objects.filter(
            role="DRIVER"
        )

        for driver in drivers:
            DriverAvailability.objects.get_or_create(
                driver=driver
            )

        available_drivers = (
            User.objects.filter(
                role="DRIVER",
                driver_availability__is_available=True,
            )
            .exclude(
                driver_dispatches__status__in=[
                    DispatchAssignment.Status.PENDING,
                    DispatchAssignment.Status.ACCEPTED,
                    DispatchAssignment.Status.EN_ROUTE,
                ]
            )
            .distinct()
            .order_by(
                "driver_availability__updated_at",
                "username",
            )
        )

        return Response(
            AvailableDriverSerializer(
                available_drivers,
                many=True,
            ).data
        )


class DispatchAssignmentViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = (
        DispatchAssignmentSerializer
    )

    permission_classes = [
        IsDriverOrDispatcher
    ]

    def get_queryset(self):
        queryset = (
            DispatchAssignment.objects
            .select_related(
                "dispatcher",
                "driver",
                "route",
                "waiting_spot",
                "waiting_spot__route",
            )
        )

        if (
            self.request.user.role
            == "DRIVER"
        ):
            return queryset.filter(
                driver=self.request.user
            )

        return queryset

    def create(
        self,
        request,
        *args,
        **kwargs,
    ):
        if (
            request.user.role
            != "DISPATCHER"
        ):
            return Response(
                {
                    "detail": (
                        "Only dispatchers can create assignments."
                    )
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        return super().create(
            request,
            *args,
            **kwargs,
        )

    @action(
        detail=True,
        methods=[
            "get",
            "post",
        ],
        permission_classes=[
            IsAuthenticated
        ],
        url_path="location",
    )
    def location(
        self,
        request,
        pk=None,
    ):
        assignment = (
            DispatchAssignment.objects
            .select_related(
                "driver",
                "dispatcher",
            )
            .filter(
                pk=pk
            )
            .first()
        )

        if assignment is None:
            return Response(
                {
                    "detail": (
                        "Dispatch assignment "
                        "not found."
                    )
                },
                status=(
                    status.HTTP_404_NOT_FOUND
                ),
            )

        if request.method == "POST":
            if (
                request.user.role
                != "DRIVER"
                or assignment.driver_id
                != request.user.id
            ):
                return Response(
                    {
                        "detail": (
                            "Only the assigned "
                            "driver can update "
                            "this location."
                        )
                    },
                    status=(
                        status.HTTP_403_FORBIDDEN
                    ),
                )

            if (
                assignment.status
                != DispatchAssignment
                .Status
                .EN_ROUTE
            ):
                return Response(
                    {
                        "detail": (
                            "Location can only "
                            "be updated while "
                            "the dispatch is "
                            "en route."
                        )
                    },
                    status=(
                        status.HTTP_400_BAD_REQUEST
                    ),
                )

            try:
                latitude = Decimal(
                    str(
                        request.data[
                            "latitude"
                        ]
                    )
                )

                longitude = Decimal(
                    str(
                        request.data[
                            "longitude"
                        ]
                    )
                )

            except (
                KeyError,
                TypeError,
                ValueError,
                InvalidOperation,
            ):
                return Response(
                    {
                        "detail": (
                            "Valid latitude and "
                            "longitude are required."
                        )
                    },
                    status=(
                        status.HTTP_400_BAD_REQUEST
                    ),
                )

            if not (
                Decimal("-90")
                <= latitude
                <= Decimal("90")
            ):
                return Response(
                    {
                        "latitude": (
                            "Latitude must be "
                            "between -90 and 90."
                        )
                    },
                    status=(
                        status.HTTP_400_BAD_REQUEST
                    ),
                )

            if not (
                Decimal("-180")
                <= longitude
                <= Decimal("180")
            ):
                return Response(
                    {
                        "longitude": (
                            "Longitude must be "
                            "between -180 and 180."
                        )
                    },
                    status=(
                        status.HTTP_400_BAD_REQUEST
                    ),
                )

            accuracy_raw = (
                request.data.get(
                    "accuracy_meters"
                )
            )

            accuracy = None

            if (
                accuracy_raw
                not in [
                    None,
                    "",
                ]
            ):
                try:
                    accuracy = Decimal(
                        str(
                            accuracy_raw
                        )
                    )

                except (
                    TypeError,
                    ValueError,
                    InvalidOperation,
                ):
                    return Response(
                        {
                            "accuracy_meters": (
                                "Accuracy must be "
                                "a valid number."
                            )
                        },
                        status=(
                            status
                            .HTTP_400_BAD_REQUEST
                        ),
                    )

                if (
                    accuracy < 0
                    or accuracy
                    > Decimal(
                        "999999.99"
                    )
                ):
                    return Response(
                        {
                            "accuracy_meters": (
                                "Accuracy must be "
                                "between 0 and "
                                "999999.99 metres."
                            )
                        },
                        status=(
                            status
                            .HTTP_400_BAD_REQUEST
                        ),
                    )

            driver_location, created = (
                DriverLocation.objects
                .update_or_create(
                    dispatch=assignment,
                    defaults={
                        "latitude": latitude,
                        "longitude": longitude,
                        "accuracy_meters": (
                            accuracy
                        ),
                    },
                )
            )

            return Response(
                {
                    "available": True,
                    "dispatch": (
                        assignment.id
                    ),
                    "latitude": float(
                        driver_location.latitude
                    ),
                    "longitude": float(
                        driver_location.longitude
                    ),
                    "accuracy_meters": (
                        float(
                            driver_location
                            .accuracy_meters
                        )
                        if (
                            driver_location
                            .accuracy_meters
                            is not None
                        )
                        else None
                    ),
                    "updated_at": (
                        driver_location
                        .updated_at
                    ),
                },
                status=(
                    status.HTTP_201_CREATED
                    if created
                    else status.HTTP_200_OK
                ),
            )

        authorised = False

        if (
            request.user.role
            == "DISPATCHER"
        ):
            authorised = True

        elif (
            request.user.role
            == "DRIVER"
            and assignment.driver_id
            == request.user.id
        ):
            authorised = True

        elif (
            request.user.role
            == "PASSENGER"
        ):
            authorised = (
                DispatchRequest.objects
                .filter(
                    dispatch=assignment,
                    waiting_request__passenger=(
                        request.user
                    ),
                    waiting_request__status=(
                        WaitingRequest
                        .Status
                        .WAITING
                    ),
                )
                .exists()
            )

        if not authorised:
            return Response(
                {
                    "detail": (
                        "You do not have "
                        "permission to track "
                        "this dispatch."
                    )
                },
                status=(
                    status.HTTP_403_FORBIDDEN
                ),
            )

        if (
            assignment.status
            != DispatchAssignment
            .Status
            .EN_ROUTE
        ):
            return Response(
                {
                    "detail": (
                        "Tracking is only "
                        "available while the "
                        "dispatch is en route."
                    )
                },
                status=(
                    status.HTTP_400_BAD_REQUEST
                ),
            )

        driver_location = (
            DriverLocation.objects
            .filter(
                dispatch=assignment
            )
            .first()
        )

        if driver_location is None:
            return Response(
                {
                    "available": False,
                    "dispatch": (
                        assignment.id
                    ),
                    "location": None,
                }
            )

        return Response(
            {
                "available": True,
                "dispatch": (
                    assignment.id
                ),
                "latitude": float(
                    driver_location.latitude
                ),
                "longitude": float(
                    driver_location.longitude
                ),
                "accuracy_meters": (
                    float(
                        driver_location
                        .accuracy_meters
                    )
                    if (
                        driver_location
                        .accuracy_meters
                        is not None
                    )
                    else None
                ),
                "updated_at": (
                    driver_location
                    .updated_at
                ),
            }
        )

    @action(
        detail=True,
        methods=["get"],
        permission_classes=[
            IsAuthenticated
        ],
        url_path="passenger-route",
    )
    def passenger_route(
        self,
        request,
        pk=None,
    ):
        assignment = (
            DispatchAssignment.objects
            .filter(
                pk=pk
            )
            .first()
        )

        if assignment is None:
            return Response(
                {
                    "detail": (
                        "Dispatch assignment "
                        "not found."
                    )
                },
                status=(
                    status.HTTP_404_NOT_FOUND
                ),
            )

        if (
            request.user.role
            != "PASSENGER"
        ):
            return Response(
                {
                    "detail": (
                        "Only an assigned "
                        "passenger can view "
                        "this pickup route."
                    )
                },
                status=(
                    status.HTTP_403_FORBIDDEN
                ),
            )

        if (
            assignment.status
            != DispatchAssignment
            .Status
            .EN_ROUTE
        ):
            return Response(
                {
                    "detail": (
                        "Pickup route tracking "
                        "is only available while "
                        "the dispatch is en route."
                    )
                },
                status=(
                    status.HTTP_400_BAD_REQUEST
                ),
            )

        passenger_link = (
            DispatchRequest.objects
            .select_related(
                "waiting_request",
                "waiting_request__waiting_spot",
            )
            .filter(
                dispatch=assignment,
                waiting_request__passenger=(
                    request.user
                ),
                waiting_request__status=(
                    WaitingRequest
                    .Status
                    .WAITING
                ),
                boarded=False,
            )
            .first()
        )

        if passenger_link is None:
            return Response(
                {
                    "detail": (
                        "Live pickup tracking "
                        "is no longer available "
                        "for this passenger."
                    )
                },
                status=(
                    status.HTTP_403_FORBIDDEN
                ),
            )

        passenger_spot = (
            passenger_link
            .waiting_request
            .waiting_spot
        )

        pickup_links = (
            DispatchRequest.objects
            .select_related(
                "waiting_request",
                "waiting_request__waiting_spot",
            )
            .filter(
                dispatch=assignment,
                boarded=False,
                waiting_request__status=(
                    WaitingRequest.Status.WAITING
                ),
                waiting_request__waiting_spot__stop_order__lte=(
                    passenger_spot.stop_order
                ),
            )
            .order_by(
                "waiting_request__waiting_spot__stop_order",
                "waiting_request__waiting_spot_id",
            )
        )

        pickup_spots = []
        seen_spot_ids = set()

        for link in pickup_links:
            spot = (
                link
                .waiting_request
                .waiting_spot
            )

            if (
                spot.id
                in seen_spot_ids
            ):
                continue

            seen_spot_ids.add(
                spot.id
            )

            pickup_spots.append(
                {
                    "id": spot.id,
                    "name": spot.name,
                    "stop_order": (
                        spot.stop_order
                    ),
                    "latitude": float(
                        spot.latitude
                    ),
                    "longitude": float(
                        spot.longitude
                    ),
                    "is_passenger_spot": (
                        spot.id
                        == passenger_spot.id
                    ),
                }
            )

        driver_location = (
            DriverLocation.objects
            .filter(
                dispatch=assignment
            )
            .first()
        )

        if driver_location is None:
            return Response(
                {
                    "available": False,
                    "dispatch": (
                        assignment.id
                    ),
                    "driver_location": None,
                    "pickup_spots": (
                        pickup_spots
                    ),
                    "route": None,
                }
            )

        coordinates = [
            [
                float(
                    driver_location
                    .longitude
                ),
                float(
                    driver_location
                    .latitude
                ),
            ]
        ]

        for spot in pickup_spots:
            coordinates.append(
                [
                    spot["longitude"],
                    spot["latitude"],
                ]
            )

        try:
            route_geojson = (
                get_coordinates_geojson(
                    coordinates
                )
            )

        except RoutingServiceError as exc:
            return Response(
                {
                    "detail": str(exc)
                },
                status=(
                    status.HTTP_400_BAD_REQUEST
                ),
            )

        return Response(
            {
                "available": True,
                "dispatch": (
                    assignment.id
                ),
                "driver_location": {
                    "latitude": float(
                        driver_location
                        .latitude
                    ),
                    "longitude": float(
                        driver_location
                        .longitude
                    ),
                    "accuracy_meters": (
                        float(
                            driver_location
                            .accuracy_meters
                        )
                        if (
                            driver_location
                            .accuracy_meters
                            is not None
                        )
                        else None
                    ),
                    "updated_at": (
                        driver_location
                        .updated_at
                    ),
                },
                "pickup_spots": (
                    pickup_spots
                ),
                "route": (
                    route_geojson
                ),
            }
        )

    @action(
    detail=True,
    methods=["post"],
    permission_classes=[IsDriver],
    )
    def accept(
        self,
        request,
        pk=None,
    ):
        with transaction.atomic():
            assignment = (
                DispatchAssignment.objects
                .select_for_update()
                .filter(
                    pk=pk,
                    driver=request.user,
                )
                .first()
            )

            if assignment is None:
                return Response(
                    {
                        "detail": (
                            "Dispatch assignment not found."
                        )
                    },
                    status=status.HTTP_404_NOT_FOUND,
                )

            if (
                assignment.status
                != DispatchAssignment.Status.PENDING
            ):
                return Response(
                    {
                        "detail": (
                            "Only pending assignments "
                            "can be accepted."
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            waiting_passengers_exist = (
                DispatchRequest.objects
                .filter(
                    dispatch=assignment,
                    waiting_request__status=(
                        WaitingRequest.Status.WAITING
                    ),
                )
                .exists()
            )

            if not waiting_passengers_exist:
                now = timezone.now()

                assignment.status = (
                    DispatchAssignment.Status.CANCELLED
                )

                assignment.responded_at = now

                assignment.save(
                    update_fields=[
                        "status",
                        "responded_at",
                    ]
                )

                availability, _ = (
                    DriverAvailability.objects
                    .select_for_update()
                    .get_or_create(
                        driver=request.user
                    )
                )

                availability.is_available = True

                availability.save(
                    update_fields=[
                        "is_available",
                        "updated_at",
                    ]
                )

                return Response(
                    {
                        "detail": (
                            "This dispatch was cancelled because "
                            "no assigned passengers are still waiting."
                        )
                    },
                    status=status.HTTP_409_CONFLICT,
                )

            now = timezone.now()

            trip, _ = (
                Trip.objects
                .get_or_create(
                    dispatch=assignment
                )
            )

            assignment.status = (
                DispatchAssignment.Status.EN_ROUTE
            )

            assignment.responded_at = now

            assignment.save(
                update_fields=[
                    "status",
                    "responded_at",
                ]
            )

            trip.en_route_at = now

            waiting_passengers = (
                User.objects
                .filter(
                    waiting_requests__dispatch_requests__dispatch=assignment,
                    waiting_requests__status=(
                        WaitingRequest.Status.WAITING
                    ),
                )
                .distinct()
            )

            for passenger in waiting_passengers:
                create_notification(
                    recipient=passenger,
                    notification_type=(
                        Notification.Type.DISPATCH_ACCEPTED
                    ),
                    title="Taxi on the way",
                    message=(
                        "Your assigned driver accepted the dispatch "
                        "and is on the way."
                    ),
                    dispatch=assignment,
                )

            create_notification(
                recipient=assignment.dispatcher,
                notification_type=(
                    Notification.Type.DISPATCH_ACCEPTED
                ),
                title="Dispatch accepted",
                message=(
                    f"{assignment.driver.username} accepted "
                    f"the dispatch for {assignment.route.name}."
                ),
                dispatch=assignment,
            )

            trip.save(
                update_fields=[
                    "en_route_at",
                ]
            )

        return Response(
            DispatchAssignmentSerializer(
                assignment
            ).data
        )

    @action(
        detail=True,
        methods=["post"],
        permission_classes=[IsDriver],
        url_path="en-route",
    )
    def en_route(
        self,
        request,
        pk=None,
    ):
        with transaction.atomic():
            assignment = (
                DispatchAssignment.objects
                .select_for_update()
                .filter(
                    pk=pk,
                    driver=request.user,
                )
                .first()
            )

            if assignment is None:
                return Response(
                    {
                        "detail": (
                            "Dispatch assignment not found."
                        )
                    },
                    status=status.HTTP_404_NOT_FOUND,
                )

            if (
                assignment.status
                != DispatchAssignment.Status.ACCEPTED
            ):
                return Response(
                    {
                        "detail": (
                            "Only accepted assignments can be "
                            "marked as en route."
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            trip, _ = (
                Trip.objects
                .get_or_create(
                    dispatch=assignment
                )
            )

            now = timezone.now()

            assignment.status = (
                DispatchAssignment.Status.EN_ROUTE
            )

            assignment.save(
                update_fields=[
                    "status"
                ]
            )

            trip.en_route_at = now

            trip.save(
                update_fields=[
                    "en_route_at"
                ]
            )

        return Response(
            DispatchAssignmentSerializer(
                assignment
            ).data
        )

    @action(
        detail=True,
        methods=["post"],
        permission_classes=[IsDriver],
        url_path="confirm-boarding",
    )
    def confirm_boarding(
        self,
        request,
        pk=None,
    ):
        waiting_spot_id = (
            request.data.get(
                "waiting_spot"
            )
        )

        boarding_pin = str(
            request.data.get(
                "boarding_pin",
                "",
            )
        ).strip().upper()

        try:
            waiting_spot_id = int(
                waiting_spot_id
            )
        except (
            TypeError,
            ValueError,
        ):
            return Response(
                {
                    "waiting_spot": (
                        "A valid waiting spot is required."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        valid_pin = (
            len(boarding_pin) == 3
            and boarding_pin[0]
            in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
            and boarding_pin[1:].isdigit()
            and 1
            <= int(boarding_pin[1:])
            <= 99
        )

        if not valid_pin:
            return Response(
                {
                    "boarding_pin": (
                        "Incorrect boarding code or this "
                        "passenger is not assigned to your taxi."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            assignment = (
                DispatchAssignment.objects
                .select_for_update()
                .filter(
                    pk=pk,
                    driver=request.user,
                )
                .first()
            )

            if assignment is None:
                return Response(
                    {
                        "detail": (
                            "Dispatch assignment not found."
                        )
                    },
                    status=status.HTTP_404_NOT_FOUND,
                )

            if (
                assignment.status
                != DispatchAssignment.Status.EN_ROUTE
            ):
                return Response(
                    {
                        "detail": (
                            "Boarding can only be confirmed "
                            "while the dispatch is en route."
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            trip = (
                Trip.objects
                .select_for_update()
                .filter(
                    dispatch=assignment
                )
                .first()
            )

            if trip is None:
                return Response(
                    {
                        "detail": (
                            "Trip record not found."
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            dispatch_request = (
                DispatchRequest.objects
                .select_for_update()
                .select_related(
                    "waiting_request",
                    "waiting_request__waiting_spot",
                )
                .filter(
                    dispatch=assignment,
                    boarded=False,
                    waiting_request__waiting_spot_id=(
                        waiting_spot_id
                    ),
                    waiting_request__boarding_pin=(
                        boarding_pin
                    ),
                    waiting_request__status=(
                        WaitingRequest.Status.WAITING
                    ),
                )
                .first()
            )

            if dispatch_request is None:
                return Response(
                    {
                        "boarding_pin": (
                            "Incorrect boarding code or this "
                            "passenger is not assigned to your taxi."
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            waiting_request = (
                dispatch_request
                .waiting_request
            )

            group_size = (
                waiting_request.party_size
            )

            if (
                trip.boarded_passenger_count
                + group_size
                > 15
            ):
                return Response(
                    {
                        "detail": (
                            "Boarding this group would exceed "
                            "the taxi capacity."
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            now = timezone.now()

            waiting_request.status = (
                WaitingRequest.Status.BOARDED
            )

            waiting_request.ended_at = now

            waiting_request.save(
                update_fields=[
                    "status",
                    "ended_at",
                ]
            )

            dispatch_request.boarded = True
            dispatch_request.boarded_at = now

            dispatch_request.save(
                update_fields=[
                    "boarded",
                    "boarded_at",
                ]
            )

            trip.boarded_passenger_count += (
                group_size
            )

            trip.boarding_confirmed_at = (
                now
            )

            trip.save(
                update_fields=[
                    "boarded_passenger_count",
                    "boarding_confirmed_at",
                ]
            )

        return Response(
            DispatchAssignmentSerializer(
                assignment
            ).data
        )

    @action(
        detail=True,
        methods=["post"],
        permission_classes=[
            IsDispatcher
        ],
    )
    def cancel(
        self,
        request,
        pk=None,
    ):
        with transaction.atomic():
            assignment = (
                DispatchAssignment.objects
                .select_for_update()
                .filter(pk=pk)
                .first()
            )

            if assignment is None:
                return Response(
                    {
                        "detail": (
                            "Dispatch assignment not found."
                        )
                    },
                    status=status.HTTP_404_NOT_FOUND,
                )

            active_statuses = [
                DispatchAssignment.Status.PENDING,
                DispatchAssignment.Status.ACCEPTED,
                DispatchAssignment.Status.EN_ROUTE,
            ]

            if (
                assignment.status
                not in active_statuses
            ):
                return Response(
                    {
                        "detail": (
                            "Only active dispatch "
                            "assignments can be cancelled."
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            boarded_exists = (
                DispatchRequest.objects
                .filter(
                    dispatch=assignment,
                    boarded=True,
                )
                .exists()
            )

            trip = (
                Trip.objects
                .select_for_update()
                .filter(
                    dispatch=assignment
                )
                .first()
            )

            if (
                boarded_exists
                or (
                    trip is not None
                    and (
                        trip.boarded_passenger_count
                        > 0
                    )
                )
            ):
                return Response(
                    {
                        "detail": (
                            "This dispatch cannot be "
                            "cancelled because passenger "
                            "boarding has already started."
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            assignment.status = (
                DispatchAssignment.Status.CANCELLED
            )

            waiting_passengers = (
                User.objects
                .filter(
                    waiting_requests__dispatch_requests__dispatch=assignment,
                    waiting_requests__status=(
                        WaitingRequest.Status.WAITING
                    ),
                )
                .distinct()
            )

            for passenger in waiting_passengers:
                create_notification(
                    recipient=passenger,
                    notification_type=(
                        Notification.Type.DISPATCH_CANCELLED
                    ),
                    title="Taxi assignment cancelled",
                    message=(
                        "Your taxi assignment was cancelled. "
                        "You are still waiting for another taxi."
                    ),
                    dispatch=assignment,
                )

            destination = (
                assignment.route.name
                if assignment.route
                else assignment.waiting_spot.name
                if assignment.waiting_spot
                else "assigned route"
            )

            create_notification(
                recipient=assignment.driver,
                notification_type=(
                    Notification.Type.DISPATCH_CANCELLED
                ),
                title="Dispatch cancelled",
                message=(
                    f"The dispatcher cancelled your dispatch "
                    f"for {destination}."
                ),
                dispatch=assignment,
            )

            create_notification(
                recipient=assignment.dispatcher,
                notification_type=(
                    Notification.Type.DISPATCH_CANCELLED
                ),
                title="Dispatch cancelled",
                message=(
                    f"The dispatch for {destination} "
                    f"was cancelled."
                ),
                dispatch=assignment,
            )

            assignment.save(
                update_fields=[
                    "status",
                ]
            )

            availability, _ = (
                DriverAvailability.objects
                .select_for_update()
                .get_or_create(
                    driver=(
                        assignment.driver
                    )
                )
            )

            availability.is_available = (
                True
            )

            availability.save(
                update_fields=[
                    "is_available",
                    "updated_at",
                ]
            )

        return Response(
            DispatchAssignmentSerializer(
                assignment
            ).data
        )

    @action(
        detail=True,
        methods=["post"],
        permission_classes=[IsDriver],
    )
    def complete(
    self,
    request,
    pk=None,
):
        with transaction.atomic():
            assignment = (
                DispatchAssignment.objects
                .select_for_update()
                .filter(
                    pk=pk,
                    driver=request.user,
                )
                .first()
            )

            if assignment is None:
                return Response(
                    {
                        "detail": (
                            "Dispatch assignment not found."
                        )
                    },
                    status=status.HTTP_404_NOT_FOUND,
                )

            if (
                assignment.status
                != DispatchAssignment.Status.EN_ROUTE
            ):
                return Response(
                    {
                        "detail": (
                            "Only en route assignments "
                            "can be completed."
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            trip = (
                Trip.objects
                .select_for_update()
                .filter(
                    dispatch=assignment
                )
                .first()
            )

            if trip is None:
                return Response(
                    {
                        "detail": (
                            "Trip record not found."
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            unresolved_requests_exist = (
                DispatchRequest.objects
                .filter(
                    dispatch=assignment,
                    boarded=False,
                    waiting_request__status=(
                        WaitingRequest.Status.WAITING
                    ),
                )
                .exists()
            )

            if unresolved_requests_exist:
                return Response(
                    {
                        "detail": (
                            "This trip cannot be completed while "
                            "assigned passengers are still waiting."
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            now = timezone.now()

            assignment.status = (
                DispatchAssignment.Status.COMPLETED
            )

            assignment.save(
                update_fields=[
                    "status"
                ]
            )

            trip.completed_at = now

            trip.save(
                update_fields=[
                    "completed_at"
                ]
            )

            availability, _ = (
                DriverAvailability.objects
                .select_for_update()
                .get_or_create(
                    driver=request.user
                )
            )

            availability.is_available = True

            availability.save(
                update_fields=[
                    "is_available",
                    "updated_at",
                ]
            )

        return Response(
            DispatchAssignmentSerializer(
                assignment
            ).data
        )

    @action(
        detail=True,
        methods=["post"],
        permission_classes=[IsDriver],
    )
    def reject(
        self,
        request,
        pk=None,
    ):
        with transaction.atomic():
            assignment = (
                DispatchAssignment.objects
                .select_for_update()
                .filter(
                    pk=pk,
                    driver=request.user,
                )
                .first()
            )

            if assignment is None:
                return Response(
                    {
                        "detail": (
                            "Dispatch assignment not found."
                        )
                    },
                    status=status.HTTP_404_NOT_FOUND,
                )

            if (
                assignment.status
                != DispatchAssignment.Status.PENDING
            ):
                return Response(
                    {
                        "detail": (
                            "Only pending assignments "
                            "can be rejected."
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            assignment.status = (
                DispatchAssignment.Status.REJECTED
            )

            assignment.responded_at = (
                timezone.now()
            )

            assignment.save(
                update_fields=[
                    "status",
                    "responded_at",
                ]
            )

            availability, _ = (
                DriverAvailability.objects
                .select_for_update()
                .get_or_create(
                    driver=request.user
                )
            )

            availability.is_available = True

            availability.save(
                update_fields=[
                    "is_available",
                    "updated_at",
                ]
            )

            waiting_passengers = (
                User.objects
                .filter(
                    waiting_requests__dispatch_requests__dispatch=assignment,
                    waiting_requests__status=(
                        WaitingRequest.Status.WAITING
                    ),
                )
                .distinct()
            )

            for passenger in waiting_passengers:
                create_notification(
                    recipient=passenger,
                    notification_type=(
                        Notification.Type.DISPATCH_REJECTED
                    ),
                    title="Taxi assignment changed",
                    message=(
                        "The assigned driver declined the dispatch. "
                        "You are still waiting for another taxi."
                    ),
                    dispatch=assignment,
                )

            destination = (
                assignment.route.name
                if assignment.route
                else assignment.waiting_spot.name
                if assignment.waiting_spot
                else "assigned route"
            )

            create_notification(
                recipient=assignment.dispatcher,
                notification_type=(
                    Notification.Type.DISPATCH_REJECTED
                ),
                title="Dispatch rejected",
                message=(
                    f"{assignment.driver.username} rejected "
                    f"the dispatch for {destination}."
                ),
                dispatch=assignment,
            )

        return Response(
            DispatchAssignmentSerializer(
                assignment
            ).data
        )

class NotificationListView(APIView):
    permission_classes = [
        IsAuthenticated
    ]

    def get(self, request):
        notifications = (
            Notification.objects
            .filter(
                recipient=request.user
            )
            .select_related(
                "dispatch"
            )
        )

        return Response(
            NotificationSerializer(
                notifications,
                many=True,
            ).data
        )


class NotificationMarkReadView(APIView):
    permission_classes = [
        IsAuthenticated
    ]

    def post(
        self,
        request,
        notification_id,
    ):
        notification = (
            Notification.objects
            .filter(
                id=notification_id,
                recipient=request.user,
            )
            .first()
        )

        if notification is None:
            return Response(
                {
                    "detail": (
                        "Notification not found."
                    )
                },
                status=(
                    status.HTTP_404_NOT_FOUND
                ),
            )

        if not notification.is_read:
            notification.is_read = True

            notification.save(
                update_fields=[
                    "is_read",
                ]
            )

        return Response(
            NotificationSerializer(
                notification
            ).data
        )


class NotificationMarkAllReadView(
    APIView
):
    permission_classes = [
        IsAuthenticated
    ]

    def post(self, request):
        marked_read = (
            Notification.objects
            .filter(
                recipient=request.user,
                is_read=False,
            )
            .update(
                is_read=True
            )
        )

        return Response(
            {
                "marked_read": (
                    marked_read
                )
            }
        )


class DeviceTokenRegisterView(APIView):
    permission_classes = [
        IsAuthenticated
    ]

    def post(self, request):
        serializer = DeviceTokenSerializer(
            data=request.data
        )

        serializer.is_valid(
            raise_exception=True
        )

        token = (
            serializer.validated_data[
                "token"
            ]
        )

        platform = (
            serializer.validated_data[
                "platform"
            ]
        )

        existing_token = (
            DeviceToken.objects
            .filter(
                token=token
            )
            .first()
        )

        created = (
            existing_token is None
        )

        if existing_token:
            existing_token.user = (
                request.user
            )

            existing_token.platform = (
                platform
            )

            existing_token.is_active = True

            existing_token.save(
                update_fields=[
                    "user",
                    "platform",
                    "is_active",
                    "updated_at",
                ]
            )

            device_token = (
                existing_token
            )

        else:
            device_token = (
                DeviceToken.objects.create(
                    user=request.user,
                    token=token,
                    platform=platform,
                )
            )

        return Response(
            {
                "id": device_token.id,
                "platform": (
                    device_token.platform
                ),
                "is_active": (
                    device_token.is_active
                ),
            },
            status=(
                status.HTTP_201_CREATED
                if created
                else status.HTTP_200_OK
            ),
        )


class DeviceTokenDeleteView(APIView):
    permission_classes = [
        IsAuthenticated
    ]

    def delete(
        self,
        request,
        token_id,
    ):
        device_token = (
            DeviceToken.objects
            .filter(
                id=token_id,
                user=request.user,
            )
            .first()
        )

        if device_token is None:
            return Response(
                {
                    "detail": (
                        "Device token not found."
                    )
                },
                status=(
                    status.HTTP_404_NOT_FOUND
                ),
            )

        device_token.delete()

        return Response(
            status=status.HTTP_204_NO_CONTENT
        )