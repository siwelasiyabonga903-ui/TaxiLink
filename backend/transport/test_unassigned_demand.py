from django.contrib.auth import get_user_model
from django.urls import reverse

from rest_framework import status
from rest_framework.test import APITestCase

from .models import (
    DispatchAssignment,
    DispatchRequest,
    Route,
    WaitingRequest,
    WaitingSpot,
)


User = get_user_model()


class UnassignedDemandTests(APITestCase):
    def setUp(self):
        self.dispatcher = User.objects.create_user(
            username="unassigned_demand_dispatcher",
            email="unassigned_demand_dispatcher@example.com",
            password="StrongPass123!",
            role="DISPATCHER",
        )

        self.driver = User.objects.create_user(
            username="unassigned_demand_driver",
            email="unassigned_demand_driver@example.com",
            password="StrongPass123!",
            role="DRIVER",
        )

        passenger = User.objects.create_user(
            username="unassigned_demand_passenger",
            email="unassigned_demand_passenger@example.com",
            password="StrongPass123!",
            role="PASSENGER",
        )

        self.route = Route.objects.create(
            name="Unassigned Demand Route",
            origin="Campus",
            destination="Town",
        )

        self.spot = WaitingSpot.objects.create(
            route=self.route,
            name="Demand Stop",
            latitude="-23.884500",
            longitude="29.738200",
            geofence_radius_meters=100,
        )

        self.waiting_request = WaitingRequest.objects.create(
            passenger=passenger,
            waiting_spot=self.spot,
            party_size=7,
            boarding_pin="D01",
            passenger_latitude=self.spot.latitude,
            passenger_longitude=self.spot.longitude,
            distance_from_spot_meters="0.00",
        )

        self.client.force_authenticate(user=self.dispatcher)

    def assert_demand(self, expected):
        route_response = self.client.get(
            reverse(
                "route-detail",
                kwargs={"pk": self.route.pk},
            )
        )

        spot_response = self.client.get(
            reverse(
                "waiting-spot-detail",
                kwargs={"pk": self.spot.pk},
            )
        )

        self.assertEqual(
            route_response.status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(
            spot_response.status_code,
            status.HTTP_200_OK,
        )

        self.assertEqual(
            route_response.data["waiting_spots"][0][
                "active_waiting_count"
            ],
            expected,
        )
        self.assertEqual(
            spot_response.data["active_waiting_count"],
            expected,
        )

    def test_demand_follows_active_dispatches(self):
        self.assert_demand(7)

        assignment = DispatchAssignment.objects.create(
            dispatcher=self.dispatcher,
            driver=self.driver,
            route=self.route,
            passenger_count=7,
        )
        DispatchRequest.objects.create(
            dispatch=assignment,
            waiting_request=self.waiting_request,
        )

        # Assigned, even before the driver accepts.
        self.assert_demand(0)

        assignment.status = DispatchAssignment.Status.EN_ROUTE
        assignment.save(update_fields=["status"])
        self.assert_demand(0)

        new_passenger = User.objects.create_user(
            username="new_unassigned_passenger",
            email="new_unassigned_passenger@example.com",
            password="StrongPass123!",
            role="PASSENGER",
        )
        WaitingRequest.objects.create(
            passenger=new_passenger,
            waiting_spot=self.spot,
            party_size=3,
            boarding_pin="D02",
            passenger_latitude=self.spot.latitude,
            passenger_longitude=self.spot.longitude,
            distance_from_spot_meters="0.00",
        )

        # A later arrival still needs a taxi.
        self.assert_demand(3)

        assignment.status = DispatchAssignment.Status.CANCELLED
        assignment.save(update_fields=["status"])
        self.assert_demand(10)

        replacement = DispatchAssignment.objects.create(
            dispatcher=self.dispatcher,
            driver=self.driver,
            route=self.route,
            passenger_count=7,
        )
        DispatchRequest.objects.create(
            dispatch=replacement,
            waiting_request=self.waiting_request,
        )

        # The old cancelled link must not inflate the count.
        self.assert_demand(3)

        replacement.status = DispatchAssignment.Status.REJECTED
        replacement.save(update_fields=["status"])
        self.assert_demand(10)