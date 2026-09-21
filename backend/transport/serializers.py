from decimal import Decimal
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.db.models import Sum, Max
from .notification_service import create_notification
from rest_framework import serializers

from .models import (
    DispatchAssignment,
    DispatchRequest,
    DriverAvailability,
    Route,
    WaitingRequest,
    WaitingSpot,
    Notification,
    DeviceToken,
)
from .services import calculate_distance_meters
User = get_user_model()
import secrets

class WaitingSpotSerializer(serializers.ModelSerializer):
    route_name = serializers.CharField(
        source="route.name",
        read_only=True,
    )

    active_waiting_count = serializers.SerializerMethodField()

    class Meta:
        model = WaitingSpot
        fields = (
            "id",
            "route",
            "route_name",
            "name",
            "latitude",
            "longitude",
            "geofence_radius_meters",
            "is_active",
            "active_waiting_count",
            "created_at",
            "stop_order",
        )
        read_only_fields = (
            "id",
            "route_name",
            "active_waiting_count",
            "created_at",
            "stop_order",
        )

    def get_active_waiting_count(self, obj):
        annotated_count = getattr(
            obj,
            "active_waiting_count",
            None,
        )

        if annotated_count is not None:
            return annotated_count

        assigned_request_ids = (
            DispatchRequest.objects.filter(
                dispatch__status__in=[
                    DispatchAssignment.Status.PENDING,
                    DispatchAssignment.Status.ACCEPTED,
                    DispatchAssignment.Status.EN_ROUTE,
                ]
            ).values("waiting_request_id")
        )

        return (
            obj.waiting_requests
            .filter(
                status=WaitingRequest.Status.WAITING
            )
            .exclude(
                pk__in=assigned_request_ids
            )
            .aggregate(
                total=Sum("party_size")
            )["total"]
            or 0
        )

    def to_representation(self, instance):
        representation = super().to_representation(
            instance
        )

        request = self.context.get("request")

        if (
            request
            and request.user.role != "DISPATCHER"
        ):
            representation.pop(
                "active_waiting_count",
                None,
            )

        return representation

    def create(self, validated_data):
        route = validated_data["route"]

        with transaction.atomic():
            Route.objects.select_for_update().get(
                pk=route.pk
            )

            max_order = (
                WaitingSpot.objects
                .filter(route=route)
                .aggregate(
                    max_order=Max("stop_order")
                )["max_order"]
                or 0
            )

            validated_data["stop_order"] = (
                max_order + 1
            )

            return super().create(
                validated_data
            )


class RouteSerializer(serializers.ModelSerializer):
    waiting_spots = WaitingSpotSerializer(
        many=True,
        read_only=True,
    )

    class Meta:
        model = Route
        fields = (
            "id",
            "name",
            "origin",
            "destination",
            "is_active",
            "created_at",
            "waiting_spots",
        )
        read_only_fields = (
            "id",
            "created_at",
            "waiting_spots",
        )


class WaitingRequestSerializer(serializers.ModelSerializer):
    passenger_username = serializers.CharField(
        source="passenger.username",
        read_only=True,
    )

    waiting_spot_name = serializers.CharField(
        source="waiting_spot.name",
        read_only=True,
    )

    route_name = serializers.CharField(
        source="waiting_spot.route.name",
        read_only=True,
    )

    class Meta:
        model = WaitingRequest
        fields = (
            "id",
            "passenger_username",
            "waiting_spot",
            "waiting_spot_name",
            "route_name",
            "passenger_latitude",
            "passenger_longitude",
            "distance_from_spot_meters",
            "status",
            "checked_in_at",
            "ended_at",
            "party_size",
            "boarding_pin"
        )
        read_only_fields = fields


