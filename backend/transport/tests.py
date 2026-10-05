from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from django.utils import timezone
from datetime import timedelta
from unittest.mock import patch
import json
from urllib.error import URLError

from .models import (
    DispatchAssignment,
    DriverAvailability,
    DriverLocation,
    Route,
    Trip,
    WaitingSpot,
    DispatchRequest,
    WaitingRequest,
    Notification,
)


User = get_user_model()


class DispatchRejectionTests(APITestCase):
    def setUp(self):
        self.dispatcher = User.objects.create_user(
            username="dispatcher1",
            email="dispatcher1@example.com",
            password="StrongPass123!",
            role="DISPATCHER",
        )

        self.driver = User.objects.create_user(
            username="driver1",
            email="driver1@example.com",
            password="StrongPass123!",
            role="DRIVER",
        )

        self.other_driver = User.objects.create_user(
            username="driver2",
            email="driver2@example.com",
            password="StrongPass123!",
            role="DRIVER",
        )

        self.route = Route.objects.create(
            name="Campus to Town",
            origin="Campus",
            destination="Town",
        )

        self.waiting_spot = WaitingSpot.objects.create(
            route=self.route,
            name="Main Gate",
            latitude="-23.884500",
            longitude="29.738200",
            geofence_radius_meters=100,
        )

        self.availability = DriverAvailability.objects.create(
            driver=self.driver,
            is_available=False,
        )

        DriverAvailability.objects.create(
            driver=self.other_driver,
            is_available=False,
        )

        self.assignment = DispatchAssignment.objects.create(
            dispatcher=self.dispatcher,
            driver=self.driver,
            waiting_spot=self.waiting_spot,
            passenger_count=3,
            status=DispatchAssignment.Status.PENDING,
        )

    def reject_url(self, assignment=None):
        assignment = assignment or self.assignment

        return reverse(
            "dispatch-reject",
            kwargs={"pk": assignment.pk},
        )

    def test_driver_can_reject_own_pending_dispatch(self):
        self.client.force_authenticate(user=self.driver)

        response = self.client.post(self.reject_url())

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.assignment.refresh_from_db()

        self.assertEqual(
            self.assignment.status,
            DispatchAssignment.Status.REJECTED,
        )

        self.assertIsNotNone(
            self.assignment.responded_at
        )

    def test_rejection_makes_driver_available_again(self):
        self.client.force_authenticate(user=self.driver)

        response = self.client.post(self.reject_url())

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.availability.refresh_from_db()

        self.assertTrue(
            self.availability.is_available
        )

    def test_driver_cannot_reject_non_pending_dispatch(self):
        self.assignment.status = (
            DispatchAssignment.Status.ACCEPTED
        )

        self.assignment.save(
            update_fields=["status"]
        )

        self.client.force_authenticate(user=self.driver)

        response = self.client.post(
            self.reject_url()
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

        self.assignment.refresh_from_db()

        self.assertEqual(
            self.assignment.status,
            DispatchAssignment.Status.ACCEPTED,
        )

    def test_driver_cannot_reject_another_drivers_dispatch(self):
        self.client.force_authenticate(
            user=self.other_driver
        )

        response = self.client.post(
            self.reject_url()
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND,
        )

        self.assignment.refresh_from_db()

        self.assertEqual(
            self.assignment.status,
            DispatchAssignment.Status.PENDING,
        )

    def test_waiting_passenger_can_be_dispatched_again_after_rejection(
    self
    ):
        passenger = User.objects.create_user(
            username="rejected_passenger",
            email="rejected_passenger@example.com",
            password="StrongPass123!",
            role="PASSENGER",
        )

        waiting_request = WaitingRequest.objects.create(
            passenger=passenger,
            waiting_spot=self.waiting_spot,
            party_size=2,
            boarding_pin="R21",
            passenger_latitude=self.waiting_spot.latitude,
            passenger_longitude=self.waiting_spot.longitude,
            distance_from_spot_meters="0.00",
        )

        DispatchRequest.objects.create(
            dispatch=self.assignment,
            waiting_request=waiting_request,
        )

        self.client.force_authenticate(
            user=self.driver
        )

        reject_response = self.client.post(
            self.reject_url()
        )

        self.assertEqual(
            reject_response.status_code,
            status.HTTP_200_OK,
        )

        waiting_request.refresh_from_db()

        self.assertEqual(
            waiting_request.status,
            WaitingRequest.Status.WAITING,
        )

        self.client.force_authenticate(
            user=self.dispatcher
        )

        second_response = self.client.post(
            reverse("dispatch-list"),
            {
                "driver": self.driver.id,
                "route": self.route.id,
                "notes": "Replacement dispatch.",
            },
            format="json",
        )

        self.assertEqual(
            second_response.status_code,
            status.HTTP_201_CREATED,
        )

        new_assignment = (
            DispatchAssignment.objects.get(
                pk=second_response.data["id"]
            )
        )

        self.assertTrue(
            DispatchRequest.objects.filter(
                dispatch=new_assignment,
                waiting_request=waiting_request,
            ).exists()
        )

    def test_rejection_notifies_waiting_passenger_and_dispatcher(
        self
    ):
        passenger = User.objects.create_user(
            username="reject_notify_passenger",
            email="reject_notify_passenger@example.com",
            password="StrongPass123!",
            role="PASSENGER",
        )

        waiting_request = WaitingRequest.objects.create(
            passenger=passenger,
            waiting_spot=self.waiting_spot,
            party_size=2,
            boarding_pin="R31",
            passenger_latitude=self.waiting_spot.latitude,
            passenger_longitude=self.waiting_spot.longitude,
            distance_from_spot_meters="0.00",
        )

        DispatchRequest.objects.create(
            dispatch=self.assignment,
            waiting_request=waiting_request,
        )

        self.client.force_authenticate(
            user=self.driver
        )

        response = self.client.post(
            self.reject_url()
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        notifications = Notification.objects.filter(
            dispatch=self.assignment,
            notification_type=(
                Notification.Type.DISPATCH_REJECTED
            ),
        )

        recipient_ids = set(
            notifications.values_list(
                "recipient_id",
                flat=True,
            )
        )

        self.assertEqual(
            recipient_ids,
            {
                passenger.id,
                self.dispatcher.id,
            },
        )

        self.assertEqual(
            notifications.count(),
            2,
        )

    def test_reassignment_notifies_passenger_and_new_driver(
        self
    ):
        passenger = User.objects.create_user(
            username="reassigned_passenger",
            email="reassigned_passenger@example.com",
            password="StrongPass123!",
            role="PASSENGER",
        )

        waiting_request = WaitingRequest.objects.create(
            passenger=passenger,
            waiting_spot=self.waiting_spot,
            party_size=2,
            boarding_pin="R42",
            passenger_latitude=self.waiting_spot.latitude,
            passenger_longitude=self.waiting_spot.longitude,
            distance_from_spot_meters="0.00",
        )

        DispatchRequest.objects.create(
            dispatch=self.assignment,
            waiting_request=waiting_request,
        )

        self.client.force_authenticate(
            user=self.driver
        )

        reject_response = self.client.post(
            self.reject_url()
        )

        self.assertEqual(
            reject_response.status_code,
            status.HTTP_200_OK,
        )

        other_availability = (
            DriverAvailability.objects.get(
                driver=self.other_driver
            )
        )

        other_availability.is_available = True
        other_availability.save(
            update_fields=[
                "is_available",
                "updated_at",
            ]
        )

        self.client.force_authenticate(
            user=self.dispatcher
        )

        response = self.client.post(
            reverse("dispatch-list"),
            {
                "driver": self.other_driver.id,
                "route": self.route.id,
                "notes": "Replacement dispatch.",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )

        new_assignment = (
            DispatchAssignment.objects.get(
                pk=response.data["id"]
            )
        )

        notifications = (
            Notification.objects
            .filter(
                dispatch=new_assignment,
                notification_type=(
                    Notification.Type.DISPATCH_REASSIGNED
                ),
            )
        )

        recipient_ids = set(
            notifications.values_list(
                "recipient_id",
                flat=True,
            )
        )

        self.assertEqual(
            recipient_ids,
            {
                passenger.id,
                self.other_driver.id,
            },
        )

        self.assertEqual(
            notifications.count(),
            2,
        )

        self.assertFalse(
            Notification.objects.filter(
                dispatch=new_assignment,
                recipient=self.other_driver,
                notification_type=(
                    Notification.Type.NEW_DISPATCH
                ),
            ).exists()
        )



class DispatchRequestTests(APITestCase):
    def setUp(self):
        self.dispatcher = User.objects.create_user(
            username="dispatcher_route",
            email="dispatcher_route@example.com",
            password="StrongPass123!",
            role="DISPATCHER",
        )

        self.driver = User.objects.create_user(
            username="driver_route",
            email="driver_route@example.com",
            password="StrongPass123!",
            role="DRIVER",
        )

        DriverAvailability.objects.create(
            driver=self.driver,
            is_available=True,
        )

        self.route = Route.objects.create(
            name="Campus to Town",
            origin="Campus",
            destination="Town",
        )

        self.other_route = Route.objects.create(
            name="Campus to Mall",
            origin="Campus",
            destination="Mall",
        )

        self.spot_one = WaitingSpot.objects.create(
            route=self.route,
            name="Main Gate",
            latitude="-23.884500",
            longitude="29.738200",
            geofence_radius_meters=100,
        )

        self.spot_two = WaitingSpot.objects.create(
            route=self.route,
            name="Library",
            latitude="-23.885000",
            longitude="29.739000",
            geofence_radius_meters=100,
        )

        self.inactive_spot = WaitingSpot.objects.create(
            route=self.route,
            name="Old Gate",
            latitude="-23.886000",
            longitude="29.740000",
            geofence_radius_meters=100,
            is_active=False,
        )

        self.other_route_spot = WaitingSpot.objects.create(
            route=self.other_route,
            name="Mall Stop",
            latitude="-23.887000",
            longitude="29.741000",
            geofence_radius_meters=100,
        )

        self.active_route_requests = []

        for index, spot in enumerate(
            [
                self.spot_one,
                self.spot_one,
                self.spot_two,
            ]
        ):
            passenger = User.objects.create_user(
                username=f"route_passenger_{index}",
                email=f"route_passenger_{index}@example.com",
                password="StrongPass123!",
                role="PASSENGER",
            )

            waiting_request = WaitingRequest.objects.create(
                passenger=passenger,
                waiting_spot=spot,
                passenger_latitude=spot.latitude,
                passenger_longitude=spot.longitude,
                distance_from_spot_meters="0.00",
            )

            self.active_route_requests.append(
                waiting_request
            )

        inactive_passenger = User.objects.create_user(
            username="inactive_spot_passenger",
            email="inactive_spot_passenger@example.com",
            password="StrongPass123!",
            role="PASSENGER",
        )

        self.inactive_request = WaitingRequest.objects.create(
            passenger=inactive_passenger,
            waiting_spot=self.inactive_spot,
            passenger_latitude=self.inactive_spot.latitude,
            passenger_longitude=self.inactive_spot.longitude,
            distance_from_spot_meters="0.00",
        )

        other_passenger = User.objects.create_user(
            username="other_route_passenger",
            email="other_route_passenger@example.com",
            password="StrongPass123!",
            role="PASSENGER",
        )

        self.other_route_request = WaitingRequest.objects.create(
            passenger=other_passenger,
            waiting_spot=self.other_route_spot,
            passenger_latitude=self.other_route_spot.latitude,
            passenger_longitude=self.other_route_spot.longitude,
            distance_from_spot_meters="0.00",
        )

    def create_dispatch(self):
        self.client.force_authenticate(
            user=self.dispatcher
        )

        return self.client.post(
            reverse("dispatch-list"),
            {
                "driver": self.driver.id,
                "route": self.route.id,
                "notes": "Collect passengers on this route.",
            },
            format="json",
        )

    def test_dispatch_links_requests_from_all_active_spots_on_route(self):
        response = self.create_dispatch()

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )

        assignment = DispatchAssignment.objects.get()

        self.assertEqual(
            assignment.route,
            self.route,
        )

        self.assertIsNone(
            assignment.waiting_spot
        )

        links = DispatchRequest.objects.filter(
            dispatch=assignment
        )

        linked_ids = set(
            links.values_list(
                "waiting_request_id",
                flat=True,
            )
        )

        expected_ids = {
            waiting_request.id
            for waiting_request
            in self.active_route_requests
        }

        self.assertEqual(
            linked_ids,
            expected_ids,
        )

    def test_dispatch_excludes_inactive_spots_and_other_routes(self):
        response = self.create_dispatch()

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )

        assignment = DispatchAssignment.objects.get()

        linked_ids = set(
            DispatchRequest.objects.filter(
                dispatch=assignment
            ).values_list(
                "waiting_request_id",
                flat=True,
            )
        )

        self.assertNotIn(
            self.inactive_request.id,
            linked_ids,
        )

        self.assertNotIn(
            self.other_route_request.id,
            linked_ids,
        )

    def test_passenger_count_is_calculated_automatically(self):
        response = self.create_dispatch()

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )

        assignment = DispatchAssignment.objects.get()

        self.assertEqual(
            assignment.passenger_count,
            3,
        )

    def test_dispatch_makes_driver_unavailable(self):
        response = self.create_dispatch()

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )

        availability = DriverAvailability.objects.get(
            driver=self.driver
        )

        self.assertFalse(
            availability.is_available
        
        )

    def test_dispatch_maximises_capacity_without_splitting_groups(self):
        # Remove the requests created by setUp so this test
        # has complete control over route demand.
        WaitingRequest.objects.filter(
            waiting_spot__route=self.route
        ).delete()

        groups = [
            (self.spot_one, 8),
            (self.spot_two, 5),
            (self.spot_one, 4),
            (self.spot_two, 1),
            (self.spot_one, 1),
        ]

        created_requests = []

        for index, (spot, party_size) in enumerate(groups):
            passenger = User.objects.create_user(
                username=f"capacity_passenger_{index}",
                email=f"capacity_passenger_{index}@example.com",
                password="StrongPass123!",
                role="PASSENGER",
            )

            waiting_request = WaitingRequest.objects.create(
                passenger=passenger,
                waiting_spot=spot,
                party_size=party_size,
                boarding_pin=f"{20 + index}",
                passenger_latitude=spot.latitude,
                passenger_longitude=spot.longitude,
                distance_from_spot_meters="0.00",
            )

            created_requests.append(waiting_request)

        response = self.create_dispatch()

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )

        assignment = DispatchAssignment.objects.get(
            pk=response.data["id"]
        )

        # 8 + 5 + 1 + 1 = full 15-seat taxi.
        self.assertEqual(
            assignment.passenger_count,
            15,
        )

        linked_ids = set(
            DispatchRequest.objects.filter(
                dispatch=assignment
            ).values_list(
                "waiting_request_id",
                flat=True,
            )
        )

        # A = 8
        self.assertIn(
            created_requests[0].id,
            linked_ids,
        )

        # B = 5
        self.assertIn(
            created_requests[1].id,
            linked_ids,
        )

        # C = 4 cannot fit after A+B,
        # so it remains waiting.
        self.assertNotIn(
            created_requests[2].id,
            linked_ids,
        )

        # D = 1 fits.
        self.assertIn(
            created_requests[3].id,
            linked_ids,
        )

        # E = 1 fits and fills seat 15.
        self.assertIn(
            created_requests[4].id,
            linked_ids,
        )

        created_requests[2].refresh_from_db()

        self.assertEqual(
            created_requests[2].status,
            WaitingRequest.Status.WAITING,
        )

    def test_new_dispatch_notifies_driver(
            self
        ):
            response = self.create_dispatch()

            self.assertEqual(
                response.status_code,
                status.HTTP_201_CREATED,
            )

            assignment = (
                DispatchAssignment.objects.get(
                    pk=response.data["id"]
                )
            )

            notification = (
                Notification.objects.get(
                    recipient=self.driver,
                    notification_type=(
                        Notification.Type.NEW_DISPATCH
                    ),
                )
            )

            self.assertEqual(
                notification.dispatch,
                assignment,
            )

            self.assertEqual(
                notification.title,
                "New dispatch",
            )

            self.assertFalse(
                notification.is_read
            )

