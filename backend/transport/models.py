from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class Route(models.Model):
    name = models.CharField(max_length=100, unique=True)
    origin = models.CharField(max_length=100)
    destination = models.CharField(max_length=100)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name}: {self.origin} → {self.destination}"


class WaitingSpot(models.Model):
    route = models.ForeignKey(
        Route,
        on_delete=models.CASCADE,
        related_name="waiting_spots",
    )
    name = models.CharField(max_length=100)

    latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        validators=[
            MinValueValidator(-90),
            MaxValueValidator(90),
        ],
    )

    longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        validators=[
            MinValueValidator(-180),
            MaxValueValidator(180),
        ],
    )

    geofence_radius_meters = models.PositiveIntegerField(
        default=100,
        validators=[
            MinValueValidator(20),
            MaxValueValidator(1000),
        ],
    )

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["route__name", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["route", "name"],
                name="unique_waiting_spot_per_route",
            )
        ]

    def __str__(self):
        return f"{self.name} — {self.route.name}"


class WaitingRequest(models.Model):

    
    class Status(models.TextChoices):
        WAITING = "WAITING", "Waiting"
        CANCELLED = "CANCELLED", "Cancelled"
        BOARDED = "BOARDED", "Boarded"

    passenger = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="waiting_requests",
    )

    waiting_spot = models.ForeignKey(
        WaitingSpot,
        on_delete=models.PROTECT,
        related_name="waiting_requests",
    )

    passenger_latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
    )

    passenger_longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
    )

    distance_from_spot_meters = models.DecimalField(
        max_digits=8,
        decimal_places=2,
    )

    party_size = models.PositiveSmallIntegerField(
    default=1,
    validators=[
        MinValueValidator(1),
        MaxValueValidator(15),
    ],
    )

    boarding_pin = models.CharField(
    max_length=3,
    null=True,
    blank=True,
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.WAITING,
    )

    checked_in_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    outside_geofence_since = models.DateTimeField(null=True,blank=True,)

    class Meta:
        ordering = ["-checked_in_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["passenger"],
                condition=models.Q(status="WAITING"),
                name="one_active_waiting_request_per_passenger",
            ), 

            models.UniqueConstraint(
                fields=[
                    "waiting_spot",
                    "boarding_pin",
                ],
                condition=models.Q(
                    status="WAITING",
                    boarding_pin__isnull=False,
                ),
                name="unique_active_boarding_pin_per_spot",
            ),
        ]

    def __str__(self):
        return (
            f"{self.passenger.username} — "
            f"{self.waiting_spot.name} — "
            f"{self.get_status_display()}"
        )

class DriverAvailability(models.Model):
    driver = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="driver_availability",
    )

    is_available = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Driver availability"

    def __str__(self):
        status = "Available" if self.is_available else "Unavailable"
        return f"{self.driver.username} — {status}"


class DispatchAssignment(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        ACCEPTED = "ACCEPTED", "Accepted"
        REJECTED = "REJECTED", "Rejected"
        EN_ROUTE = "EN_ROUTE", "En route"
        COMPLETED = "COMPLETED", "Completed"
        CANCELLED = "CANCELLED", "Cancelled"

    dispatcher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_dispatches",
    )

    driver = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="driver_dispatches",
    )

    route = models.ForeignKey(
        Route,
        on_delete=models.PROTECT,
        related_name="dispatch_assignments",
        null=True,
        blank=True,
    )

    waiting_spot = models.ForeignKey(
        WaitingSpot,
        on_delete=models.PROTECT,
        related_name="dispatch_assignments",
        null=True,
        blank=True,
    )

    passenger_count = models.PositiveIntegerField()

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )

    notes = models.CharField(
        max_length=250,
        blank=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    responded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

        constraints = [
            models.CheckConstraint(
                condition=models.Q(passenger_count__gte=1),
                name="dispatch_passenger_count_at_least_one",
            ),

            models.UniqueConstraint(
                fields=["driver"],
                condition=models.Q(
                    status__in=[
                        "PENDING",
                        "ACCEPTED",
                        "EN_ROUTE",
                    ]
                ),
                name="one_active_dispatch_per_driver",
            ),
        ]

    def __str__(self):
        destination = (
            self.route.name
            if self.route
            else self.waiting_spot.name
            if self.waiting_spot
            else "Unknown route"
        )

        return (
            f"{self.driver.username} → "
            f"{destination} — "
            f"{self.get_status_display()}"
        )

class DispatchRequest(models.Model):
    dispatch = models.ForeignKey(
        DispatchAssignment,
        on_delete=models.PROTECT,
        related_name="dispatch_requests",
    )

    waiting_request = models.ForeignKey(
        WaitingRequest,
        on_delete=models.PROTECT,
        related_name="dispatch_requests",
    )

    boarded = models.BooleanField(default=False)

    boarded_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["dispatch", "waiting_request"],
                name="unique_waiting_request_per_dispatch",
            )
        ]

    def __str__(self):
        return (
            f"Dispatch {self.dispatch_id} — "
            f"Waiting Request {self.waiting_request_id}"
        )

class Trip(models.Model):
    dispatch = models.OneToOneField(
        DispatchAssignment,
        on_delete=models.PROTECT,
        related_name="trip",
    )

    boarded_passenger_count = models.PositiveIntegerField(
        default=0,
    )

    en_route_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    arrived_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    boarding_confirmed_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    completed_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    def __str__(self):
        return f"Trip for Dispatch {self.dispatch_id}"