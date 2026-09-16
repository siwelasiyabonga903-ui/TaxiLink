from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.db.models import IntegerField, Prefetch, Q, Sum, Value
from django.utils import timezone
from django.db.models.functions import Coalesce
from .services import calculate_distance_meters

from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import (
    DispatchAssignment,
    DispatchRequest,
    DriverAvailability,
    Route,
    Trip,
    WaitingRequest,
    WaitingSpot,
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
)


User = get_user_model()
GEOFENCE_EXIT_GRACE_SECONDS = 30


def waiting_spot_queryset():
    return WaitingSpot.objects.select_related(
        "route"
    ).annotate(
        active_waiting_count=Coalesce(
            Sum(
                "waiting_requests__party_size",
                filter=Q(
                    waiting_requests__status=(
                        WaitingRequest.Status.WAITING
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
        waiting_request = (
            WaitingRequest.objects
            .filter(
                passenger=request.user,
                status=WaitingRequest.Status.WAITING,
            )
            .first()
        )

        if waiting_request is None:
            return Response(
                {
                    "detail": (
                        "You do not have an active waiting request."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
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

                return Response(
                    {
                        "active": True,
                        "cancelled": False,
                        "inside_geofence": False,
                        "grace_period_active": True,
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
                        "distance_meters": round(
                            distance,
                            2,
                        ),
                    }
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

            return Response(
                {
                    "active": False,
                    "cancelled": True,
                    "inside_geofence": False,
                    "grace_period_active": False,
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