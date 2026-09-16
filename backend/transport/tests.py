from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from django.utils import timezone
from datetime import timedelta

from .models import (
    DispatchAssignment,
    DriverAvailability,
    Route,
    Trip,
    WaitingSpot,
    DispatchRequest,
    WaitingRequest,
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

        self.client.post(
            self.accept_url()
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
                    seconds=15
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
                    seconds=31
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