class AcceptStartsTripTests(APITestCase):
    def setUp(self):
        self.dispatcher = User.objects.create_user(
            username="dispatcher_accept",
            email="dispatcher_accept@example.com",
            password="StrongPass123!",
            role="DISPATCHER",
        )

        self.driver = User.objects.create_user(
            username="driver_accept",
            email="driver_accept@example.com",
            password="StrongPass123!",
            role="DRIVER",
        )

        self.other_driver = User.objects.create_user(
            username="other_driver_accept",
            email="other_driver_accept@example.com",
            password="StrongPass123!",
            role="DRIVER",
        )

        DriverAvailability.objects.create(
            driver=self.driver,
            is_available=False,
        )

        self.route = Route.objects.create(
            name="Accept Test Route",
            origin="Campus",
            destination="Town",
        )

        self.waiting_spot = WaitingSpot.objects.create(
            route=self.route,
            name="Main Gate",
            latitude="-23.884500",
            longitude="29.738200",
            geofence_radius_meters=100,
        )

        self.assignment = (
            DispatchAssignment.objects.create(
                dispatcher=self.dispatcher,
                driver=self.driver,
                route=self.route,
                waiting_spot=None,
                passenger_count=2,
                status=(
                    DispatchAssignment.Status.PENDING
                ),
            )
        )

        self.passenger_one = User.objects.create_user(
            username="accept_passenger_one",
            email="accept_passenger_one@example.com",
            password="StrongPass123!",
            role="PASSENGER",
        )

        self.passenger_two = User.objects.create_user(
            username="accept_passenger_two",
            email="accept_passenger_two@example.com",
            password="StrongPass123!",
            role="PASSENGER",
        )

        self.waiting_request_one = (
            WaitingRequest.objects.create(
                passenger=self.passenger_one,
                waiting_spot=self.waiting_spot,
                party_size=1,
                boarding_pin="A31",
                passenger_latitude=(
                    self.waiting_spot.latitude
                ),
                passenger_longitude=(
                    self.waiting_spot.longitude
                ),
                distance_from_spot_meters="0.00",
            )
        )

        self.waiting_request_two = (
            WaitingRequest.objects.create(
                passenger=self.passenger_two,
                waiting_spot=self.waiting_spot,
                party_size=1,
                boarding_pin="A32",
                passenger_latitude=(
                    self.waiting_spot.latitude
                ),
                passenger_longitude=(
                    self.waiting_spot.longitude
                ),
                distance_from_spot_meters="0.00",
            )
        )

        DispatchRequest.objects.create(
            dispatch=self.assignment,
            waiting_request=self.waiting_request_one,
        )

        DispatchRequest.objects.create(
            dispatch=self.assignment,
            waiting_request=self.waiting_request_two,
        )

    def accept_url(self):
        return reverse(
            "dispatch-accept",
            kwargs={
                "pk": self.assignment.pk,
            },
        )

    def test_accept_moves_dispatch_directly_en_route(self):
        self.client.force_authenticate(
            user=self.driver
        )

        response = self.client.post(
            self.accept_url()
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.assignment.refresh_from_db()

        self.assertEqual(
            self.assignment.status,
            DispatchAssignment.Status.EN_ROUTE,
        )

    def test_accept_creates_trip_and_en_route_timestamp(self):
        self.client.force_authenticate(
            user=self.driver
        )

        response = self.client.post(
            self.accept_url()
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        trip = Trip.objects.get(
            dispatch=self.assignment
        )

        self.assertIsNotNone(
            trip.en_route_at
        )

    def test_accept_sets_responded_timestamp(self):
        self.client.force_authenticate(
            user=self.driver
        )

        response = self.client.post(
            self.accept_url()
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.assignment.refresh_from_db()

        self.assertIsNotNone(
            self.assignment.responded_at
        )

    def test_non_pending_dispatch_cannot_be_accepted(self):
        self.assignment.status = (
            DispatchAssignment.Status.EN_ROUTE
        )

        self.assignment.save(
            update_fields=["status"]
        )

        self.client.force_authenticate(
            user=self.driver
        )

        response = self.client.post(
            self.accept_url()
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_other_driver_cannot_accept_dispatch(self):
        self.client.force_authenticate(
            user=self.other_driver
        )

        response = self.client.post(
            self.accept_url()
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_accept_cancels_dispatch_when_all_passengers_cancelled(
        self
    ):
        now = timezone.now()

        WaitingRequest.objects.filter(
            id__in=[
                self.waiting_request_one.id,
                self.waiting_request_two.id,
            ]
        ).update(
            status=WaitingRequest.Status.CANCELLED,
            ended_at=now,
        )

        self.client.force_authenticate(
            user=self.driver
        )

        response = self.client.post(
            self.accept_url()
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_409_CONFLICT,
        )

        self.assignment.refresh_from_db()

        self.assertEqual(
            self.assignment.status,
            DispatchAssignment.Status.CANCELLED,
        )

        self.assertIsNotNone(
            self.assignment.responded_at
        )

        self.assertFalse(
            Trip.objects.filter(
                dispatch=self.assignment
            ).exists()
        )

        availability = (
            DriverAvailability.objects.get(
                driver=self.driver
            )
        )

        self.assertTrue(
            availability.is_available
        )

    def test_accept_succeeds_when_one_passenger_still_waiting(
        self
    ):
        self.waiting_request_one.status = (
            WaitingRequest.Status.CANCELLED
        )

        self.waiting_request_one.ended_at = (
            timezone.now()
        )

        self.waiting_request_one.save(
            update_fields=[
                "status",
                "ended_at",
            ]
        )

        self.client.force_authenticate(
            user=self.driver
        )

        response = self.client.post(
            self.accept_url()
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.assignment.refresh_from_db()

        self.assertEqual(
            self.assignment.status,
            DispatchAssignment.Status.EN_ROUTE,
        )

        self.assertTrue(
            Trip.objects.filter(
                dispatch=self.assignment
            ).exists()
        )
    def test_accept_notifies_waiting_passengers_and_dispatcher(
        self
    ):
        self.client.force_authenticate(
            user=self.driver
        )

        response = self.client.post(
            self.accept_url()
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        notifications = (
            Notification.objects
            .filter(
                notification_type=(
                    Notification.Type.DISPATCH_ACCEPTED
                ),
                dispatch=self.assignment,
            )
        )

        recipient_ids = set(
            notifications.values_list(
                "recipient_id",
                flat=True,
            )
        )

        self.assertEqual(
            recipient_ids,
            {
                self.passenger_one.id,
                self.passenger_two.id,
                self.dispatcher.id,
            },
        )

        self.assertEqual(
            notifications.count(),
            3,
        )



class BoardingTests(APITestCase):
    def setUp(self):
        self.dispatcher = User.objects.create_user(
            username="dispatcher_boarding",
            email="dispatcher_boarding@example.com",
            password="StrongPass123!",
            role="DISPATCHER",
        )

        self.driver = User.objects.create_user(
            username="driver_boarding",
            email="driver_boarding@example.com",
            password="StrongPass123!",
            role="DRIVER",
        )

        self.other_driver = User.objects.create_user(
            username="other_driver_boarding",
            email="other_driver_boarding@example.com",
            password="StrongPass123!",
            role="DRIVER",
        )

        self.route = Route.objects.create(
            name="Boarding Route",
            origin="Campus",
            destination="Town",
        )

        self.spot_one = WaitingSpot.objects.create(
            route=self.route,
            name="Main Gate",
            latitude="-23.884500",
            longitude="29.738200",
            geofence_radius_meters=100,
        )

        self.spot_two = WaitingSpot.objects.create(
            route=self.route,
            name="Library",
            latitude="-23.885000",
            longitude="29.739000",
            geofence_radius_meters=100,
        )

        self.assignment = (
            DispatchAssignment.objects.create(
                dispatcher=self.dispatcher,
                driver=self.driver,
                route=self.route,
                waiting_spot=None,
                passenger_count=10,
                status=(
                    DispatchAssignment.Status.EN_ROUTE
                ),
            )
        )

        self.trip = Trip.objects.create(
            dispatch=self.assignment,
            en_route_at=timezone.now(),
        )

        self.spot_one_request_a = (
            self.create_waiting_request(
                username="spot_one_a",
                spot=self.spot_one,
                party_size=3,
                code="A21",
            )
        )

        self.spot_one_request_b = (
            self.create_waiting_request(
                username="spot_one_b",
                spot=self.spot_one,
                party_size=2,
                code="B14",
            )
        )

        # Same code is allowed at another waiting spot.
        self.spot_two_request_a = (
            self.create_waiting_request(
                username="spot_two_a",
                spot=self.spot_two,
                party_size=4,
                code="A21",
            )
        )

        self.spot_two_request_b = (
            self.create_waiting_request(
                username="spot_two_b",
                spot=self.spot_two,
                party_size=1,
                code="C07",
            )
        )

    def create_waiting_request(
        self,
        username,
        spot,
        party_size,
        code,
    ):
        passenger = User.objects.create_user(
            username=username,
            email=f"{username}@example.com",
            password="StrongPass123!",
            role="PASSENGER",
        )

        waiting_request = (
            WaitingRequest.objects.create(
                passenger=passenger,
                waiting_spot=spot,
                party_size=party_size,
                boarding_pin=code,
                passenger_latitude=spot.latitude,
                passenger_longitude=spot.longitude,
                distance_from_spot_meters="0.00",
            )
        )

        DispatchRequest.objects.create(
            dispatch=self.assignment,
            waiting_request=waiting_request,
        )

        return waiting_request

    def boarding_url(self):
        return reverse(
            "dispatch-confirm-boarding",
            kwargs={
                "pk": self.assignment.pk,
            },
        )

    def board(self, spot, code):
        return self.client.post(
            self.boarding_url(),
            {
                "waiting_spot": spot.id,
                "boarding_pin": code,
            },
            format="json",
        )

    def test_correct_code_boards_exact_group(self):
        self.client.force_authenticate(
            user=self.driver
        )

        response = self.board(
            self.spot_one,
            "A21",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.spot_one_request_a.refresh_from_db()
        self.spot_one_request_b.refresh_from_db()

        self.assertEqual(
            self.spot_one_request_a.status,
            WaitingRequest.Status.BOARDED,
        )

        self.assertEqual(
            self.spot_one_request_b.status,
            WaitingRequest.Status.WAITING,
        )

        link = DispatchRequest.objects.get(
            dispatch=self.assignment,
            waiting_request=self.spot_one_request_a,
        )

        self.assertTrue(link.boarded)
        self.assertIsNotNone(link.boarded_at)

    def test_group_size_updates_boarded_passenger_count(self):
        self.client.force_authenticate(
            user=self.driver
        )

        response = self.board(
            self.spot_one,
            "A21",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.trip.refresh_from_db()

        # A21 represents a group of 3 people.
        self.assertEqual(
            self.trip.boarded_passenger_count,
            3,
        )

    def test_same_code_can_exist_at_different_spots(self):
        self.client.force_authenticate(
            user=self.driver
        )

        response = self.board(
            self.spot_two,
            "A21",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.spot_one_request_a.refresh_from_db()
        self.spot_two_request_a.refresh_from_db()

        # A21 at Main Gate was NOT boarded.
        self.assertEqual(
            self.spot_one_request_a.status,
            WaitingRequest.Status.WAITING,
        )

        # A21 at Library was boarded.
        self.assertEqual(
            self.spot_two_request_a.status,
            WaitingRequest.Status.BOARDED,
        )

        self.trip.refresh_from_db()

        # Library A21 represents 4 people.
        self.assertEqual(
            self.trip.boarded_passenger_count,
            4,
        )

    def test_incorrect_code_returns_clear_message(self):
        self.client.force_authenticate(
            user=self.driver
        )

        response = self.board(
            self.spot_one,
            "Z99",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

        self.assertEqual(
            response.data["boarding_pin"],
            (
                "Incorrect boarding code or this "
                "passenger is not assigned to your taxi."
            ),
        )

        self.trip.refresh_from_db()

        self.assertEqual(
            self.trip.boarded_passenger_count,
            0,
        )

    def test_code_belonging_to_another_taxi_is_rejected(self):
        other_assignment = (
            DispatchAssignment.objects.create(
                dispatcher=self.dispatcher,
                driver=self.other_driver,
                route=self.route,
                waiting_spot=None,
                passenger_count=2,
                status=(
                    DispatchAssignment.Status.EN_ROUTE
                ),
            )
        )

        Trip.objects.create(
            dispatch=other_assignment,
            en_route_at=timezone.now(),
        )

        passenger = User.objects.create_user(
            username="other_taxi_passenger",
            email="other_taxi_passenger@example.com",
            password="StrongPass123!",
            role="PASSENGER",
        )

        other_request = (
            WaitingRequest.objects.create(
                passenger=passenger,
                waiting_spot=self.spot_one,
                party_size=2,
                boarding_pin="D55",
                passenger_latitude=(
                    self.spot_one.latitude
                ),
                passenger_longitude=(
                    self.spot_one.longitude
                ),
                distance_from_spot_meters="0.00",
            )
        )

        DispatchRequest.objects.create(
            dispatch=other_assignment,
            waiting_request=other_request,
        )

        self.client.force_authenticate(
            user=self.driver
        )

        response = self.board(
            self.spot_one,
            "D55",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

        self.assertEqual(
            response.data["boarding_pin"],
            (
                "Incorrect boarding code or this "
                "passenger is not assigned to your taxi."
            ),
        )

        other_request.refresh_from_db()

        self.assertEqual(
            other_request.status,
            WaitingRequest.Status.WAITING,
        )

    def test_code_cannot_board_same_request_twice(self):
        self.client.force_authenticate(
            user=self.driver
        )

        first_response = self.board(
            self.spot_one,
            "A21",
        )

        second_response = self.board(
            self.spot_one,
            "A21",
        )

        self.assertEqual(
            first_response.status_code,
            status.HTTP_200_OK,
        )

        self.assertEqual(
            second_response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

        self.trip.refresh_from_db()

        # It must remain 3, not become 6.
        self.assertEqual(
            self.trip.boarded_passenger_count,
            3,
        )

    def test_same_dispatch_can_board_multiple_spots(self):
        self.client.force_authenticate(
            user=self.driver
        )

        first_response = self.board(
            self.spot_one,
            "A21",
        )

        second_response = self.board(
            self.spot_two,
            "C07",
        )

        self.assertEqual(
            first_response.status_code,
            status.HTTP_200_OK,
        )

        self.assertEqual(
            second_response.status_code,
            status.HTTP_200_OK,
        )

        self.trip.refresh_from_db()
        self.assignment.refresh_from_db()

        # Main Gate A21 = 3 people
        # Library C07 = 1 person
        self.assertEqual(
            self.trip.boarded_passenger_count,
            4,
        )

        self.assertEqual(
            self.assignment.status,
            DispatchAssignment.Status.EN_ROUTE,
        )

    def test_lowercase_code_is_accepted(self):
        self.client.force_authenticate(
            user=self.driver
        )

        response = self.board(
            self.spot_one,
            "a21",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.spot_one_request_a.refresh_from_db()

        self.assertEqual(
            self.spot_one_request_a.status,
            WaitingRequest.Status.BOARDED,
        )

    def test_boarding_requires_en_route_dispatch(self):
        self.assignment.status = (
            DispatchAssignment.Status.ACCEPTED
        )

        self.assignment.save(
            update_fields=["status"]
        )

        self.client.force_authenticate(
            user=self.driver
        )

        response = self.board(
            self.spot_one,
            "A21",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_other_driver_cannot_confirm_boarding(self):
        self.client.force_authenticate(
            user=self.other_driver
        )

        response = self.board(
            self.spot_one,
            "A21",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_pickup_spot_counts_people_not_requests(self):
        self.client.force_authenticate(
            user=self.driver
        )

        response = self.board(
            self.spot_one,
            "A21",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        spot_data = next(
            spot
            for spot in response.data["pickup_spots"]
            if spot["id"] == self.spot_one.id
        )

        # Main Gate has:
        # A21 = 3 people
        # B14 = 2 people
        self.assertEqual(
            spot_data["assigned_count"],
            5,
        )

        self.assertEqual(
            spot_data["boarded_count"],
            3,
        )

        self.assertEqual(
            spot_data["waiting_count"],
            2,
        )

class TripCompletionTests(APITestCase):
    def setUp(self):
        self.dispatcher = User.objects.create_user(
            username="dispatcher_complete",
            email="dispatcher_complete@example.com",
            password="StrongPass123!",
            role="DISPATCHER",
        )

        self.driver = User.objects.create_user(
            username="driver_complete",
            email="driver_complete@example.com",
            password="StrongPass123!",
            role="DRIVER",
        )

        self.other_driver = User.objects.create_user(
            username="other_driver_complete",
            email="other_driver_complete@example.com",
            password="StrongPass123!",
            role="DRIVER",
        )

        DriverAvailability.objects.create(
            driver=self.driver,
            is_available=False,
        )

        self.route = Route.objects.create(
            name="Completion Test Route",
            origin="Campus",
            destination="Town",
        )

        self.assignment = DispatchAssignment.objects.create(
            dispatcher=self.dispatcher,
            driver=self.driver,
            route=self.route,
            waiting_spot=None,
            passenger_count=2,
            status=DispatchAssignment.Status.EN_ROUTE,
        )

        self.trip = Trip.objects.create(
            dispatch=self.assignment,
            en_route_at=timezone.now(),
            boarded_passenger_count=1,
            boarding_confirmed_at=timezone.now(),
        )

    def complete_url(self):
        return reverse(
            "dispatch-complete",
            kwargs={"pk": self.assignment.pk},
        )

    def test_driver_can_complete_en_route_dispatch(self):
        self.client.force_authenticate(user=self.driver)

        response = self.client.post(
            self.complete_url()
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.assignment.refresh_from_db()

        self.assertEqual(
            self.assignment.status,
            DispatchAssignment.Status.COMPLETED,
        )

    def test_completion_sets_completed_timestamp(self):
        self.client.force_authenticate(user=self.driver)

        self.client.post(
            self.complete_url()
        )

        self.trip.refresh_from_db()

        self.assertIsNotNone(
            self.trip.completed_at
        )

    def test_completion_makes_driver_available(self):
        self.client.force_authenticate(user=self.driver)

        self.client.post(
            self.complete_url()
        )

        availability = DriverAvailability.objects.get(
            driver=self.driver
        )

        self.assertTrue(
            availability.is_available
        )

    def test_non_en_route_dispatch_cannot_be_completed(self):
        self.assignment.status = (
            DispatchAssignment.Status.ACCEPTED
        )

        self.assignment.save(
            update_fields=["status"]
        )

        self.client.force_authenticate(user=self.driver)

        response = self.client.post(
            self.complete_url()
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_other_driver_cannot_complete_dispatch(self):
        self.client.force_authenticate(
            user=self.other_driver
        )

        response = self.client.post(
            self.complete_url()
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND,
        )

class PassengerRequestRulesTests(APITestCase):
    def setUp(self):
        self.passenger = User.objects.create_user(
            username="pin_passenger",
            email="pin_passenger@example.com",
            password="StrongPass123!",
            role="PASSENGER",
        )

        self.route = Route.objects.create(
            name="PIN Test Route",
            origin="Campus",
            destination="Town",
        )

        self.spot = WaitingSpot.objects.create(
            route=self.route,
            name="PIN Test Spot",
            latitude="-23.884500",
            longitude="29.738200",
            geofence_radius_meters=100,
        )

        self.client.force_authenticate(
            user=self.passenger
        )

    def check_in(self, party_size=None):
        data = {
            "waiting_spot": self.spot.id,
            "latitude": "-23.884500",
            "longitude": "29.738200",
        }

        if party_size is not None:
            data["party_size"] = party_size

        return self.client.post(
            reverse("passenger-check-in"),
            data,
            format="json",
        )

    def test_default_party_size_is_one(self):
        response = self.check_in()

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )

        waiting_request = (
            WaitingRequest.objects.get(
                passenger=self.passenger
            )
        )

        self.assertEqual(
            waiting_request.party_size,
            1,
        )

    def test_passenger_can_request_for_group(self):
        response = self.check_in(
            party_size=6
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )

        waiting_request = (
            WaitingRequest.objects.get(
                passenger=self.passenger
            )
        )

        self.assertEqual(
            waiting_request.party_size,
            6,
        )

    def test_waiting_request_gets_two_digit_pin(self):
        response = self.check_in()

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )

        waiting_request = (
            WaitingRequest.objects.get(
                passenger=self.passenger
            )
        )

        self.assertIsNotNone(
            waiting_request.boarding_pin
        )

        self.assertEqual(
            len(waiting_request.boarding_pin),
            3,
        )

        self.assertTrue(
            waiting_request.boarding_pin[0].isalpha()
        )

        self.assertTrue(
            waiting_request.boarding_pin[0].isupper()
        )

        self.assertTrue(
            waiting_request.boarding_pin[1:].isdigit()
        )

        self.assertGreaterEqual(
            int(waiting_request.boarding_pin[1:]),
            1,
        )

        self.assertLessEqual(
            int(waiting_request.boarding_pin[1:]),
            99,
        )

    def test_api_returns_pin_and_party_size(self):
        response = self.check_in(
            party_size=4
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )

        self.assertEqual(
            response.data["party_size"],
            4,
        )

        self.assertIsNotNone(
            response.data["boarding_pin"]
        )

class PassengerDispatchVisibilityTests(APITestCase):
    def setUp(self):
        self.passenger = User.objects.create_user(
            username="visibility_passenger",
            email="visibility_passenger@example.com",
            password="StrongPass123!",
            role="PASSENGER",
        )

        self.dispatcher = User.objects.create_user(
            username="visibility_dispatcher",
            email="visibility_dispatcher@example.com",
            password="StrongPass123!",
            role="DISPATCHER",
        )

        self.driver = User.objects.create_user(
            username="visibility_driver",
            first_name="Thabo",
            last_name="Mokoena",
            email="visibility_driver@example.com",
            password="StrongPass123!",
            role="DRIVER",
            number_plate="ABC 123 L",
        )

        self.route = Route.objects.create(
            name="Visibility Route",
            origin="Campus",
            destination="Town",
        )

        self.spot = WaitingSpot.objects.create(
            route=self.route,
            name="Main Gate",
            latitude="-23.884500",
            longitude="29.738200",
            geofence_radius_meters=100,
        )

        self.waiting_request = (
            WaitingRequest.objects.create(
                passenger=self.passenger,
                waiting_spot=self.spot,
                party_size=4,
                boarding_pin="A21",
                passenger_latitude=self.spot.latitude,
                passenger_longitude=self.spot.longitude,
                distance_from_spot_meters="0.00",
            )
        )

        self.assignment = (
            DispatchAssignment.objects.create(
                dispatcher=self.dispatcher,
                driver=self.driver,
                route=self.route,
                waiting_spot=None,
                passenger_count=4,
                status=DispatchAssignment.Status.PENDING,
            )
        )

        DispatchRequest.objects.create(
            dispatch=self.assignment,
            waiting_request=self.waiting_request,
        )

        self.client.force_authenticate(
            user=self.passenger
        )

        self.url = (
            "/api/transport/"
            "waiting-requests/current/"
        )

    def test_pending_dispatch_hides_driver_details(self):
        response = self.client.get(
            self.url
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.assertTrue(
            response.data["active"]
        )

        self.assertEqual(
            response.data["dispatch"]["status"],
            DispatchAssignment.Status.PENDING,
        )

        self.assertEqual(
            response.data["dispatch"]["message"],
            (
                "Taxi assigned. Waiting for "
                "driver to accept."
            ),
        )

        self.assertIsNone(
            response.data["dispatch"]["driver"]
        )

    def test_accepted_dispatch_shows_driver_details(self):
        self.assignment.status = (
            DispatchAssignment.Status.ACCEPTED
        )

        self.assignment.save(
            update_fields=["status"]
        )

        response = self.client.get(
            self.url
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.assertEqual(
            response.data["dispatch"]["message"],
            "Your taxi is on the way.",
        )

        self.assertEqual(
            response.data["dispatch"]["driver"]["name"],
            "Thabo Mokoena",
        )

        self.assertEqual(
            response.data["dispatch"]["driver"][
                "number_plate"
            ],
            "ABC 123 L",
        )

    def test_en_route_dispatch_keeps_driver_details_visible(self):
        self.assignment.status = (
            DispatchAssignment.Status.EN_ROUTE
        )

        self.assignment.save(
            update_fields=["status"]
        )

        response = self.client.get(
            self.url
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.assertEqual(
            response.data["dispatch"]["status"],
            DispatchAssignment.Status.EN_ROUTE,
        )

        self.assertEqual(
            response.data["dispatch"]["driver"]["name"],
            "Thabo Mokoena",
        )

        self.assertEqual(
            response.data["dispatch"]["driver"][
                "number_plate"
            ],
            "ABC 123 L",
        )

    def test_passenger_sees_own_boarding_code_and_party_size(self):
        response = self.client.get(
            self.url
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.assertEqual(
            response.data["request"]["boarding_pin"],
            "A21",
        )

        self.assertEqual(
            response.data["request"]["party_size"],
            4,
        )

    def test_rejected_dispatch_no_longer_appears_as_assigned(self):
        self.assignment.status = (
            DispatchAssignment.Status.REJECTED
        )

        self.assignment.save(
            update_fields=["status"]
        )

        response = self.client.get(
            self.url
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.assertTrue(
            response.data["active"]
        )

        self.assertIsNone(
            response.data["dispatch"]
        )

        self.assertEqual(
            self.waiting_request.status,
            WaitingRequest.Status.WAITING,
        )

    def test_en_route_dispatch_returns_tracking_ids(
        self
    ):
        self.assignment.status = (
            DispatchAssignment.Status.EN_ROUTE
        )

        self.assignment.save(
            update_fields=[
                "status",
            ]
        )

        response = self.client.get(
            self.url
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.assertEqual(
            response.data["dispatch"]["id"],
            self.assignment.id,
        )

        self.assertEqual(
            response.data["dispatch"]["route_id"],
            self.route.id,
        )


class DispatcherCancellationTests(
    APITestCase
):
    def setUp(self):
        self.dispatcher = User.objects.create_user(
            username="cancel_dispatcher",
            email="cancel_dispatcher@example.com",
            password="StrongPass123!",
            role="DISPATCHER",
        )

        self.driver = User.objects.create_user(
            username="cancel_driver",
            email="cancel_driver@example.com",
            password="StrongPass123!",
            role="DRIVER",
        )

        self.passenger = User.objects.create_user(
            username="cancel_passenger",
            email="cancel_passenger@example.com",
            password="StrongPass123!",
            role="PASSENGER",
        )

        self.route = Route.objects.create(
            name="Cancellation Test Route",
            origin="Campus",
            destination="Town",
        )

        self.spot = WaitingSpot.objects.create(
            route=self.route,
            name="Cancellation Test Spot",
            latitude="-23.884500",
            longitude="29.738200",
            geofence_radius_meters=100,
        )

        self.availability = (
            DriverAvailability.objects.create(
                driver=self.driver,
                is_available=False,
            )
        )

        self.waiting_request = (
            WaitingRequest.objects.create(
                passenger=self.passenger,
                waiting_spot=self.spot,
                party_size=3,
                boarding_pin="A21",
                passenger_latitude=self.spot.latitude,
                passenger_longitude=self.spot.longitude,
                distance_from_spot_meters="0.00",
            )
        )

        self.assignment = (
            DispatchAssignment.objects.create(
                dispatcher=self.dispatcher,
                driver=self.driver,
                route=self.route,
                waiting_spot=None,
                passenger_count=3,
                status=(
                    DispatchAssignment.Status.PENDING
                ),
            )
        )

        self.dispatch_request = (
            DispatchRequest.objects.create(
                dispatch=self.assignment,
                waiting_request=self.waiting_request,
            )
        )

    def cancel_url(self):
        return reverse(
            "dispatch-cancel",
            kwargs={
                "pk": self.assignment.pk,
            },
        )

    def cancel_as_dispatcher(self):
        self.client.force_authenticate(
            user=self.dispatcher
        )

        return self.client.post(
            self.cancel_url()
        )

    def test_dispatcher_can_cancel_pending_dispatch(
        self
    ):
        response = (
            self.cancel_as_dispatcher()
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.assignment.refresh_from_db()

        self.assertEqual(
            self.assignment.status,
            DispatchAssignment.Status.CANCELLED,
        )

    def test_cancellation_makes_driver_available(
        self
    ):
        response = (
            self.cancel_as_dispatcher()
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.availability.refresh_from_db()

        self.assertTrue(
            self.availability.is_available
        )

    def test_cancellation_keeps_passenger_waiting(
        self
    ):
        response = (
            self.cancel_as_dispatcher()
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.waiting_request.refresh_from_db()

        self.assertEqual(
            self.waiting_request.status,
            WaitingRequest.Status.WAITING,
        )

        self.assertIsNone(
            self.waiting_request.ended_at
        )

    def test_cancelled_dispatch_disappears_from_passenger_assignment(
        self
    ):
        response = (
            self.cancel_as_dispatcher()
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.client.force_authenticate(
            user=self.passenger
        )

        passenger_response = self.client.get(
            reverse(
                "current-waiting-request"
            )
        )

        self.assertEqual(
            passenger_response.status_code,
            status.HTTP_200_OK,
        )

        self.assertTrue(
            passenger_response.data["active"]
        )

        self.assertIsNone(
            passenger_response.data[
                "dispatch"
            ]
        )

    def test_dispatcher_can_cancel_en_route_before_boarding(
        self
    ):
        self.assignment.status = (
            DispatchAssignment.Status.EN_ROUTE
        )

        self.assignment.save(
            update_fields=["status"]
        )

        Trip.objects.create(
            dispatch=self.assignment,
            en_route_at=timezone.now(),
            boarded_passenger_count=0,
        )

        response = (
            self.cancel_as_dispatcher()
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.assignment.refresh_from_db()
        self.availability.refresh_from_db()

        self.assertEqual(
            self.assignment.status,
            DispatchAssignment.Status.CANCELLED,
        )

        self.assertTrue(
            self.availability.is_available
        )

    def test_dispatch_cannot_be_cancelled_after_boarding_started(
        self
    ):
        self.assignment.status = (
            DispatchAssignment.Status.EN_ROUTE
        )

        self.assignment.save(
            update_fields=["status"]
        )

        Trip.objects.create(
            dispatch=self.assignment,
            en_route_at=timezone.now(),
            boarded_passenger_count=3,
            boarding_confirmed_at=timezone.now(),
        )

        self.dispatch_request.boarded = True
        self.dispatch_request.boarded_at = (
            timezone.now()
        )

        self.dispatch_request.save(
            update_fields=[
                "boarded",
                "boarded_at",
            ]
        )

        response = (
            self.cancel_as_dispatcher()
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

        self.assignment.refresh_from_db()
        self.availability.refresh_from_db()

        self.assertEqual(
            self.assignment.status,
            DispatchAssignment.Status.EN_ROUTE,
        )

        self.assertFalse(
            self.availability.is_available
        )

    def test_driver_cannot_cancel_dispatch(
        self
    ):
        self.client.force_authenticate(
            user=self.driver
        )

        response = self.client.post(
            self.cancel_url()
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

        self.assignment.refresh_from_db()

        self.assertEqual(
            self.assignment.status,
            DispatchAssignment.Status.PENDING,
        )

    def test_completed_dispatch_cannot_be_cancelled(
        self
    ):
        self.assignment.status = (
            DispatchAssignment.Status.COMPLETED
        )

        self.assignment.save(
            update_fields=["status"]
        )

        response = (
            self.cancel_as_dispatcher()
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

        self.assignment.refresh_from_db()

        self.assertEqual(
            self.assignment.status,
            DispatchAssignment.Status.COMPLETED,
        )

    def test_waiting_passenger_can_be_dispatched_again_after_cancellation(
        self
    ):
        response = (
            self.cancel_as_dispatcher()
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.client.force_authenticate(
            user=self.dispatcher
        )

        second_response = self.client.post(
            reverse("dispatch-list"),
            {
                "driver": self.driver.id,
                "route": self.route.id,
                "notes": (
                    "Replacement dispatch."
                ),
            },
            format="json",
        )

        self.assertEqual(
            second_response.status_code,
            status.HTTP_201_CREATED,
        )

        new_assignment = (
            DispatchAssignment.objects.get(
                pk=second_response.data["id"]
            )
        )

        self.assertTrue(
            DispatchRequest.objects.filter(
                dispatch=new_assignment,
                waiting_request=(
                    self.waiting_request
                ),
            ).exists()
        )

    def test_cancellation_notifies_affected_users_and_dispatcher(
        self
    ):
        response = self.cancel_as_dispatcher()

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        notifications = (
            Notification.objects
            .filter(
                dispatch=self.assignment,
                notification_type=(
                    Notification.Type.DISPATCH_CANCELLED
                ),
            )
        )

        recipient_ids = set(
            notifications.values_list(
                "recipient_id",
                flat=True,
            )
        )

        self.assertEqual(
            recipient_ids,
            {
                self.passenger.id,
                self.driver.id,
                self.dispatcher.id,
            },
        )

        self.assertEqual(
            notifications.count(),
            3,
        )


class TripCompletionIntegrityTests(APITestCase):
    def setUp(self):
        self.dispatcher = User.objects.create_user(
            username="integrity_dispatcher",
            email="integrity_dispatcher@example.com",
            password="StrongPass123!",
            role="DISPATCHER",
        )

        self.driver = User.objects.create_user(
            username="integrity_driver",
            email="integrity_driver@example.com",
            password="StrongPass123!",
            role="DRIVER",
        )

        self.passenger = User.objects.create_user(
            username="integrity_passenger",
            email="integrity_passenger@example.com",
            password="StrongPass123!",
            role="PASSENGER",
        )

        self.route = Route.objects.create(
            name="Completion Integrity Route",
            origin="Campus",
            destination="Town",
        )

        self.spot = WaitingSpot.objects.create(
            route=self.route,
            name="Integrity Waiting Spot",
            latitude="-23.884500",
            longitude="29.738200",
            geofence_radius_meters=100,
        )

        self.availability = (
            DriverAvailability.objects.create(
                driver=self.driver,
                is_available=False,
            )
        )

        self.waiting_request = (
            WaitingRequest.objects.create(
                passenger=self.passenger,
                waiting_spot=self.spot,
                party_size=3,
                boarding_pin="B21",
                passenger_latitude=self.spot.latitude,
                passenger_longitude=self.spot.longitude,
                distance_from_spot_meters="0.00",
            )
        )

        self.assignment = (
            DispatchAssignment.objects.create(
                dispatcher=self.dispatcher,
                driver=self.driver,
                route=self.route,
                passenger_count=3,
                status=(
                    DispatchAssignment.Status.EN_ROUTE
                ),
            )
        )

        self.dispatch_request = (
            DispatchRequest.objects.create(
                dispatch=self.assignment,
                waiting_request=self.waiting_request,
                boarded=False,
            )
        )

        self.trip = Trip.objects.create(
            dispatch=self.assignment,
            en_route_at=timezone.now(),
        )

    def complete_url(self):
        return reverse(
            "dispatch-complete",
            kwargs={
                "pk": self.assignment.pk,
            },
        )

    def complete_as_driver(self):
        self.client.force_authenticate(
            user=self.driver
        )

        return self.client.post(
            self.complete_url()
        )

    def test_waiting_passenger_blocks_trip_completion(
        self
    ):
        response = self.complete_as_driver()

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

        self.assertEqual(
            response.data["detail"],
            (
                "This trip cannot be completed while "
                "assigned passengers are still waiting."
            ),
        )

        self.assignment.refresh_from_db()
        self.trip.refresh_from_db()
        self.availability.refresh_from_db()

        self.assertEqual(
            self.assignment.status,
            DispatchAssignment.Status.EN_ROUTE,
        )

        self.assertIsNone(
            self.trip.completed_at
        )

        self.assertFalse(
            self.availability.is_available
        )

    def test_boarded_passenger_allows_trip_completion(
        self
    ):
        self.waiting_request.status = (
            WaitingRequest.Status.BOARDED
        )

        self.waiting_request.ended_at = (
            timezone.now()
        )

        self.waiting_request.save(
            update_fields=[
                "status",
                "ended_at",
            ]
        )

        self.dispatch_request.boarded = True
        self.dispatch_request.boarded_at = (
            timezone.now()
        )

        self.dispatch_request.save(
            update_fields=[
                "boarded",
                "boarded_at",
            ]
        )

        self.trip.boarded_passenger_count = 3

        self.trip.save(
            update_fields=[
                "boarded_passenger_count",
            ]
        )

        response = self.complete_as_driver()

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.assignment.refresh_from_db()
        self.trip.refresh_from_db()
        self.availability.refresh_from_db()

        self.assertEqual(
            self.assignment.status,
            DispatchAssignment.Status.COMPLETED,
        )

        self.assertIsNotNone(
            self.trip.completed_at
        )

        self.assertTrue(
            self.availability.is_available
        )

    def test_cancelled_passenger_does_not_block_completion(
        self
    ):
        self.waiting_request.status = (
            WaitingRequest.Status.CANCELLED
        )

        self.waiting_request.ended_at = (
            timezone.now()
        )

        self.waiting_request.save(
            update_fields=[
                "status",
                "ended_at",
            ]
        )

        response = self.complete_as_driver()

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.assignment.refresh_from_db()

        self.assertEqual(
            self.assignment.status,
            DispatchAssignment.Status.COMPLETED,
        )

    def test_one_remaining_waiting_group_blocks_completion(
        self
    ):
        passenger_two = User.objects.create_user(
            username="integrity_passenger_two",
            email="integrity_passenger_two@example.com",
            password="StrongPass123!",
            role="PASSENGER",
        )

        second_request = WaitingRequest.objects.create(
            passenger=passenger_two,
            waiting_spot=self.spot,
            party_size=2,
            boarding_pin="B22",
            passenger_latitude=self.spot.latitude,
            passenger_longitude=self.spot.longitude,
            distance_from_spot_meters="0.00",
        )

        DispatchRequest.objects.create(
            dispatch=self.assignment,
            waiting_request=second_request,
            boarded=False,
        )

        self.waiting_request.status = (
            WaitingRequest.Status.BOARDED
        )

        self.waiting_request.ended_at = (
            timezone.now()
        )

        self.waiting_request.save(
            update_fields=[
                "status",
                "ended_at",
            ]
        )

        self.dispatch_request.boarded = True

        self.dispatch_request.boarded_at = (
            timezone.now()
        )

        self.dispatch_request.save(
            update_fields=[
                "boarded",
                "boarded_at",
            ]
        )

        response = self.complete_as_driver()

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

        self.assignment.refresh_from_db()

        self.assertEqual(
            self.assignment.status,
            DispatchAssignment.Status.EN_ROUTE,
        )

class WaitingLocationRevalidationTests(
    APITestCase
):

    def test_countdown_decreases_and_resets_only_after_return(self):
        started_at = timezone.now()

        with patch(
            "transport.views.timezone.now",
            return_value=started_at,
        ):
            first_response = self.post_outside()

        self.assertEqual(
            first_response.status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(
            first_response.data["grace_seconds_remaining"],
            60,
        )

        later = started_at + timedelta(seconds=20)

        with patch(
            "transport.views.timezone.now",
            return_value=later,
        ):
            repeated_response = self.post_outside()
            inside_response = self.post_inside()

        self.assertEqual(
            repeated_response.status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(
            repeated_response.data["grace_seconds_remaining"],
            40,
        )
        self.assertEqual(
            inside_response.status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(
            inside_response.data["grace_seconds_remaining"],
            0,
        )
        self.assertFalse(
            inside_response.data["grace_period_active"]
        )

        self.waiting_request.refresh_from_db()
        self.assertIsNone(
            self.waiting_request.outside_geofence_since
        )

        restarted_at = started_at + timedelta(seconds=25)

        with patch(
            "transport.views.timezone.now",
            return_value=restarted_at,
        ):
            new_exit_response = self.post_outside()

        self.assertEqual(
            new_exit_response.status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(
            new_exit_response.data["grace_seconds_remaining"],
            60,
        )

        self.waiting_request.refresh_from_db()
        self.assertEqual(
            self.waiting_request.outside_geofence_since,
            restarted_at,
        )

    def setUp(self):
        self.passenger = (
            User.objects.create_user(
                username=(
                    "location_passenger"
                ),
                email=(
                    "location_passenger"
                    "@example.com"
                ),
                password=(
                    "StrongPass123!"
                ),
                role="PASSENGER",
            )
        )

        self.route = Route.objects.create(
            name="Location Test Route",
            origin="Campus",
            destination="Town",
        )

        self.spot = (
            WaitingSpot.objects.create(
                route=self.route,
                name="Location Test Spot",
                latitude="-23.884500",
                longitude="29.738200",
                geofence_radius_meters=100,
            )
        )

        self.waiting_request = (
            WaitingRequest.objects.create(
                passenger=self.passenger,
                waiting_spot=self.spot,
                passenger_latitude=(
                    self.spot.latitude
                ),
                passenger_longitude=(
                    self.spot.longitude
                ),
                distance_from_spot_meters=(
                    "0.00"
                ),
            )
        )

        self.client.force_authenticate(
            user=self.passenger
        )

        self.url = reverse(
            "revalidate-waiting-location"
        )


    def post_inside(self):
        return self.client.post(
            self.url,
            {
                "latitude": (
                    "-23.884500"
                ),
                "longitude": (
                    "29.738200"
                ),
            },
            format="json",
        )


    def post_outside(self):
        return self.client.post(
            self.url,
            {
                "latitude": (
                    "-23.900000"
                ),
                "longitude": (
                    "29.738200"
                ),
            },
            format="json",
        )


    def test_inside_geofence_keeps_request_waiting(
        self
    ):
        response = self.post_inside()

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.waiting_request\
            .refresh_from_db()

        self.assertEqual(
            self.waiting_request.status,
            WaitingRequest.Status.WAITING,
        )

        self.assertIsNone(
            self.waiting_request
            .outside_geofence_since
        )

        self.assertTrue(
            response.data[
                "inside_geofence"
            ]
        )

        self.assertFalse(
            response.data[
                "cancelled"
            ]
        )

    def test_each_exit_sends_one_warning_and_restarts_timer(self):
        started_at = timezone.now()
        restarted_at = started_at + timedelta(seconds=20)

        warnings = Notification.objects.filter(
            recipient=self.passenger,
            notification_type=Notification.Type.WAITING_SPOT_EXIT,
        )

        with patch(
            "transport.notification_service.send_push_notification"
        ) as push, self.captureOnCommitCallbacks(execute=True):
            with patch(
                "transport.views.timezone.now",
                return_value=started_at,
            ):
                first_response = self.post_outside()
                self.post_outside()

            self.assertEqual(
                first_response.status_code,
                status.HTTP_200_OK,
            )
            self.waiting_request.refresh_from_db()
            self.assertEqual(
                self.waiting_request.outside_geofence_since,
                started_at,
            )
            self.assertEqual(warnings.count(), 1)

            inside_response = self.post_inside()

            self.assertEqual(
                inside_response.status_code,
                status.HTTP_200_OK,
            )
            self.waiting_request.refresh_from_db()
            self.assertIsNone(
                self.waiting_request.outside_geofence_since
            )
            self.assertFalse(
                inside_response.data["grace_period_active"]
            )

            with patch(
                "transport.views.timezone.now",
                return_value=restarted_at,
            ):
                second_response = self.post_outside()
                self.post_outside()

            self.assertEqual(
                second_response.status_code,
                status.HTTP_200_OK,
            )
            self.waiting_request.refresh_from_db()
            self.assertEqual(
                self.waiting_request.outside_geofence_since,
                restarted_at,
            )
            self.assertTrue(
                second_response.data["grace_period_active"]
            )
            self.assertEqual(warnings.count(), 2)

        self.assertEqual(push.call_count, 2)

    def test_first_outside_reading_starts_grace_period(
        self
    ):
        response = self.post_outside()

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.waiting_request\
            .refresh_from_db()

        self.assertEqual(
            self.waiting_request.status,
            WaitingRequest.Status.WAITING,
        )

        self.assertIsNotNone(
            self.waiting_request
            .outside_geofence_since
        )

        self.assertTrue(
            response.data[
                "grace_period_active"
            ]
        )

        self.assertFalse(
            response.data[
                "cancelled"
            ]
        )


    def test_outside_during_grace_does_not_cancel(
        self
    ):
        self.waiting_request\
            .outside_geofence_since = (
                timezone.now()
                - timedelta(
                    seconds=59
                )
            )

        self.waiting_request.save(
            update_fields=[
                "outside_geofence_since",
            ]
        )

        response = self.post_outside()

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.waiting_request\
            .refresh_from_db()

        self.assertEqual(
            self.waiting_request.status,
            WaitingRequest.Status.WAITING,
        )

        self.assertTrue(
            response.data[
                "grace_period_active"
            ]
        )

        self.assertFalse(
            response.data[
                "cancelled"
            ]
        )


    def test_returning_inside_clears_grace_period(
        self
    ):
        self.waiting_request\
            .outside_geofence_since = (
                timezone.now()
                - timedelta(
                    seconds=15
                )
            )

        self.waiting_request.save(
            update_fields=[
                "outside_geofence_since",
            ]
        )

        response = self.post_inside()

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.waiting_request\
            .refresh_from_db()

        self.assertEqual(
            self.waiting_request.status,
            WaitingRequest.Status.WAITING,
        )

        self.assertIsNone(
            self.waiting_request
            .outside_geofence_since
        )

        self.assertFalse(
            response.data[
                "grace_period_active"
            ]
        )


    def test_outside_after_grace_cancels_request(
        self
    ):
        self.waiting_request\
            .outside_geofence_since = (
                timezone.now()
                - timedelta(
                    seconds=61
                )
            )

        self.waiting_request.save(
            update_fields=[
                "outside_geofence_since",
            ]
        )

        response = self.post_outside()

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.waiting_request\
            .refresh_from_db()

        self.assertEqual(
            self.waiting_request.status,
            WaitingRequest.Status.CANCELLED,
        )

        self.assertIsNotNone(
            self.waiting_request.ended_at
        )

        self.assertTrue(
            response.data[
                "cancelled"
            ]
        )

        self.assertFalse(
            response.data[
                "active"
            ]
        )


    def test_revalidation_does_not_replace_check_in_coordinates(
        self
    ):
        self.waiting_request.refresh_from_db()

        original_latitude = (
            self.waiting_request
            .passenger_latitude
        )

        original_longitude = (
            self.waiting_request
            .passenger_longitude
        )

        self.post_outside()

        self.waiting_request\
            .refresh_from_db()

        self.assertEqual(
            self.waiting_request
            .passenger_latitude,
            original_latitude,
        )

        self.assertEqual(
            self.waiting_request
            .passenger_longitude,
            original_longitude,
        )


    def test_no_active_request_stops_monitoring(
        self
    ):
        self.waiting_request.status = (
            WaitingRequest.Status.CANCELLED
        )

        self.waiting_request.ended_at = (
            timezone.now()
        )

        self.waiting_request.save(
            update_fields=[
                "status",
                "ended_at",
            ]
        )

        response = self.post_inside()

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.assertFalse(
            response.data["active"]
        )

        self.assertFalse(
            response.data["cancelled"]
        )

class WaitingDemandVisibilityTests(
    APITestCase
):
    def setUp(self):
        self.passenger = User.objects.create_user(
            username="demand_passenger",
            email="demand_passenger@example.com",
            password="StrongPass123!",
            role="PASSENGER",
        )

        self.driver = User.objects.create_user(
            username="demand_driver",
            email="demand_driver@example.com",
            password="StrongPass123!",
            role="DRIVER",
        )

        self.dispatcher = User.objects.create_user(
            username="demand_dispatcher",
            email="demand_dispatcher@example.com",
            password="StrongPass123!",
            role="DISPATCHER",
        )

        self.route = Route.objects.create(
            name="Demand Visibility Route",
            origin="Campus",
            destination="Town",
        )

        self.spot = WaitingSpot.objects.create(
            route=self.route,
            name="Demand Visibility Spot",
            latitude="-23.884500",
            longitude="29.738200",
            geofence_radius_meters=100,
        )

        WaitingRequest.objects.create(
            passenger=self.passenger,
            waiting_spot=self.spot,
            passenger_latitude="-23.884500",
            passenger_longitude="29.738200",
            distance_from_spot_meters="0.00",
            party_size=4,
        )

        self.url = "/api/transport/routes/"


    def get_first_spot(self, user):
        self.client.force_authenticate(
            user=user
        )

        response = self.client.get(
            self.url
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        return (
            response.data[0]
            ["waiting_spots"][0]
        )


    def test_dispatcher_can_see_waiting_count(
        self
    ):
        spot = self.get_first_spot(
            self.dispatcher
        )

        self.assertIn(
            "active_waiting_count",
            spot,
        )

        self.assertEqual(
            spot["active_waiting_count"],
            4,
        )


    def test_passenger_cannot_see_waiting_count(
        self
    ):
        spot = self.get_first_spot(
            self.passenger
        )

        self.assertNotIn(
            "active_waiting_count",
            spot,
        )


    def test_driver_cannot_see_waiting_count(
        self
    ):
        spot = self.get_first_spot(
            self.driver
        )

        self.assertNotIn(
            "active_waiting_count",
            spot,
        )

class AvailableDriverQueueTests(APITestCase):
    def setUp(self):
        self.dispatcher = User.objects.create_user(
            username="queue_dispatcher",
            email="queue_dispatcher@example.com",
            password="StrongPass123!",
            role="DISPATCHER",
        )

        self.driver_oldest = User.objects.create_user(
            username="charlie_driver",
            email="charlie_driver@example.com",
            password="StrongPass123!",
            role="DRIVER",
        )

        self.driver_middle = User.objects.create_user(
            username="bravo_driver",
            email="bravo_driver@example.com",
            password="StrongPass123!",
            role="DRIVER",
        )

        self.driver_newest = User.objects.create_user(
            username="alpha_driver",
            email="alpha_driver@example.com",
            password="StrongPass123!",
            role="DRIVER",
        )

        self.oldest_availability = (
            DriverAvailability.objects.create(
                driver=self.driver_oldest,
                is_available=True,
            )
        )

        self.middle_availability = (
            DriverAvailability.objects.create(
                driver=self.driver_middle,
                is_available=True,
            )
        )

        self.newest_availability = (
            DriverAvailability.objects.create(
                driver=self.driver_newest,
                is_available=True,
            )
        )

        now = timezone.now()

        DriverAvailability.objects.filter(
            pk=self.oldest_availability.pk
        ).update(
            updated_at=now - timedelta(minutes=30)
        )

        DriverAvailability.objects.filter(
            pk=self.middle_availability.pk
        ).update(
            updated_at=now - timedelta(minutes=20)
        )

        DriverAvailability.objects.filter(
            pk=self.newest_availability.pk
        ).update(
            updated_at=now - timedelta(minutes=10)
        )

        self.url = reverse(
            "available-drivers"
        )

    def test_available_drivers_are_ordered_oldest_first(
        self
    ):
        self.client.force_authenticate(
            user=self.dispatcher
        )

        response = self.client.get(
            self.url
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        usernames = [
            driver["username"]
            for driver in response.data
        ]

        self.assertEqual(
            usernames,
            [
                "charlie_driver",
                "bravo_driver",
                "alpha_driver",
            ],
        )

    def test_driver_with_active_dispatch_is_excluded(
        self
    ):
        route = Route.objects.create(
            name="Queue Test Route",
            origin="Campus",
            destination="Town",
        )

        DispatchAssignment.objects.create(
            dispatcher=self.dispatcher,
            driver=self.driver_oldest,
            route=route,
            passenger_count=1,
            status=(
                DispatchAssignment.Status.PENDING
            ),
        )

        self.client.force_authenticate(
            user=self.dispatcher
        )

        response = self.client.get(
            self.url
        )

        usernames = [
            driver["username"]
            for driver in response.data
        ]

        self.assertNotIn(
            "charlie_driver",
            usernames,
        )

    def test_unavailable_driver_is_excluded(
        self
    ):
        self.middle_availability\
            .is_available = False

        self.middle_availability.save(
            update_fields=[
                "is_available",
                "updated_at",
            ]
        )

        self.client.force_authenticate(
            user=self.dispatcher
        )

        response = self.client.get(
            self.url
        )

        usernames = [
            driver["username"]
            for driver in response.data
        ]

        self.assertNotIn(
            "bravo_driver",
            usernames,
        )

class DriverLocationTrackingTests(
    APITestCase
):
    def setUp(self):
        self.dispatcher = (
            User.objects.create_user(
                username=(
                    "tracking_dispatcher"
                ),
                email=(
                    "tracking_dispatcher"
                    "@example.com"
                ),
                password=(
                    "StrongPass123!"
                ),
                role="DISPATCHER",
            )
        )

        self.driver = (
            User.objects.create_user(
                username="tracking_driver",
                email=(
                    "tracking_driver"
                    "@example.com"
                ),
                password=(
                    "StrongPass123!"
                ),
                role="DRIVER",
            )
        )

        self.other_driver = (
            User.objects.create_user(
                username=(
                    "tracking_other_driver"
                ),
                email=(
                    "tracking_other_driver"
                    "@example.com"
                ),
                password=(
                    "StrongPass123!"
                ),
                role="DRIVER",
            )
        )

        self.passenger = (
            User.objects.create_user(
                username=(
                    "tracking_passenger"
                ),
                email=(
                    "tracking_passenger"
                    "@example.com"
                ),
                password=(
                    "StrongPass123!"
                ),
                role="PASSENGER",
            )
        )

        self.other_passenger = (
            User.objects.create_user(
                username=(
                    "tracking_other_passenger"
                ),
                email=(
                    "tracking_other_passenger"
                    "@example.com"
                ),
                password=(
                    "StrongPass123!"
                ),
                role="PASSENGER",
            )
        )

        self.route = (
            Route.objects.create(
                name=(
                    "Tracking Test Route"
                ),
                origin="Campus",
                destination="Town",
            )
        )

        self.spot = (
            WaitingSpot.objects.create(
                route=self.route,
                name=(
                    "Tracking Test Spot"
                ),
                latitude="-23.884500",
                longitude="29.738200",
                geofence_radius_meters=100,
            )
        )

        self.waiting_request = (
            WaitingRequest.objects.create(
                passenger=self.passenger,
                waiting_spot=self.spot,
                party_size=2,
                boarding_pin="T21",
                passenger_latitude=(
                    self.spot.latitude
                ),
                passenger_longitude=(
                    self.spot.longitude
                ),
                distance_from_spot_meters=(
                    "0.00"
                ),
            )
        )

        self.assignment = (
            DispatchAssignment.objects.create(
                dispatcher=self.dispatcher,
                driver=self.driver,
                route=self.route,
                passenger_count=2,
                status=(
                    DispatchAssignment
                    .Status
                    .EN_ROUTE
                ),
            )
        )

        DispatchRequest.objects.create(
            dispatch=self.assignment,
            waiting_request=(
                self.waiting_request
            ),
        )

    def location_url(self):
        return reverse(
            "dispatch-location",
            kwargs={
                "pk": self.assignment.pk,
            },
        )

    def post_location(
        self,
        user=None,
        latitude="-23.885000",
        longitude="29.739000",
        accuracy="8.50",
    ):
        self.client.force_authenticate(
            user=(
                user
                or self.driver
            )
        )

        return self.client.post(
            self.location_url(),
            {
                "latitude": latitude,
                "longitude": longitude,
                "accuracy_meters": accuracy,
            },
            format="json",
        )

    def create_location(self):
        return (
            DriverLocation.objects.create(
                dispatch=self.assignment,
                latitude="-23.885000",
                longitude="29.739000",
                accuracy_meters="8.50",
            )
        )

    def test_assigned_driver_can_update_location(
        self
    ):
        response = self.post_location()

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )

        location = (
            DriverLocation.objects.get(
                dispatch=self.assignment
            )
        )

        self.assertEqual(
            float(location.latitude),
            -23.885,
        )

        self.assertEqual(
            float(location.longitude),
            29.739,
        )

    def test_location_update_overwrites_existing_row(
        self
    ):
        first_response = (
            self.post_location()
        )

        second_response = (
            self.post_location(
                latitude="-23.886000",
                longitude="29.740000",
                accuracy="5.00",
            )
        )

        self.assertEqual(
            first_response.status_code,
            status.HTTP_201_CREATED,
        )

        self.assertEqual(
            second_response.status_code,
            status.HTTP_200_OK,
        )

        self.assertEqual(
            DriverLocation.objects.filter(
                dispatch=self.assignment
            ).count(),
            1,
        )

        location = (
            DriverLocation.objects.get(
                dispatch=self.assignment
            )
        )

        self.assertEqual(
            float(location.latitude),
            -23.886,
        )

        self.assertEqual(
            float(location.longitude),
            29.74,
        )

    def test_other_driver_cannot_update_location(
        self
    ):
        response = self.post_location(
            user=self.other_driver
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

        self.assertFalse(
            DriverLocation.objects.filter(
                dispatch=self.assignment
            ).exists()
        )

    def test_driver_cannot_update_non_en_route_dispatch(
        self
    ):
        self.assignment.status = (
            DispatchAssignment
            .Status
            .COMPLETED
        )

        self.assignment.save(
            update_fields=[
                "status",
            ]
        )

        response = self.post_location()

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

        self.assertFalse(
            DriverLocation.objects.filter(
                dispatch=self.assignment
            ).exists()
        )

    def test_invalid_coordinates_are_rejected(
        self
    ):
        response = self.post_location(
            latitude="100",
            longitude="29.739000",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

        self.assertFalse(
            DriverLocation.objects.filter(
                dispatch=self.assignment
            ).exists()
        )

    def test_linked_waiting_passenger_can_get_location(
        self
    ):
        self.create_location()

        self.client.force_authenticate(
            user=self.passenger
        )

        response = self.client.get(
            self.location_url()
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.assertTrue(
            response.data["available"]
        )

        self.assertEqual(
            response.data["dispatch"],
            self.assignment.id,
        )

        self.assertEqual(
            response.data["latitude"],
            -23.885,
        )

        self.assertEqual(
            response.data["longitude"],
            29.739,
        )

    def test_unrelated_passenger_cannot_get_location(
        self
    ):
        self.create_location()

        self.client.force_authenticate(
            user=self.other_passenger
        )

        response = self.client.get(
            self.location_url()
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_dispatcher_can_get_location(
        self
    ):
        self.create_location()

        self.client.force_authenticate(
            user=self.dispatcher
        )

        response = self.client.get(
            self.location_url()
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.assertTrue(
            response.data["available"]
        )

    def test_no_location_returns_available_false(
        self
    ):
        self.client.force_authenticate(
            user=self.passenger
        )

        response = self.client.get(
            self.location_url()
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.assertFalse(
            response.data["available"]
        )

        self.assertIsNone(
            response.data["location"]
        )

    def test_location_not_exposed_after_dispatch_ends(
        self
    ):
        self.create_location()

        self.assignment.status = (
            DispatchAssignment
            .Status
            .COMPLETED
        )

        self.assignment.save(
            update_fields=[
                "status",
            ]
        )

        self.client.force_authenticate(
            user=self.dispatcher
        )

        response = self.client.get(
            self.location_url()
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

class PassengerPickupRouteTests(
    APITestCase
):
    def setUp(self):
        self.dispatcher = (
            User.objects.create_user(
                username="pickup_dispatcher",
                email="pickup_dispatcher@example.com",
                password="StrongPass123!",
                role="DISPATCHER",
            )
        )

        self.driver = (
            User.objects.create_user(
                username="pickup_driver",
                email="pickup_driver@example.com",
                password="StrongPass123!",
                role="DRIVER",
            )
        )

        self.passenger = (
            User.objects.create_user(
                username="pickup_passenger",
                email="pickup_passenger@example.com",
                password="StrongPass123!",
                role="PASSENGER",
            )
        )

        self.early_passenger_one = (
            User.objects.create_user(
                username="pickup_early_one",
                email="pickup_early_one@example.com",
                password="StrongPass123!",
                role="PASSENGER",
            )
        )

        self.early_passenger_two = (
            User.objects.create_user(
                username="pickup_early_two",
                email="pickup_early_two@example.com",
                password="StrongPass123!",
                role="PASSENGER",
            )
        )

        self.later_passenger = (
            User.objects.create_user(
                username="pickup_later",
                email="pickup_later@example.com",
                password="StrongPass123!",
                role="PASSENGER",
            )
        )

        self.other_passenger = (
            User.objects.create_user(
                username="pickup_other",
                email="pickup_other@example.com",
                password="StrongPass123!",
                role="PASSENGER",
            )
        )

        self.route = Route.objects.create(
            name="Passenger Pickup Route",
            origin="Start",
            destination="End",
        )

        self.spot_one = (
            WaitingSpot.objects.create(
                route=self.route,
                name="Spot 1",
                latitude="-23.880000",
                longitude="29.730000",
                geofence_radius_meters=100,
                stop_order=1,
            )
        )

        self.spot_two = (
            WaitingSpot.objects.create(
                route=self.route,
                name="Spot 2",
                latitude="-23.881000",
                longitude="29.731000",
                geofence_radius_meters=100,
                stop_order=2,
            )
        )

        self.spot_three = (
            WaitingSpot.objects.create(
                route=self.route,
                name="Spot 3",
                latitude="-23.882000",
                longitude="29.732000",
                geofence_radius_meters=100,
                stop_order=3,
            )
        )

        self.spot_four = (
            WaitingSpot.objects.create(
                route=self.route,
                name="Spot 4",
                latitude="-23.883000",
                longitude="29.733000",
                geofence_radius_meters=100,
                stop_order=4,
            )
        )

        self.assignment = (
            DispatchAssignment.objects.create(
                dispatcher=self.dispatcher,
                driver=self.driver,
                route=self.route,
                passenger_count=4,
                status=(
                    DispatchAssignment
                    .Status
                    .EN_ROUTE
                ),
            )
        )

        self.request_one = (
            self.create_request(
                user=self.early_passenger_one,
                spot=self.spot_one,
                code="P11",
            )
        )

        self.request_two = (
            self.create_request(
                user=self.early_passenger_two,
                spot=self.spot_two,
                code="P22",
            )
        )

        self.passenger_request = (
            self.create_request(
                user=self.passenger,
                spot=self.spot_three,
                code="P33",
            )
        )

        self.request_four = (
            self.create_request(
                user=self.later_passenger,
                spot=self.spot_four,
                code="P44",
            )
        )

        self.driver_location = (
            DriverLocation.objects.create(
                dispatch=self.assignment,
                latitude="-23.879000",
                longitude="29.729000",
                accuracy_meters="5.00",
            )
        )

        self.url = (
            f"/api/transport/dispatches/"
            f"{self.assignment.id}/"
            f"passenger-route/"
        )

        self.client.force_authenticate(
            user=self.passenger
        )

    def _tracking_urls(self):
        return (
            f"/api/transport/dispatches/{self.assignment.pk}/location/",
            self.url,
        )

    @staticmethod
    def _tracking_geojson(coordinates):
        return {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "LineString",
                        "coordinates": coordinates,
                    },
                    "properties": {},
                }
            ],
        }

    def _assert_tracking_access(self, expected_status):
        before = self._routing_state()

        with patch(
            "transport.views.get_coordinates_geojson",
            side_effect=self._tracking_geojson,
        ) as routing:
            for url in self._tracking_urls():
                with self.subTest(url=url, expected=expected_status):
                    response = self.client.get(url)

                    self.assertEqual(self._routing_state(), before)
                    self.assertEqual(
                        response.status_code,
                        expected_status,
                    )

                    if expected_status == status.HTTP_200_OK:
                        self.assertTrue(response.data["available"])
                    else:
                        self.assertEqual(
                            set(response.data),
                            {"detail"},
                        )

            if expected_status == status.HTTP_200_OK:
                routing.assert_called_once()
            else:
                routing.assert_not_called()

    def _board_for_tracking(self, waiting_request):
        Trip.objects.get_or_create(
            dispatch=self.assignment,
            defaults={"en_route_at": timezone.now()},
        )
        self.client.force_authenticate(user=self.driver)

        response = self.client.post(
            reverse(
                "dispatch-confirm-boarding",
                kwargs={"pk": self.assignment.pk},
            ),
            {
                "waiting_spot": waiting_request.waiting_spot_id,
                "boarding_pin": waiting_request.boarding_pin,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        waiting_request.refresh_from_db()
        self.assertEqual(
            waiting_request.status,
            WaitingRequest.Status.BOARDED,
        )
        self.client.force_authenticate(user=self.passenger)

    def test_cancellation_revokes_both_tracking_endpoints(self):
        self._assert_tracking_access(status.HTTP_200_OK)

        response = self.client.post(reverse("cancel-waiting-request"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.passenger_request.refresh_from_db()
        self.assignment.refresh_from_db()

        self.assertEqual(
            self.passenger_request.status,
            WaitingRequest.Status.CANCELLED,
        )
        self.assertEqual(
            self.assignment.status,
            DispatchAssignment.Status.EN_ROUTE,
        )

        self._assert_tracking_access(status.HTTP_403_FORBIDDEN)

    def test_boarding_revokes_both_tracking_endpoints(self):
        self._assert_tracking_access(status.HTTP_200_OK)
        self._board_for_tracking(self.passenger_request)

        self.assignment.refresh_from_db()
        self.assertEqual(
            self.assignment.status,
            DispatchAssignment.Status.EN_ROUTE,
        )

        self._assert_tracking_access(status.HTTP_403_FORBIDDEN)

    def test_other_driver_cannot_read_tracking_endpoints(self):
        other_driver = User.objects.create_user(
            username="tracking_other_driver",
            email="tracking_other_driver@example.com",
            password="StrongPass123!",
            role="DRIVER",
        )

        self.client.force_authenticate(user=other_driver)
        self._assert_tracking_access(status.HTTP_403_FORBIDDEN)

    def test_anonymous_user_cannot_read_tracking_endpoints(self):
        self.client.force_authenticate(user=None)
        self._assert_tracking_access(status.HTTP_401_UNAUTHORIZED)

    def test_boarded_earlier_stop_is_removed_from_pickup_route(self):
        self._board_for_tracking(self.request_one)
        before = self._routing_state()

        coordinates = [
            [29.729, -23.879],
            [29.731, -23.881],
            [29.732, -23.882],
        ]

        with patch(
            "transport.views.get_coordinates_geojson",
            side_effect=self._tracking_geojson,
        ) as routing:
            response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            [spot["id"] for spot in response.data["pickup_spots"]],
            [self.spot_two.pk, self.spot_three.pk],
        )

        routing.assert_called_once_with(coordinates)

        self.assertEqual(
            response.data["route"]["features"][0]["geometry"]["coordinates"],
            coordinates,
        )
        self.assertEqual(self._routing_state(), before)

    def test_driver_gps_update_changes_pickup_route_start(self):
        with patch(
            "transport.views.get_coordinates_geojson",
            side_effect=self._tracking_geojson,
        ) as routing:
            first_response = self.client.get(self.url)
            self.assertEqual(
                first_response.status_code,
                status.HTTP_200_OK,
            )

            original_coordinates = routing.call_args.args[0]
            self.assertEqual(
                original_coordinates[0],
                [29.729, -23.879],
            )

            self.client.force_authenticate(user=self.driver)
            update_response = self.client.post(
                self._tracking_urls()[0],
                {
                    "latitude": "-23.878500",
                    "longitude": "29.728500",
                    "accuracy_meters": "4.00",
                },
                format="json",
            )
            self.assertEqual(
                update_response.status_code,
                status.HTTP_200_OK,
            )

            self.client.force_authenticate(user=self.passenger)
            before = self._routing_state()
            second_response = self.client.get(self.url)

        self.assertEqual(second_response.status_code, status.HTTP_200_OK)

        expected_coordinates = [
            [29.7285, -23.8785],
            *original_coordinates[1:],
        ]

        self.assertEqual(routing.call_count, 2)
        routing.assert_called_with(expected_coordinates)

        self.assertEqual(
            second_response.data["route"]["features"][0]["geometry"]["coordinates"],
            expected_coordinates,
        )
        self.assertEqual(
            second_response.data["driver_location"]["latitude"],
            -23.8785,
        )
        self.assertEqual(
            second_response.data["driver_location"]["longitude"],
            29.7285,
        )
        self.assertEqual(
            DriverLocation.objects.filter(dispatch=self.assignment).count(),
            1,
        )

        self.assignment.refresh_from_db()
        self.assertEqual(
            self.assignment.status,
            DispatchAssignment.Status.EN_ROUTE,
        )
        self.assertEqual(self._routing_state(), before)

    def create_request(
        self,
        user,
        spot,
        code,
    ):
        waiting_request = (
            WaitingRequest.objects.create(
                passenger=user,
                waiting_spot=spot,
                party_size=1,
                boarding_pin=code,
                passenger_latitude=(
                    spot.latitude
                ),
                passenger_longitude=(
                    spot.longitude
                ),
                distance_from_spot_meters="0.00",
            )
        )

        DispatchRequest.objects.create(
            dispatch=self.assignment,
            waiting_request=waiting_request,
        )

        return waiting_request

    @patch(
        "transport.views."
        "get_coordinates_geojson"
    )
    def test_route_goes_through_waiting_spots_before_passenger(
        self,
        mock_route,
    ):
        mock_route.return_value = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [],
                    },
                    "properties": {},
                }
            ],
        }

        response = self.client.get(
            self.url
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        pickup_ids = [
            spot["id"]
            for spot
            in response.data[
                "pickup_spots"
            ]
        ]

        self.assertEqual(
            pickup_ids,
            [
                self.spot_one.id,
                self.spot_two.id,
                self.spot_three.id,
            ],
        )

        self.assertNotIn(
            self.spot_four.id,
            pickup_ids,
        )

        mock_route.assert_called_once_with(
            [
                [
                    29.729,
                    -23.879,
                ],
                [
                    29.73,
                    -23.88,
                ],
                [
                    29.731,
                    -23.881,
                ],
                [
                    29.732,
                    -23.882,
                ],
            ]
        )

    @patch(
        "transport.views."
        "get_coordinates_geojson"
    )
    def test_empty_earlier_spots_are_skipped(
        self,
        mock_route,
    ):
        self.request_one.status = (
            WaitingRequest.Status.CANCELLED
        )

        self.request_one.ended_at = (
            timezone.now()
        )

        self.request_one.save(
            update_fields=[
                "status",
                "ended_at",
            ]
        )

        self.request_two.status = (
            WaitingRequest.Status.CANCELLED
        )

        self.request_two.ended_at = (
            timezone.now()
        )

        self.request_two.save(
            update_fields=[
                "status",
                "ended_at",
            ]
        )

        mock_route.return_value = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [],
                    },
                    "properties": {},
                }
            ],
        }

        response = self.client.get(
            self.url
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        pickup_ids = [
            spot["id"]
            for spot
            in response.data[
                "pickup_spots"
            ]
        ]

        self.assertEqual(
            pickup_ids,
            [
                self.spot_three.id,
            ],
        )

        mock_route.assert_called_once_with(
            [
                [
                    29.729,
                    -23.879,
                ],
                [
                    29.732,
                    -23.882,
                ],
            ]
        )

    @patch(
        "transport.views."
        "get_coordinates_geojson"
    )
    def test_no_driver_location_returns_unavailable(
        self,
        mock_route,
    ):
        self.driver_location.delete()

        response = self.client.get(
            self.url
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.assertFalse(
            response.data["available"]
        )

        self.assertIsNone(
            response.data[
                "driver_location"
            ]
        )

        self.assertIsNone(
            response.data["route"]
        )

        mock_route.assert_not_called()

    @patch(
        "transport.views."
        "get_coordinates_geojson"
    )
    def test_boarded_passenger_can_no_longer_track(
        self,
        mock_route,
    ):
        self.passenger_request.status = (
            WaitingRequest.Status.BOARDED
        )

        self.passenger_request.ended_at = (
            timezone.now()
        )

        self.passenger_request.save(
            update_fields=[
                "status",
                "ended_at",
            ]
        )

        link = (
            DispatchRequest.objects.get(
                dispatch=self.assignment,
                waiting_request=(
                    self.passenger_request
                ),
            )
        )

        link.boarded = True
        link.boarded_at = timezone.now()

        link.save(
            update_fields=[
                "boarded",
                "boarded_at",
            ]
        )

        response = self.client.get(
            self.url
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

        mock_route.assert_not_called()

    @patch(
        "transport.views."
        "get_coordinates_geojson"
    )
    def test_unrelated_passenger_cannot_track(
        self,
        mock_route,
    ):
        self.client.force_authenticate(
            user=self.other_passenger
        )

        response = self.client.get(
            self.url
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

        mock_route.assert_not_called()

    @patch(
        "transport.views."
        "get_coordinates_geojson"
    )
    def test_tracking_requires_en_route_dispatch(
        self,
        mock_route,
    ):
        self.assignment.status = (
            DispatchAssignment
            .Status
            .COMPLETED
        )

        self.assignment.save(
            update_fields=[
                "status",
            ]
        )

        response = self.client.get(
            self.url
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

        mock_route.assert_not_called()

    def _routing_state(self):
            return {
                model.__name__: list(
                    model.objects.order_by("pk").values()
                )
                for model in (
                    DispatchAssignment,
                    DispatchRequest,
                    WaitingRequest,
                    Trip,
                    DriverAvailability,
                    DriverLocation,
                    Notification,
                )
            }

    def _prepare_routing_failure_checks(self):
            # Return HTTP 500 responses so assertions expose unhandled errors.
            self.client.raise_request_exception = False

            Trip.objects.get_or_create(
                dispatch=self.assignment,
                defaults={"en_route_at": timezone.now()},
            )

            DriverAvailability.objects.update_or_create(
                driver=self.driver,
                defaults={"is_available": False},
            )

            return self._routing_state()

    def _routing_urls(self):
            return (
                f"/api/transport/routes/{self.route.pk}/road-route/",
                self.url,
            )

    def _assert_routing_error_preserves_state(
            self,
            response,
            before,
        ):
            self.assertEqual(
                self._routing_state(),
                before,
            )

            self.assertEqual(
                response.status_code,
                status.HTTP_400_BAD_REQUEST,
                msg=(
                    "Expected a handled routing error; "
                    f"received {response.status_code}."
                ),
            )

            self.assertIn("detail", response.data)
            self.assertTrue(response.data["detail"])

    def test_routing_timeouts_preserve_trip_state(self):
            before = self._prepare_routing_failure_checks()

            with self.settings(
                OPENROUTESERVICE_API_KEY="routing-test-key"
            ):
                for url in self._routing_urls():
                    for phase in ("connect", "read"):
                        with self.subTest(url=url, phase=phase):
                            with patch(
                                "transport.routing_service.urlopen"
                            ) as provider:
                                error = TimeoutError(
                                    "Simulated routing timeout"
                                )

                                if phase == "connect":
                                    provider.side_effect = error
                                else:
                                    provider_response = (
                                        provider.return_value
                                        .__enter__.return_value
                                    )
                                    provider_response.read.side_effect = (
                                        error
                                    )

                                response = self.client.get(url)

                            provider.assert_called_once()

                            self._assert_routing_error_preserves_state(
                                response,
                                before,
                            )

    def test_routing_non_object_json_preserves_trip_state(self):
            before = self._prepare_routing_failure_checks()

            with self.settings(
                OPENROUTESERVICE_API_KEY="routing-test-key"
            ):
                for url in self._routing_urls():
                    for payload in (b"[]", b"null"):
                        with self.subTest(url=url, payload=payload):
                            with patch(
                                "transport.routing_service.urlopen"
                            ) as provider:
                                provider_response = (
                                    provider.return_value
                                    .__enter__.return_value
                                )
                                provider_response.read.return_value = (
                                    payload
                                )

                                response = self.client.get(url)

                            provider.assert_called_once()

                            self._assert_routing_error_preserves_state(
                                response,
                                before,
                            )
    def test_routing_invalid_json_preserves_trip_state(self):
            before = self._prepare_routing_failure_checks()

            with self.settings(
                OPENROUTESERVICE_API_KEY="routing-test-key"
            ):
                for url in self._routing_urls():
                    with self.subTest(url=url):
                        with patch(
                            "transport.routing_service.urlopen"
                        ) as provider:
                            provider_response = (
                                provider.return_value
                                .__enter__.return_value
                            )
                            provider_response.read.return_value = (
                                b"not JSON"
                            )

                            response = self.client.get(url)

                        provider.assert_called_once()

                        self._assert_routing_error_preserves_state(
                            response,
                            before,
                        )

    def test_routing_connection_failure_preserves_trip_state(self):
            before = self._prepare_routing_failure_checks()

            with self.settings(
                OPENROUTESERVICE_API_KEY="routing-test-key"
            ):
                for url in self._routing_urls():
                    with self.subTest(url=url):
                        with patch(
                            "transport.routing_service.urlopen",
                            side_effect=URLError(
                                "Simulated provider outage"
                            ),
                        ) as provider:
                            response = self.client.get(url)

                        provider.assert_called_once()

                        self._assert_routing_error_preserves_state(
                            response,
                            before,
                        )

    def test_routing_recovers_after_provider_outage(self):
            before = self._prepare_routing_failure_checks()

            with self.settings(
                OPENROUTESERVICE_API_KEY="routing-test-key"
            ):
                for url in self._routing_urls():
                    with self.subTest(url=url):
                        with patch(
                            "transport.routing_service.urlopen"
                        ) as provider:
                            successful_response = provider.return_value

                            provider.side_effect = [
                                URLError("Simulated provider outage"),
                                successful_response,
                            ]

                            failed_response = self.client.get(url)

                            self._assert_routing_error_preserves_state(
                                failed_response,
                                before,
                            )

                            # Return a valid route using the coordinates
                            # actually submitted to the provider.
                            coordinates = json.loads(
                                provider.call_args.args[0].data
                            )["coordinates"]

                            route_data = {
                                "type": "FeatureCollection",
                                "features": [
                                    {
                                        "type": "Feature",
                                        "geometry": {
                                            "type": "LineString",
                                            "coordinates": coordinates,
                                        },
                                        "properties": {},
                                    }
                                ],
                            }

                            provider_response = (
                                successful_response
                                .__enter__.return_value
                            )
                            provider_response.read.return_value = (
                                json.dumps(route_data).encode("utf-8")
                            )

                            recovered_response = self.client.get(url)

                        self.assertEqual(provider.call_count, 2)

                        self.assertEqual(
                            recovered_response.status_code,
                            status.HTTP_200_OK,
                        )

                        returned_route = (
                            recovered_response.data["route"]
                            if url == self.url
                            else recovered_response.data
                        )

                        self.assertEqual(
                            returned_route,
                            route_data,
                        )

                        self.assertEqual(
                            self._routing_state(),
                            before,
                        )