class PassengerCheckInSerializer(serializers.Serializer):
    waiting_spot = serializers.PrimaryKeyRelatedField(
        queryset=WaitingSpot.objects.select_related("route").filter(
            is_active=True,
            route__is_active=True,
        )
    )

    latitude = serializers.DecimalField(
        max_digits=9,
        decimal_places=6,
        min_value=Decimal("-90"),
        max_value=Decimal("90"),
    )

    party_size = serializers.IntegerField(
    min_value=1,
    max_value=15,
    default=1,
    )

    longitude = serializers.DecimalField(
        max_digits=9,
        decimal_places=6,
        min_value=Decimal("-180"),
        max_value=Decimal("180"),
    )

    def validate(self, attrs):
        passenger = self.context["request"].user
        waiting_spot = attrs["waiting_spot"]

        existing_request = WaitingRequest.objects.filter(
            passenger=passenger,
            status=WaitingRequest.Status.WAITING,
        ).first()

        if existing_request:
            raise serializers.ValidationError(
                {
                    "detail": (
                        "You already have an active waiting request "
                        f"at {existing_request.waiting_spot.name}."
                    )
                }
            )

        distance = calculate_distance_meters(
            attrs["latitude"],
            attrs["longitude"],
            waiting_spot.latitude,
            waiting_spot.longitude,
        )

        if distance > waiting_spot.geofence_radius_meters:
            raise serializers.ValidationError(
                {
                    "location": (
                        f"You are approximately {distance:.0f} metres "
                        f"from {waiting_spot.name}. You must be within "
                        f"{waiting_spot.geofence_radius_meters} metres."
                    )
                }
            )

        attrs["calculated_distance"] = distance

        return attrs

    def create(self, validated_data):
        passenger = self.context["request"].user

        distance = validated_data.pop(
            "calculated_distance"
        )

        latitude = validated_data.pop("latitude")
        longitude = validated_data.pop("longitude")

        waiting_spot = validated_data["waiting_spot"]

        party_size = validated_data.get(
            "party_size",
            1,
        )

        used_pins = set(
            WaitingRequest.objects.filter(
                waiting_spot=waiting_spot,
                status=WaitingRequest.Status.WAITING,
                boarding_pin__isnull=False,
            ).values_list(
                "boarding_pin",
                flat=True,
            )
        )

        available_pins = [
            f"{letter}{number:02d}"
            for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
            for number in range(1, 100)
            if f"{letter}{number:02d}" not in used_pins
        ]

        if not available_pins:
            raise serializers.ValidationError(
                {
                    "detail": (
                        "No boarding slots are currently "
                        "available at this waiting spot. "
                        "Please try again later."
                    )
                }
            )

        boarding_pin = secrets.choice(
            available_pins
        )

        return WaitingRequest.objects.create(
            passenger=passenger,
            waiting_spot=waiting_spot,
            party_size=party_size,
            boarding_pin=boarding_pin,
            passenger_latitude=latitude,
            passenger_longitude=longitude,
            distance_from_spot_meters=Decimal(
                f"{distance:.2f}"
            ),
        )

class PassengerLocationRevalidationSerializer(
    serializers.Serializer
):
    latitude = serializers.DecimalField(
        max_digits=9,
        decimal_places=6,
        min_value=Decimal("-90"),
        max_value=Decimal("90"),
    )

    longitude = serializers.DecimalField(
        max_digits=9,
        decimal_places=6,
        min_value=Decimal("-180"),
        max_value=Decimal("180"),
    )


class DriverAvailabilitySerializer(serializers.ModelSerializer):
    driver_id = serializers.IntegerField(
        source="driver.id",
        read_only=True,
    )

    driver_username = serializers.CharField(
        source="driver.username",
        read_only=True,
    )

    driver_name = serializers.SerializerMethodField()

    class Meta:
        model = DriverAvailability
        fields = (
            "driver_id",
            "driver_username",
            "driver_name",
            "is_available",
            "updated_at",
        )

        read_only_fields = (
            "driver_id",
            "driver_username",
            "driver_name",
            "updated_at",
        )

    def get_driver_name(self, obj):
        full_name = obj.driver.get_full_name().strip()
        return full_name or obj.driver.username


class AvailableDriverSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()

    phone_number = serializers.CharField(
        read_only=True
    )

    number_plate = serializers.CharField(
        read_only=True
    )

    class Meta:
        model = User

        fields = (
            "id",
            "username",
            "full_name",
            "phone_number",
            "number_plate",
        )

    def get_full_name(self, obj):
        full_name = (
            obj.get_full_name().strip()
        )

        return (
            full_name
            or obj.username
        )


