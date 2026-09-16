from django.contrib import admin

from .models import (
    DispatchAssignment,
    DriverAvailability,
    Route,
    WaitingRequest,
    WaitingSpot,
)


class WaitingSpotInline(admin.TabularInline):
    model = WaitingSpot
    extra = 0


@admin.register(Route)
class RouteAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "origin",
        "destination",
        "is_active",
    )

    list_filter = ("is_active",)
    search_fields = ("name", "origin", "destination")
    inlines = [WaitingSpotInline]


@admin.register(WaitingSpot)
class WaitingSpotAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "route",
        "geofence_radius_meters",
        "is_active",
    )

    list_filter = ("is_active", "route")
    search_fields = ("name", "route__name")


@admin.register(WaitingRequest)
class WaitingRequestAdmin(admin.ModelAdmin):
    list_display = (
        "passenger",
        "waiting_spot",
        "status",
        "distance_from_spot_meters",
        "checked_in_at",
    )

    list_filter = (
        "status",
        "waiting_spot",
        "waiting_spot__route",
    )

    search_fields = (
        "passenger__username",
        "waiting_spot__name",
    )

    readonly_fields = (
        "passenger",
        "waiting_spot",
        "passenger_latitude",
        "passenger_longitude",
        "distance_from_spot_meters",
        "checked_in_at",
        "ended_at",
    )

@admin.register(DriverAvailability)
class DriverAvailabilityAdmin(admin.ModelAdmin):
    list_display = (
        "driver",
        "is_available",
        "updated_at",
    )

    list_filter = ("is_available",)
    search_fields = ("driver__username",)


@admin.register(DispatchAssignment)
class DispatchAssignmentAdmin(admin.ModelAdmin):
    list_display = (
        "driver",
        "waiting_spot",
        "passenger_count",
        "status",
        "dispatcher",
        "created_at",
    )

    list_filter = (
        "status",
        "waiting_spot",
        "waiting_spot__route",
    )

    search_fields = (
        "driver__username",
        "dispatcher__username",
        "waiting_spot__name",
    )

    readonly_fields = (
        "created_at",
        "responded_at",
    )