class DispatchAssignmentSerializer(serializers.ModelSerializer):
    dispatcher_username = serializers.CharField(
        source="dispatcher.username",
        read_only=True,
    )

    driver_username = serializers.CharField(
        source="driver.username",
        read_only=True,
    )

    driver_name = serializers.SerializerMethodField()

    route_name = serializers.CharField(
        source="route.name",
        read_only=True,
    )

    pickup_spots = serializers.SerializerMethodField()

    status_display = serializers.CharField(
        source="get_status_display",
        read_only=True,
    )

    class Meta:
        model = DispatchAssignment

        fields = (
            "id",
            "dispatcher",
            "dispatcher_username",
            "driver",
            "driver_username",
            "driver_name",
            "route",
            "route_name",
            "passenger_count",
            "pickup_spots",
            "status",
            "status_display",
            "notes",
            "created_at",
            "responded_at",
        )

        read_only_fields = (
            "id",
            "dispatcher",
            "dispatcher_username",
            "driver_username",
            "driver_name",
            "route_name",
            "passenger_count",
            "pickup_spots",
            "status",
            "status_display",
            "created_at",
            "responded_at",
        )

    def get_driver_name(self, obj):
        full_name = obj.driver.get_full_name().strip()

        return full_name or obj.driver.username

    def get_pickup_spots(self, obj):
        links = (
            obj.dispatch_requests
            .select_related(
                "waiting_request__waiting_spot"
            )
            .all()
        )

        spots = {}

        for link in links:
            waiting_request = link.waiting_request
            waiting_spot = waiting_request.waiting_spot
            party_size = waiting_request.party_size

            if waiting_spot.id not in spots:
                spots[waiting_spot.id] = {
                    "id": waiting_spot.id,
                    "name": waiting_spot.name,
                    "assigned_count": 0,
                    "boarded_count": 0,
                    "waiting_count": 0,
                }

            spots[
                waiting_spot.id
            ]["assigned_count"] += party_size

            if link.boarded:
                spots[
                    waiting_spot.id
                ]["boarded_count"] += party_size

            elif (
                waiting_request.status
                == WaitingRequest.Status.WAITING
            ):
                spots[
                    waiting_spot.id
                ]["waiting_count"] += party_size

        return list(spots.values())

    def validate_driver(self, driver):
        if driver.role != "DRIVER":
            raise serializers.ValidationError(
                "The selected user is not a driver."
            )

        return driver

    def validate_route(self, route):
        if not route.is_active:
            raise serializers.ValidationError(
                "The selected route is inactive."
            )

        return route

    def validate(self, attrs):
        driver = attrs["driver"]
        route = attrs["route"]

        availability, _ = (
            DriverAvailability.objects.get_or_create(
                driver=driver
            )
        )

        if not availability.is_available:
            raise serializers.ValidationError(
                {
                    "driver": (
                        "The selected driver is currently "
                        "unavailable."
                    )
                }
            )

        active_statuses = [
            DispatchAssignment.Status.PENDING,
            DispatchAssignment.Status.ACCEPTED,
            DispatchAssignment.Status.EN_ROUTE,
        ]

        active_dispatch_exists = (
            DispatchAssignment.objects.filter(
                driver=driver,
                status__in=active_statuses,
            ).exists()
        )

        if active_dispatch_exists:
            raise serializers.ValidationError(
                {
                    "driver": (
                        "The selected driver already has "
                        "an active dispatch assignment."
                    )
                }
            )

        already_assigned_ids = (
            DispatchRequest.objects.filter(
                dispatch__status__in=active_statuses
            )
            .values_list(
                "waiting_request_id",
                flat=True,
            )
        )

        waiting_requests_exist = (
            WaitingRequest.objects.filter(
                waiting_spot__route=route,
                waiting_spot__is_active=True,
                status=WaitingRequest.Status.WAITING,
            )
            .exclude(
                id__in=already_assigned_ids
            )
            .exists()
        )

        if not waiting_requests_exist:
            raise serializers.ValidationError(
                {
                    "route": (
                        "There are no unassigned waiting "
                        "passengers on this route."
                    )
                }
            )

        return attrs

    def create(self, validated_data):
        request = self.context["request"]

        driver = validated_data["driver"]
        route = validated_data["route"]

        active_statuses = [
            DispatchAssignment.Status.PENDING,
            DispatchAssignment.Status.ACCEPTED,
            DispatchAssignment.Status.EN_ROUTE,
        ]

        try:
            with transaction.atomic():
                # Allocate passengers to one taxi at a time on this route.
                route = (
                    Route.objects
                    .select_for_update()
                    .get(pk=route.pk)
                )

                availability, _ = (
                    DriverAvailability.objects
                    .select_for_update()
                    .get_or_create(
                        driver=driver
                    )
                )

                if not availability.is_available:
                    raise serializers.ValidationError(
                        {
                            "driver": (
                                "This driver is no longer "
                                "available."
                            )
                        }
                    )

                active_dispatch_exists = (
                    DispatchAssignment.objects.filter(
                        driver=driver,
                        status__in=active_statuses,
                    ).exists()
                )

                if active_dispatch_exists:
                    raise serializers.ValidationError(
                        {
                            "driver": (
                                "This driver already has an "
                                "active dispatch assignment."
                            )
                        }
                    )

                already_assigned_ids = (
                    DispatchRequest.objects.filter(
                        dispatch__status__in=(
                            active_statuses
                        )
                    )
                    .values_list(
                        "waiting_request_id",
                        flat=True,
                    )
                )

                candidate_requests = list(
                    WaitingRequest.objects
                    .select_for_update()
                    .filter(
                        waiting_spot__route=route,
                        waiting_spot__is_active=True,
                        status=(
                            WaitingRequest.Status.WAITING
                        ),
                    )
                    .exclude(
                        id__in=already_assigned_ids
                    )
                    .select_related(
                        "waiting_spot",
                        "passenger",
                    )
                    .order_by(
                        "checked_in_at",
                        "id",
                    )
                )

                if not candidate_requests:
                    raise serializers.ValidationError(
                        {
                            "route": (
                                "There are no unassigned "
                                "waiting passengers on "
                                "this route."
                            )
                        }
                    )

                remaining_capacity = 15
                selected_requests = []

                for waiting_request in candidate_requests:
                    if (
                        waiting_request.party_size
                        <= remaining_capacity
                    ):
                        selected_requests.append(
                            waiting_request
                        )

                        remaining_capacity -= (
                            waiting_request.party_size
                        )

                        if remaining_capacity == 0:
                            break

                if not selected_requests:
                    raise serializers.ValidationError(
                        {
                            "route": (
                                "No waiting group can fit "
                                "in this taxi."
                            )
                        }
                    )

                passenger_count = sum(
                    waiting_request.party_size
                    for waiting_request
                    in selected_requests
                )

                selected_request_ids = [
                    waiting_request.id
                    for waiting_request in selected_requests
                ]

                reassigned_request_ids = set(
                    DispatchRequest.objects
                    .filter(
                        waiting_request_id__in=(
                            selected_request_ids
                        ),
                        dispatch__status__in=[
                            DispatchAssignment.Status.REJECTED,
                            DispatchAssignment.Status.CANCELLED,
                        ],
                    )
                    .values_list(
                        "waiting_request_id",
                        flat=True,
                    )
                )

                assignment = (
                    DispatchAssignment.objects.create(
                        dispatcher=request.user,
                        driver=driver,
                        route=route,
                        waiting_spot=None,
                        passenger_count=(
                            passenger_count
                        ),
                        notes=validated_data.get(
                            "notes",
                            "",
                        ),
                    )
                )

                DispatchRequest.objects.bulk_create(
                    [
                        DispatchRequest(
                            dispatch=assignment,
                            waiting_request=(
                                waiting_request
                            ),
                        )
                        for waiting_request
                        in selected_requests
                    ]
                )

                availability.is_available = False

                availability.save(
                    update_fields=[
                        "is_available",
                        "updated_at",
                    ]
                )

                if reassigned_request_ids:
                    create_notification(
                        recipient=driver,
                        notification_type=(
                            Notification.Type.DISPATCH_REASSIGNED
                        ),
                        title="Reassigned dispatch",
                        message=(
                            f"You have been assigned passengers "
                            f"waiting on {route.name}."
                        ),
                        dispatch=assignment,
                    )

                    for waiting_request in selected_requests:
                        if (
                            waiting_request.id
                            not in reassigned_request_ids
                        ):
                            continue

                        create_notification(
                            recipient=(
                                waiting_request.passenger
                            ),
                            notification_type=(
                                Notification.Type.DISPATCH_REASSIGNED
                            ),
                            title="Taxi reassigned",
                            message=(
                                "A new driver has been assigned "
                                "to your request."
                            ),
                            dispatch=assignment,
                        )

                else:
                    create_notification(
                        recipient=driver,
                        notification_type=(
                            Notification.Type.NEW_DISPATCH
                        ),
                        title="New dispatch",
                        message=(
                            f"You have been assigned to "
                            f"{route.name}."
                        ),
                        dispatch=assignment,
                    )

                return assignment

        except IntegrityError:
            raise serializers.ValidationError(
                {
                    "driver": (
                        "This driver already has an "
                        "active dispatch."
                    )
                }
            )

class NotificationSerializer(
    serializers.ModelSerializer
):
    class Meta:
        model = Notification

        fields = (
            "id",
            "notification_type",
            "title",
            "message",
            "dispatch",
            "is_read",
            "created_at",
        )

        read_only_fields = fields


class DeviceTokenSerializer(
    serializers.Serializer
):
    token = serializers.CharField()

    platform = serializers.ChoiceField(
        choices=DeviceToken.Platform.choices
    )