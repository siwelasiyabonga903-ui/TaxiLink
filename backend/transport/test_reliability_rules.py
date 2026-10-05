from django.contrib.auth import get_user_model
from django.urls import reverse
from datetime import timedelta
from unittest.mock import patch

from django.utils import timezone

from rest_framework import status
from rest_framework.test import APITestCase

from .models import (
    DispatchAssignment,
    DispatchRequest,
    DriverAvailability,
    Route,
    Trip,
    WaitingRequest,
    WaitingSpot,
    Notification,
)


User = get_user_model()


class DispatchReliabilityRulesTests(
    APITestCase
):
    def setUp(self):
        self.dispatcher = (
            User.objects.create_user(
                username="reliability_dispatcher",
                email=(
                    "reliability_dispatcher"
                    "@example.com"
                ),
                password="StrongPass123!",
                role="DISPATCHER",
            )
        )

        self.driver_one = (
            User.objects.create_user(
                username="reliability_driver_one",
                email=(
                    "reliability_driver_one"
                    "@example.com"
                ),
                password="StrongPass123!",
                role="DRIVER",
            )
        )

        self.driver_two = (
            User.objects.create_user(
                username="reliability_driver_two",
                email=(
                    "reliability_driver_two"
                    "@example.com"
                ),
                password="StrongPass123!",
                role="DRIVER",
            )
        )

        DriverAvailability.objects.create(
            driver=self.driver_one,
            is_available=True,
        )

        DriverAvailability.objects.create(
            driver=self.driver_two,
            is_available=True,
        )

        self.route = Route.objects.create(
            name="Reliability Route",
            origin="Campus",
            destination="Town",
        )

        self.spot = WaitingSpot.objects.create(
            route=self.route,
            name="Reliability Stop",
            latitude="-23.884500",
            longitude="29.738200",
            geofence_radius_meters=100,
        )

    def create_waiting_request(
        self,
        username,
        party_size,
        boarding_pin,
    ):
        passenger = User.objects.create_user(
            username=username,
            email=f"{username}@example.com",
            password="StrongPass123!",
            role="PASSENGER",
        )

        return WaitingRequest.objects.create(
            passenger=passenger,
            waiting_spot=self.spot,
            party_size=party_size,
            boarding_pin=boarding_pin,
            passenger_latitude=(
                self.spot.latitude
            ),
            passenger_longitude=(
                self.spot.longitude
            ),
            distance_from_spot_meters="0.00",
        )

    def create_dispatch(
        self,
        driver,
    ):
        self.client.force_authenticate(
            user=self.dispatcher
        )

        return self.client.post(
            reverse("dispatch-list"),
            {
                "driver": driver.id,
                "route": self.route.id,
                "notes": (
                    "Reliability test dispatch."
                ),
            },
            format="json",
        )

    def cancel_waiting_request(
        self,
        waiting_request,
    ):
        self.client.force_authenticate(
            user=waiting_request.passenger
        )

        return self.client.post(
            reverse(
                "cancel-waiting-request"
            )
        )

    def test_second_taxi_blocked_when_no_unassigned_demand(
        self
    ):
        self.create_waiting_request(
            "only_waiting_group",
            6,
            "A01",
        )

        first_response = (
            self.create_dispatch(
                self.driver_one
            )
        )

        self.assertEqual(
            first_response.status_code,
            status.HTTP_201_CREATED,
        )

        second_response = (
            self.create_dispatch(
                self.driver_two
            )
        )

        self.assertEqual(
            second_response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

        self.assertEqual(
            DispatchAssignment.objects.count(),
            1,
        )

        second_availability = (
            DriverAvailability.objects.get(
                driver=self.driver_two
            )
        )

        self.assertTrue(
            second_availability.is_available
        )

    def test_second_taxi_receives_only_remaining_unassigned_group(
        self
    ):
        group_eight = (
            self.create_waiting_request(
                "group_eight",
                8,
                "A02",
            )
        )

        group_five = (
            self.create_waiting_request(
                "group_five",
                5,
                "A03",
            )
        )

        group_four = (
            self.create_waiting_request(
                "group_four",
                4,
                "A04",
            )
        )

        group_one_a = (
            self.create_waiting_request(
                "group_one_a",
                1,
                "A05",
            )
        )

        group_one_b = (
            self.create_waiting_request(
                "group_one_b",
                1,
                "A06",
            )
        )

        first_response = (
            self.create_dispatch(
                self.driver_one
            )
        )

        self.assertEqual(
            first_response.status_code,
            status.HTTP_201_CREATED,
        )

        first_assignment = (
            DispatchAssignment.objects.get(
                pk=first_response.data["id"]
            )
        )

        self.assertEqual(
            first_assignment.passenger_count,
            15,
        )

        first_ids = set(
            DispatchRequest.objects.filter(
                dispatch=first_assignment
            ).values_list(
                "waiting_request_id",
                flat=True,
            )
        )

        self.assertIn(
            group_eight.id,
            first_ids,
        )

        self.assertIn(
            group_five.id,
            first_ids,
        )

        self.assertIn(
            group_one_a.id,
            first_ids,
        )

        self.assertIn(
            group_one_b.id,
            first_ids,
        )

        self.assertNotIn(
            group_four.id,
            first_ids,
        )

        second_response = (
            self.create_dispatch(
                self.driver_two
            )
        )

        self.assertEqual(
            second_response.status_code,
            status.HTTP_201_CREATED,
        )

        second_assignment = (
            DispatchAssignment.objects.get(
                pk=second_response.data["id"]
            )
        )

        self.assertEqual(
            second_assignment.passenger_count,
            4,
        )

        second_ids = set(
            DispatchRequest.objects.filter(
                dispatch=second_assignment
            ).values_list(
                "waiting_request_id",
                flat=True,
            )
        )

        self.assertEqual(
            second_ids,
            {
                group_four.id,
            },
        )

        self.assertTrue(
            first_ids.isdisjoint(
                second_ids
            )
        )

    def test_cancelled_request_reduces_demand_to_zero_and_cannot_be_dispatched(
        self
    ):
        waiting_request = (
            self.create_waiting_request(
                "cancel_before_dispatch",
                4,
                "B01",
            )
        )

        cancel_response = (
            self.cancel_waiting_request(
                waiting_request
            )
        )

        self.assertEqual(
            cancel_response.status_code,
            status.HTTP_200_OK,
        )

        waiting_request.refresh_from_db()

        self.assertEqual(
            waiting_request.status,
            WaitingRequest.Status.CANCELLED,
        )

        self.client.force_authenticate(
            user=self.dispatcher
        )

        spot_response = self.client.get(
            reverse(
                "waiting-spot-detail",
                kwargs={
                    "pk": self.spot.pk,
                },
            )
        )

        self.assertEqual(
            spot_response.status_code,
            status.HTTP_200_OK,
        )

        self.assertEqual(
            spot_response.data[
                "active_waiting_count"
            ],
            0,
        )

        dispatch_response = (
            self.create_dispatch(
                self.driver_one
            )
        )

        self.assertEqual(
            dispatch_response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

        self.assertFalse(
            DispatchAssignment.objects.exists()
        )

    def test_partial_cancellation_leaves_only_remaining_demand_dispatchable(
        self
    ):
        cancelled_request = (
            self.create_waiting_request(
                "partial_cancel_one",
                4,
                "B02",
            )
        )

        remaining_request = (
            self.create_waiting_request(
                "partial_cancel_two",
                3,
                "B03",
            )
        )

        cancel_response = (
            self.cancel_waiting_request(
                cancelled_request
            )
        )

        self.assertEqual(
            cancel_response.status_code,
            status.HTTP_200_OK,
        )

        self.client.force_authenticate(
            user=self.dispatcher
        )

        spot_response = self.client.get(
            reverse(
                "waiting-spot-detail",
                kwargs={
                    "pk": self.spot.pk,
                },
            )
        )

        self.assertEqual(
            spot_response.data[
                "active_waiting_count"
            ],
            3,
        )

        dispatch_response = (
            self.create_dispatch(
                self.driver_one
            )
        )

        self.assertEqual(
            dispatch_response.status_code,
            status.HTTP_201_CREATED,
        )

        assignment = (
            DispatchAssignment.objects.get(
                pk=dispatch_response.data["id"]
            )
        )

        self.assertEqual(
            assignment.passenger_count,
            3,
        )

        linked_ids = set(
            DispatchRequest.objects.filter(
                dispatch=assignment
            ).values_list(
                "waiting_request_id",
                flat=True,
            )
        )

        self.assertEqual(
            linked_ids,
            {
                remaining_request.id,
            },
        )

    def test_pending_dispatch_recalculates_count_after_one_group_cancels(
        self
    ):
        cancelled_request = (
            self.create_waiting_request(
                "assigned_cancel_one",
                4,
                "C01",
            )
        )

        remaining_request = (
            self.create_waiting_request(
                "assigned_cancel_two",
                3,
                "C02",
            )
        )

        dispatch_response = (
            self.create_dispatch(
                self.driver_one
            )
        )

        self.assertEqual(
            dispatch_response.status_code,
            status.HTTP_201_CREATED,
        )

        assignment = (
            DispatchAssignment.objects.get(
                pk=dispatch_response.data["id"]
            )
        )

        self.assertEqual(
            assignment.passenger_count,
            7,
        )

        cancel_response = (
            self.cancel_waiting_request(
                cancelled_request
            )
        )

        self.assertEqual(
            cancel_response.status_code,
            status.HTTP_200_OK,
        )

        assignment.refresh_from_db()

        self.assertEqual(
            assignment.status,
            DispatchAssignment.Status.PENDING,
        )

        self.assertEqual(
            assignment.passenger_count,
            3,
        )

        remaining_request.refresh_from_db()

        self.assertEqual(
            remaining_request.status,
            WaitingRequest.Status.WAITING,
        )

        availability = (
            DriverAvailability.objects.get(
                driver=self.driver_one
            )
        )

        self.assertFalse(
            availability.is_available
        )

    def test_last_pending_passenger_cancelling_cancels_dispatch_and_frees_driver(
        self
    ):
        waiting_request = (
            self.create_waiting_request(
                "last_assigned_group",
                5,
                "C03",
            )
        )

        dispatch_response = (
            self.create_dispatch(
                self.driver_one
            )
        )

        self.assertEqual(
            dispatch_response.status_code,
            status.HTTP_201_CREATED,
        )

        assignment = (
            DispatchAssignment.objects.get(
                pk=dispatch_response.data["id"]
            )
        )

        cancel_response = (
            self.cancel_waiting_request(
                waiting_request
            )
        )

        self.assertEqual(
            cancel_response.status_code,
            status.HTTP_200_OK,
        )

        assignment.refresh_from_db()

        self.assertEqual(
            assignment.status,
            DispatchAssignment.Status.CANCELLED,
        )

        availability = (
            DriverAvailability.objects.get(
                driver=self.driver_one
            )
        )

        self.assertTrue(
            availability.is_available
        )

    def test_en_route_trip_with_all_passengers_cancelled_remains_manual_to_complete(
        self
    ):
        waiting_request = (
            self.create_waiting_request(
                "en_route_cancel_group",
                3,
                "D01",
            )
        )

        dispatch_response = (
            self.create_dispatch(
                self.driver_one
            )
        )

        self.assertEqual(
            dispatch_response.status_code,
            status.HTTP_201_CREATED,
        )

        assignment = (
            DispatchAssignment.objects.get(
                pk=dispatch_response.data["id"]
            )
        )

        self.client.force_authenticate(
            user=self.driver_one
        )

        accept_response = self.client.post(
            reverse(
                "dispatch-accept",
                kwargs={
                    "pk": assignment.pk,
                },
            )
        )

        self.assertEqual(
            accept_response.status_code,
            status.HTTP_200_OK,
        )

        assignment.refresh_from_db()

        self.assertEqual(
            assignment.status,
            DispatchAssignment.Status.EN_ROUTE,
        )

        cancel_response = (
            self.cancel_waiting_request(
                waiting_request
            )
        )

        self.assertEqual(
            cancel_response.status_code,
            status.HTTP_200_OK,
        )

        assignment.refresh_from_db()

        # Do not silently auto-complete a taxi
        # that is already travelling.
        self.assertEqual(
            assignment.status,
            DispatchAssignment.Status.EN_ROUTE,
        )

        self.client.force_authenticate(
            user=self.driver_one
        )

        complete_response = self.client.post(
            reverse(
                "dispatch-complete",
                kwargs={
                    "pk": assignment.pk,
                },
            )
        )

        self.assertEqual(
            complete_response.status_code,
            status.HTTP_200_OK,
        )

        assignment.refresh_from_db()

        self.assertEqual(
            assignment.status,
            DispatchAssignment.Status.COMPLETED,
        )

        trip = Trip.objects.get(
            dispatch=assignment
        )

        self.assertIsNotNone(
            trip.completed_at
        )

        availability = (
            DriverAvailability.objects.get(
                driver=self.driver_one
            )
        )

        self.assertTrue(
            availability.is_available
        )

    def test_geofence_cancellation_recalculates_pending_dispatch_count(
        self
    ):
        leaving_request = (
            self.create_waiting_request(
                "geofence_leave_group",
                4,
                "E01",
            )
        )

        remaining_request = (
            self.create_waiting_request(
                "geofence_stay_group",
                3,
                "E02",
            )
        )

        dispatch_response = (
            self.create_dispatch(
                self.driver_one
            )
        )

        self.assertEqual(
            dispatch_response.status_code,
            status.HTTP_201_CREATED,
        )

        assignment = (
            DispatchAssignment.objects.get(
                pk=dispatch_response.data["id"]
            )
        )

        self.assertEqual(
            assignment.passenger_count,
            7,
        )

        leaving_request.outside_geofence_since = (
            timezone.now()
            - timedelta(seconds=61)
        )

        leaving_request.save(
            update_fields=[
                "outside_geofence_since",
            ]
        )

        self.client.force_authenticate(
            user=leaving_request.passenger
        )

        response = self.client.post(
            reverse(
                "revalidate-waiting-location"
            ),
            {
                "latitude": "-23.900000",
                "longitude": "29.738200",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.assertTrue(
            response.data["cancelled"]
        )

        leaving_request.refresh_from_db()
        remaining_request.refresh_from_db()
        assignment.refresh_from_db()

        self.assertEqual(
            leaving_request.status,
            WaitingRequest.Status.CANCELLED,
        )

        self.assertEqual(
            remaining_request.status,
            WaitingRequest.Status.WAITING,
        )

        self.assertEqual(
            assignment.status,
            DispatchAssignment.Status.PENDING,
        )

        self.assertEqual(
            assignment.passenger_count,
            3,
        )

        availability = (
            DriverAvailability.objects.get(
                driver=self.driver_one
            )
        )

        self.assertFalse(
            availability.is_available
        )

    def test_geofence_cancellation_of_last_pending_group_cancels_dispatch(
        self
    ):
        waiting_request = (
            self.create_waiting_request(
                "geofence_last_group",
                5,
                "E03",
            )
        )

        dispatch_response = (
            self.create_dispatch(
                self.driver_one
            )
        )

        self.assertEqual(
            dispatch_response.status_code,
            status.HTTP_201_CREATED,
        )

        assignment = (
            DispatchAssignment.objects.get(
                pk=dispatch_response.data["id"]
            )
        )

        waiting_request.outside_geofence_since = (
            timezone.now()
            - timedelta(seconds=61)
        )

        waiting_request.save(
            update_fields=[
                "outside_geofence_since",
            ]
        )

        self.client.force_authenticate(
            user=waiting_request.passenger
        )

        response = self.client.post(
            reverse(
                "revalidate-waiting-location"
            ),
            {
                "latitude": "-23.900000",
                "longitude": "29.738200",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.assertTrue(
            response.data["cancelled"]
        )

        waiting_request.refresh_from_db()
        assignment.refresh_from_db()

        self.assertEqual(
            waiting_request.status,
            WaitingRequest.Status.CANCELLED,
        )

        self.assertEqual(
            assignment.status,
            DispatchAssignment.Status.CANCELLED,
        )

        availability = (
            DriverAvailability.objects.get(
                driver=self.driver_one
            )
        )

        self.assertTrue(
            availability.is_available
        )

    def _check_in_for_reliability(self, passenger, party_size):
        self.client.force_authenticate(user=passenger)

        response = self.client.post(
            reverse("passenger-check-in"),
            {
                "waiting_spot": self.spot.pk,
                "latitude": str(self.spot.latitude),
                "longitude": str(self.spot.longitude),
                "party_size": party_size,
            },
            format="json",
        )

        self._assert_api_status(response, status.HTTP_201_CREATED)
        return WaitingRequest.objects.get(pk=response.data["id"])

    def _assert_spot_demand(self, expected):
        self.client.force_authenticate(user=self.dispatcher)

        response = self.client.get(
            reverse(
                "waiting-spot-detail",
                kwargs={"pk": self.spot.pk},
            )
        )

        self._assert_api_status(response, status.HTTP_200_OK)
        self.assertEqual(
            response.data["active_waiting_count"],
            expected,
        )

    def _boarding_attempt(self, assignment, code, spot=None, driver=None):
        return self._dispatch_action(
            assignment,
            "confirm-boarding",
            user=driver,
            data={
                "waiting_spot": (self.spot if spot is None else spot).pk,
                "boarding_pin": code,
            },
        )

    def test_cancelled_code_cannot_board_or_change_other_groups(self):
        cancelled = self.create_waiting_request(
            "cancelled_code", 3, "B81"
        )
        remaining = self.create_waiting_request(
            "remaining_code", 2, "B82"
        )
        assignment = self._create_lifecycle_dispatch()
        self._accept_lifecycle_dispatch(assignment)

        self._assert_api_status(
            self.cancel_waiting_request(cancelled),
            status.HTTP_200_OK,
        )
        cancelled.refresh_from_db()
        self.assertEqual(
            cancelled.status,
            WaitingRequest.Status.CANCELLED,
        )

        before = self._lifecycle_state()

        response = self._boarding_attempt(
            assignment,
            cancelled.boarding_pin,
        )
        self._assert_api_status(
            response,
            status.HTTP_400_BAD_REQUEST,
        )
        self._assert_lifecycle_unchanged(before)

        remaining.refresh_from_db()
        self.assertEqual(
            remaining.status,
            WaitingRequest.Status.WAITING,
        )
        self.assertEqual(remaining.party_size, 2)
        self.assertEqual(
            Trip.objects.get(
                dispatch=assignment
            ).boarded_passenger_count,
            0,
        )
        self._assert_spot_demand(0)

    def test_valid_code_at_wrong_assigned_spot_is_rejected(self):
        first = self.create_waiting_request(
            "spot_code_one", 2, "S11"
        )
        second = self.create_waiting_request(
            "spot_code_two", 3, "S12"
        )

        other_spot = WaitingSpot.objects.create(
            route=self.route,
            name="Other Boarding Stop",
            latitude="-23.884600",
            longitude="29.738300",
            geofence_radius_meters=100,
            stop_order=2,
        )
        second.waiting_spot = other_spot
        second.save(update_fields=["waiting_spot"])

        assignment = self._create_lifecycle_dispatch()
        self._accept_lifecycle_dispatch(assignment)
        before = self._lifecycle_state()

        response = self._boarding_attempt(
            assignment,
            first.boarding_pin,
            spot=other_spot,
        )
        self._assert_api_status(
            response,
            status.HTTP_400_BAD_REQUEST,
        )
        self._assert_lifecycle_unchanged(before)

        # The same code must still work at its correct spot.
        self._board_lifecycle_group(assignment, first)

        second.refresh_from_db()
        self.assertEqual(
            second.status,
            WaitingRequest.Status.WAITING,
        )
        self.assertEqual(second.party_size, 3)

    def test_reused_code_boards_new_request_only_after_recheck_in(self):
        old_request, old_assignment = self._lifecycle_fixture()
        self._accept_lifecycle_dispatch(old_assignment)
        self._assert_spot_demand(0)

        self._assert_api_status(
            self.cancel_waiting_request(old_request),
            status.HTTP_200_OK,
        )
        old_request.refresh_from_db()
        self.assertEqual(
            old_request.status,
            WaitingRequest.Status.CANCELLED,
        )

        cancelled_record = WaitingRequest.objects.values().get(
            pk=old_request.pk
        )
        self._assert_spot_demand(0)

        def choose_previous_code(available_codes):
            self.assertIn(
                old_request.boarding_pin,
                available_codes,
            )
            return old_request.boarding_pin

        with patch(
            "transport.serializers.secrets.choice",
            side_effect=choose_previous_code,
        ) as choose_code:
            new_request = self._check_in_for_reliability(
                old_request.passenger,
                party_size=2,
            )

        choose_code.assert_called_once()

        self.assertNotEqual(new_request.pk, old_request.pk)
        self.assertEqual(
            new_request.boarding_pin,
            old_request.boarding_pin,
        )
        self.assertEqual(new_request.party_size, 2)
        self.assertEqual(
            WaitingRequest.objects.filter(
                passenger=old_request.passenger,
                status=WaitingRequest.Status.WAITING,
            ).count(),
            1,
        )
        self._assert_spot_demand(2)

        response = self.create_dispatch(self.driver_two)
        self._assert_api_status(
            response,
            status.HTTP_201_CREATED,
        )
        new_assignment = DispatchAssignment.objects.get(
            pk=response.data["id"]
        )

        self.assertEqual(new_assignment.passenger_count, 2)
        self.assertEqual(
            set(
                DispatchRequest.objects.filter(
                    dispatch=new_assignment
                ).values_list(
                    "waiting_request_id",
                    flat=True,
                )
            ),
            {new_request.pk},
        )
        self._assert_api_status(
            self._dispatch_action(
                new_assignment,
                "accept",
                user=self.driver_two,
            ),
            status.HTTP_200_OK,
        )

        # The old taxi cannot consume the new booking's reused code.
        before = self._lifecycle_state()

        self._assert_api_status(
            self._boarding_attempt(
                old_assignment,
                new_request.boarding_pin,
            ),
            status.HTTP_400_BAD_REQUEST,
        )
        self._assert_lifecycle_unchanged(before)

        self._assert_api_status(
            self._boarding_attempt(
                new_assignment,
                new_request.boarding_pin,
                driver=self.driver_two,
            ),
            status.HTTP_200_OK,
        )

        new_request.refresh_from_db()
        self.assertEqual(
            new_request.status,
            WaitingRequest.Status.BOARDED,
        )
        self.assertEqual(
            Trip.objects.get(
                dispatch=new_assignment
            ).boarded_passenger_count,
            2,
        )

        # The historical cancelled request must remain unchanged.
        self.assertEqual(
            WaitingRequest.objects.values().get(pk=old_request.pk),
            cancelled_record,
        )
        self.assertFalse(
            DispatchRequest.objects.get(
                dispatch=old_assignment,
                waiting_request=old_request,
            ).boarded
        )
        self.assertEqual(
            Trip.objects.get(
                dispatch=old_assignment
            ).boarded_passenger_count,
            0,
        )
        self._assert_spot_demand(0)

    def test_mixed_boarded_and_cancelled_groups_allow_completion(self):
        boarded = self.create_waiting_request(
            "mixed_boarded", 3, "M81"
        )
        cancelled = self.create_waiting_request(
            "mixed_cancelled", 2, "M82"
        )
        assignment = self._create_lifecycle_dispatch()
        self._accept_lifecycle_dispatch(assignment)
        self._assert_spot_demand(0)

        self._board_lifecycle_group(assignment, boarded)
        self._assert_spot_demand(0)

        # Completion must fail while the second group still waits.
        before = self._lifecycle_state()

        self._assert_api_status(
            self._dispatch_action(assignment, "complete"),
            status.HTTP_400_BAD_REQUEST,
        )
        self._assert_lifecycle_unchanged(before)

        self._assert_api_status(
            self.cancel_waiting_request(cancelled),
            status.HTTP_200_OK,
        )
        self._assert_spot_demand(0)

        self._assert_api_status(
            self._dispatch_action(assignment, "complete"),
            status.HTTP_200_OK,
        )

        assignment.refresh_from_db()
        boarded.refresh_from_db()
        cancelled.refresh_from_db()
        trip = Trip.objects.get(dispatch=assignment)

        self.assertEqual(
            assignment.status,
            DispatchAssignment.Status.COMPLETED,
        )
        self.assertEqual(
            boarded.status,
            WaitingRequest.Status.BOARDED,
        )
        self.assertEqual(
            cancelled.status,
            WaitingRequest.Status.CANCELLED,
        )
        self.assertEqual(
            (boarded.party_size, cancelled.party_size),
            (3, 2),
        )
        self.assertEqual(trip.boarded_passenger_count, 3)
        self.assertIsNotNone(trip.completed_at)
        self.assertTrue(
            DriverAvailability.objects.get(
                driver=self.driver_one
            ).is_available
        )

    def test_new_arrival_uses_second_taxi_after_pending_cancellation(self):
        leaving = self.create_waiting_request(
            "fixed_leaving", 4, "F81"
        )
        staying = self.create_waiting_request(
            "fixed_staying", 3, "F82"
        )
        first_assignment = self._create_lifecycle_dispatch()
        self.assertEqual(first_assignment.passenger_count, 7)

        newcomer = User.objects.create_user(
            username="fixed_newcomer",
            email="fixed_newcomer@example.com",
            password="StrongPass123!",
            role="PASSENGER",
        )
        new_request = self._check_in_for_reliability(
            newcomer,
            party_size=5,
        )

        first_assignment.refresh_from_db()
        self.assertEqual(first_assignment.passenger_count, 7)
        self.assertFalse(
            DispatchRequest.objects.filter(
                waiting_request=new_request
            ).exists()
        )
        self._assert_spot_demand(5)

        self._assert_api_status(
            self.cancel_waiting_request(leaving),
            status.HTTP_200_OK,
        )
        self._assert_lifecycle_driver_busy(first_assignment)
        self.assertEqual(first_assignment.passenger_count, 3)

        # Freed seats must not automatically absorb the new group.
        self.assertFalse(
            DispatchRequest.objects.filter(
                waiting_request=new_request
            ).exists()
        )
        self._assert_spot_demand(5)

        response = self.create_dispatch(self.driver_two)
        self._assert_api_status(
            response,
            status.HTTP_201_CREATED,
        )
        second_assignment = DispatchAssignment.objects.get(
            pk=response.data["id"]
        )

        self.assertEqual(second_assignment.passenger_count, 5)
        self.assertEqual(
            set(
                DispatchRequest.objects.filter(
                    dispatch=second_assignment
                ).values_list(
                    "waiting_request_id",
                    flat=True,
                )
            ),
            {new_request.pk},
        )
        self.assertEqual(
            set(
                DispatchRequest.objects.filter(
                    dispatch=first_assignment,
                    waiting_request__status=WaitingRequest.Status.WAITING,
                ).values_list(
                    "waiting_request_id",
                    flat=True,
                )
            ),
            {staying.pk},
        )
        self.assertFalse(
            DriverAvailability.objects.get(
                driver=self.driver_two
            ).is_available
        )

        for waiting_request, expected_size in (
            (leaving, 4),
            (staying, 3),
            (new_request, 5),
        ):
            waiting_request.refresh_from_db()
            self.assertEqual(
                waiting_request.party_size,
                expected_size,
            )

        self._assert_spot_demand(0)
        # Additional lifecycle/retry tests.

    def _assert_push_records(
        self, push, assignment, notification_type, recipient_ids
    ):
        notifications = list(
            assignment.notifications.filter(
                notification_type=notification_type
            )
        )

        self.assertCountEqual(
            [notification.recipient_id for notification in notifications],
            recipient_ids,
        )

        self.assertCountEqual(
            [
                (
                    call.kwargs["recipient"].pk,
                    str(call.kwargs["data"]["notification_id"]),
                    str(call.kwargs["data"]["dispatch_id"]),
                    call.kwargs["data"]["notification_type"],
                )
                for call in push.call_args_list
            ],
            [
                (
                    notification.recipient_id,
                    str(notification.pk),
                    str(assignment.pk),
                    notification.notification_type,
                )
                for notification in notifications
            ],
        )

    def test_dispatch_survives_push_failure_without_duplicate_retry_alerts(self):
        waiting_request = self.create_waiting_request(
            "push_dispatch_passenger", 3, "N71"
        )

        with patch(
            "transport.notification_service.send_push_notification",
            side_effect=RuntimeError("Simulated push provider outage"),
        ) as push:
            with self.captureOnCommitCallbacks(execute=True):
                assignment = self._create_lifecycle_dispatch()
                before_delivery = self._lifecycle_state()
                push.assert_not_called()

            self._assert_lifecycle_unchanged(before_delivery)
            self._assert_lifecycle_driver_busy(assignment)
            self.assertEqual(assignment.passenger_count, 3)

            self.assertEqual(
                list(
                    DispatchRequest.objects.filter(
                        dispatch=assignment
                    ).values_list(
                        "waiting_request_id",
                        flat=True,
                    )
                ),
                [waiting_request.pk],
            )
            self.assertFalse(
                Trip.objects.filter(dispatch=assignment).exists()
            )

            self._assert_push_records(
                push,
                assignment,
                "NEW_DISPATCH",
                [self.driver_one.pk],
            )

            # Retrying the dispatch must not create another alert.
            with self.captureOnCommitCallbacks(execute=True):
                response = self.create_dispatch(self.driver_one)
                self._assert_api_status(
                    response,
                    status.HTTP_400_BAD_REQUEST,
                )

            self._assert_lifecycle_unchanged(before_delivery)
            push.assert_called_once()

    def test_acceptance_survives_push_failures_for_all_relevant_recipients(self):
        first = self.create_waiting_request(
            "push_first", 3, "N81"
        )
        second = self.create_waiting_request(
            "push_second", 2, "N82"
        )
        cancelled = self.create_waiting_request(
            "push_cancelled", 1, "N83"
        )
        assignment = self._create_lifecycle_dispatch()

        self._assert_api_status(
            self.cancel_waiting_request(cancelled),
            status.HTTP_200_OK,
        )

        with patch(
            "transport.notification_service.send_push_notification",
            side_effect=RuntimeError("Simulated push provider outage"),
        ) as push:
            with self.captureOnCommitCallbacks(execute=True):
                self._accept_lifecycle_dispatch(assignment)
                before_delivery = self._lifecycle_state()
                push.assert_not_called()

            self._assert_lifecycle_unchanged(before_delivery)

            # Every relevant recipient gets an attempt, even when
            # earlier attempts fail. The cancelled passenger is excluded.
            self._assert_push_records(
                push,
                assignment,
                "DISPATCH_ACCEPTED",
                [
                    first.passenger_id,
                    second.passenger_id,
                    self.dispatcher.pk,
                ],
            )

            trip = Trip.objects.get(dispatch=assignment)
            self.assertIsNotNone(trip.en_route_at)
            self.assertIsNone(trip.completed_at)
            self.assertIsNotNone(assignment.responded_at)
            self.assertFalse(
                DriverAvailability.objects.get(
                    driver=self.driver_one
                ).is_available
            )

            # Retrying acceptance must preserve timestamps and alerts.
            with self.captureOnCommitCallbacks(execute=True):
                response = self._dispatch_action(
                    assignment,
                    "accept",
                )
                self._assert_api_status(
                    response,
                    status.HTTP_400_BAD_REQUEST,
                )

            self._assert_lifecycle_unchanged(before_delivery)
            self.assertEqual(push.call_count, 3)

    def test_rolled_back_dispatch_does_not_send_push_or_keep_notifications(self):
        self.create_waiting_request(
            "push_rollback", 3, "N91"
        )
        before = self._lifecycle_state()

        with patch(
            "transport.notification_service.send_push_notification"
        ) as push:
            with self.captureOnCommitCallbacks(execute=True):
                with self.assertRaisesMessage(
                    RuntimeError,
                    "Simulated transaction abort",
                ):
                    with transaction.atomic():
                        self._create_lifecycle_dispatch()
                        push.assert_not_called()
                        raise RuntimeError(
                            "Simulated transaction abort"
                        )

            push.assert_not_called()

        self._assert_lifecycle_unchanged(before)

    def _assert_api_status(self, response, expected):
        self.assertEqual(
            response.status_code,
            expected,
            msg=str(getattr(response, "data", None)),
        )

    def _lifecycle_state(self):
        from .models import Notification

        return {
            model.__name__: list(model.objects.order_by("pk").values())
            for model in (
                WaitingRequest,
                DispatchAssignment,
                DispatchRequest,
                Trip,
                DriverAvailability,
                Notification,
            )
        }

    def _assert_lifecycle_unchanged(self, before):
        after = self._lifecycle_state()
        for model_name, rows in before.items():
            self.assertEqual(
                after[model_name],
                rows,
                msg=f"Rejected/repeated request changed {model_name}.",
            )

    def _create_lifecycle_dispatch(self):
        response = self.create_dispatch(self.driver_one)
        self._assert_api_status(response, status.HTTP_201_CREATED)
        return DispatchAssignment.objects.get(pk=response.data["id"])

    def _lifecycle_fixture(self):
        waiting_request = self.create_waiting_request(
            "lifecycle_passenger", 3, "L11"
        )
        assignment = self._create_lifecycle_dispatch()
        return waiting_request, assignment

    def _dispatch_action(self, assignment, action, user=None, data=None):
        self.client.force_authenticate(
            user=self.driver_one if user is None else user
        )
        return self.client.post(
            reverse(f"dispatch-{action}", kwargs={"pk": assignment.pk}),
            {} if data is None else data,
            format="json",
        )

    def _accept_lifecycle_dispatch(self, assignment):
        self._assert_api_status(
            self._dispatch_action(assignment, "accept"),
            status.HTTP_200_OK,
        )
        assignment.refresh_from_db()
        self.assertEqual(
            assignment.status, DispatchAssignment.Status.EN_ROUTE
        )
        self.assertEqual(
            Trip.objects.filter(dispatch=assignment).count(), 1
        )

    def _board_lifecycle_group(self, assignment, waiting_request):
        self._assert_api_status(
            self._dispatch_action(
                assignment,
                "confirm-boarding",
                data={
                    "waiting_spot": self.spot.pk,
                    "boarding_pin": waiting_request.boarding_pin,
                },
            ),
            status.HTTP_200_OK,
        )
        waiting_request.refresh_from_db()
        self.assertEqual(
            waiting_request.status, WaitingRequest.Status.BOARDED
        )
        self.assertEqual(
            Trip.objects.get(dispatch=assignment).boarded_passenger_count,
            waiting_request.party_size,
        )

    def _assert_lifecycle_driver_busy(self, assignment):
        assignment.refresh_from_db()
        self.assertEqual(
            assignment.status, DispatchAssignment.Status.PENDING
        )
        self.assertFalse(
            DriverAvailability.objects.get(
                driver=self.driver_one
            ).is_available
        )


    def test_repeated_acceptance_preserves_trip_timestamps_and_notifications(self):
        _, assignment = self._lifecycle_fixture()
        self._accept_lifecycle_dispatch(assignment)
        self.assertTrue(
            assignment.notifications.filter(
                notification_type="DISPATCH_ACCEPTED"
            ).exists()
        )
        before = self._lifecycle_state()

        self._assert_api_status(
            self._dispatch_action(assignment, "accept"),
            status.HTTP_400_BAD_REQUEST,
        )

        self._assert_lifecycle_unchanged(before)

    def test_repeated_passenger_cancellation_has_no_further_side_effects(self):
        waiting_request, assignment = self._lifecycle_fixture()
        self._assert_api_status(
            self.cancel_waiting_request(waiting_request),
            status.HTTP_200_OK,
        )
        assignment.refresh_from_db()
        waiting_request.refresh_from_db()
        self.assertEqual(
            assignment.status, DispatchAssignment.Status.CANCELLED
        )
        self.assertEqual(
            waiting_request.status, WaitingRequest.Status.CANCELLED
        )
        self.assertTrue(
            DriverAvailability.objects.get(
                driver=self.driver_one
            ).is_available
        )
        before = self._lifecycle_state()

        self._assert_api_status(
            self.cancel_waiting_request(waiting_request),
            status.HTTP_400_BAD_REQUEST,
        )

        self._assert_lifecycle_unchanged(before)

    def test_old_dispatch_cancellation_cannot_free_a_reassigned_driver(self):
        _, old_assignment = self._lifecycle_fixture()
        self._assert_api_status(
            self._dispatch_action(
                old_assignment, "cancel", user=self.dispatcher
            ),
            status.HTTP_200_OK,
        )
        old_assignment.refresh_from_db()
        self.assertEqual(
            old_assignment.status, DispatchAssignment.Status.CANCELLED
        )

        new_assignment = self._create_lifecycle_dispatch()
        self.assertNotEqual(old_assignment.pk, new_assignment.pk)
        self._assert_lifecycle_driver_busy(new_assignment)
        before = self._lifecycle_state()

        self._assert_api_status(
            self._dispatch_action(
                old_assignment, "cancel", user=self.dispatcher
            ),
            status.HTTP_400_BAD_REQUEST,
        )

        self._assert_lifecycle_unchanged(before)
        self._assert_lifecycle_driver_busy(new_assignment)

    def test_old_rejection_cannot_free_a_reassigned_driver(self):
        _, old_assignment = self._lifecycle_fixture()
        self._assert_api_status(
            self._dispatch_action(old_assignment, "reject"),
            status.HTTP_200_OK,
        )
        old_assignment.refresh_from_db()
        self.assertEqual(
            old_assignment.status, DispatchAssignment.Status.REJECTED
        )

        new_assignment = self._create_lifecycle_dispatch()
        self.assertNotEqual(old_assignment.pk, new_assignment.pk)
        self._assert_lifecycle_driver_busy(new_assignment)
        before = self._lifecycle_state()

        self._assert_api_status(
            self._dispatch_action(old_assignment, "reject"),
            status.HTTP_400_BAD_REQUEST,
        )

        self._assert_lifecycle_unchanged(before)
        self._assert_lifecycle_driver_busy(new_assignment)

    def test_completed_dispatch_actions_cannot_change_a_new_assignment(self):
        waiting_request, old_assignment = self._lifecycle_fixture()
        self._accept_lifecycle_dispatch(old_assignment)
        self._board_lifecycle_group(old_assignment, waiting_request)
        self._assert_api_status(
            self._dispatch_action(old_assignment, "complete"),
            status.HTTP_200_OK,
        )
        old_assignment.refresh_from_db()
        self.assertEqual(
            old_assignment.status, DispatchAssignment.Status.COMPLETED
        )
        self.assertIsNotNone(
            Trip.objects.get(dispatch=old_assignment).completed_at
        )

        self.create_waiting_request(
            "next_trip_passenger", 2, "L12"
        )
        new_assignment = self._create_lifecycle_dispatch()
        self._assert_lifecycle_driver_busy(new_assignment)
        before = self._lifecycle_state()

        boarding_data = {
            "waiting_spot": self.spot.pk,
            "boarding_pin": waiting_request.boarding_pin,
        }
        for action, user, data in (
            ("complete", self.driver_one, None),
            ("accept", self.driver_one, None),
            ("reject", self.driver_one, None),
            ("confirm-boarding", self.driver_one, boarding_data),
            ("cancel", self.dispatcher, None),
        ):
            with self.subTest(action=action):
                self._assert_api_status(
                    self._dispatch_action(
                        old_assignment, action, user=user, data=data
                    ),
                    status.HTTP_400_BAD_REQUEST,
                )
                self._assert_lifecycle_unchanged(before)
                self._assert_lifecycle_driver_busy(new_assignment)

    def test_cancelled_dispatch_cannot_be_accepted_while_its_passenger_still_waits(self):
        waiting_request, assignment = self._lifecycle_fixture()
        self._assert_api_status(
            self._dispatch_action(
                assignment, "cancel", user=self.dispatcher
            ),
            status.HTTP_200_OK,
        )
        waiting_request.refresh_from_db()
        self.assertEqual(
            waiting_request.status, WaitingRequest.Status.WAITING
        )
        self.assertFalse(
            Trip.objects.filter(dispatch=assignment).exists()
        )
        before = self._lifecycle_state()

        self._assert_api_status(
            self._dispatch_action(assignment, "accept"),
            status.HTTP_400_BAD_REQUEST,
        )

        self._assert_lifecycle_unchanged(before)

    def test_passenger_cannot_cancel_someone_elses_request_by_supplying_ids(self):
        waiting_request, _ = self._lifecycle_fixture()
        other_passenger = User.objects.create_user(
            username="lifecycle_other_passenger",
            email="lifecycle_other_passenger@example.com",
            password="StrongPass123!",
            role="PASSENGER",
        )
        before = self._lifecycle_state()

        # This caller has no active request of their own.
        self.client.force_authenticate(user=other_passenger)
        response = self.client.post(
            reverse("cancel-waiting-request"),
            {
                "id": waiting_request.pk,
                "waiting_request": waiting_request.pk,
                "passenger": waiting_request.passenger_id,
            },
            format="json",
        )

        self._assert_api_status(response, status.HTTP_400_BAD_REQUEST)
        self._assert_lifecycle_unchanged(before)

    def test_passenger_cannot_operate_driver_or_dispatcher_actions(self):
        waiting_request, assignment = self._lifecycle_fixture()
        passenger = waiting_request.passenger
        before = self._lifecycle_state()

        for action in ("accept", "reject", "cancel"):
            with self.subTest(phase="pending", action=action):
                self._assert_api_status(
                    self._dispatch_action(
                        assignment, action, user=passenger
                    ),
                    status.HTTP_403_FORBIDDEN,
                )
                self._assert_lifecycle_unchanged(before)

        self._accept_lifecycle_dispatch(assignment)
        before = self._lifecycle_state()
        self._assert_api_status(
            self._dispatch_action(
                assignment,
                "confirm-boarding",
                user=passenger,
                data={
                    "waiting_spot": self.spot.pk,
                    "boarding_pin": waiting_request.boarding_pin,
                },
            ),
            status.HTTP_403_FORBIDDEN,
        )
        self._assert_lifecycle_unchanged(before)

        # Completion is now valid for the driver, but not for a passenger.
        self._board_lifecycle_group(assignment, waiting_request)
        before = self._lifecycle_state()
        self._assert_api_status(
            self._dispatch_action(
                assignment, "complete", user=passenger
            ),
            status.HTTP_403_FORBIDDEN,
        )
        self._assert_lifecycle_unchanged(before)

    def test_boarded_passenger_cannot_cancel_and_undo_boarding(self):
        waiting_request, assignment = self._lifecycle_fixture()
        self._accept_lifecycle_dispatch(assignment)
        self._board_lifecycle_group(assignment, waiting_request)
        before = self._lifecycle_state()

        self._assert_api_status(
            self.cancel_waiting_request(waiting_request),
            status.HTTP_400_BAD_REQUEST,
        )

        self._assert_lifecycle_unchanged(before)

    def test_repeated_dispatch_creation_does_not_duplicate_assignment_or_links(self):
        # Create the first dispatch before introducing more demand.
        assigned_group, assignment = self._lifecycle_fixture()

        self.assertEqual(
            assignment.passenger_count,
            assigned_group.party_size,
        )

        self.assertSetEqual(
            set(
                DispatchRequest.objects.filter(
                    dispatch=assignment
                ).values_list(
                    "waiting_request_id",
                    flat=True,
                )
            ),
            {assigned_group.pk},
        )

        # New passengers arrive while this driver is already assigned.
        remaining_group = self.create_waiting_request(
            "retry_remaining_group",
            15,
            "L12",
        )

        self.assertEqual(
            remaining_group.status,
            WaitingRequest.Status.WAITING,
        )

        self.assertFalse(
            DispatchRequest.objects.filter(
                waiting_request=remaining_group
            ).exists()
        )

        before = self._lifecycle_state()

        repeated_response = self.create_dispatch(
            self.driver_one
        )

        self._assert_api_status(
            repeated_response,
            status.HTTP_400_BAD_REQUEST,
        )

        self._assert_lifecycle_unchanged(before)

        self.assertEqual(
            DispatchAssignment.objects.count(),
            1,
        )

        self._assert_lifecycle_driver_busy(
            assignment
        )

    def test_push_failure_does_not_undo_created_dispatch(self):
        waiting_request = self.create_waiting_request(
            "push_failure_group",
            3,
            "N31",
        )

        with patch(
            "transport.notification_service.send_push_notification",
            side_effect=RuntimeError("FCM unavailable"),
        ) as send_push:
            with self.captureOnCommitCallbacks(execute=True) as callbacks:
                response = self.create_dispatch(self.driver_one)
                send_push.assert_not_called()

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )
        self.assertEqual(len(callbacks), 1)
        send_push.assert_called_once()

        assignment = DispatchAssignment.objects.get(
            pk=response.data["id"]
        )

        self.assertEqual(
            assignment.status,
            DispatchAssignment.Status.PENDING,
        )
        self.assertEqual(assignment.passenger_count, 3)
        self.assertTrue(
            DispatchRequest.objects.filter(
                dispatch=assignment,
                waiting_request=waiting_request,
            ).exists()
        )
        self.assertFalse(
            DriverAvailability.objects.get(
                driver=self.driver_one
            ).is_available
        )
        self.assertTrue(
            Notification.objects.filter(
                recipient=self.driver_one,
                dispatch=assignment,
                notification_type=Notification.Type.NEW_DISPATCH,
            ).exists()
        )

from queue import Empty, Queue
from threading import Thread
from time import monotonic, sleep
from traceback import format_exc

from django.db import connection, connections, transaction
from rest_framework.test import (
    APIRequestFactory,
    APITransactionTestCase,
    force_authenticate,
)

from .views import DispatchAssignmentViewSet


class DispatchConcurrencyTests(APITransactionTestCase):
    def setUp(self):
        super().setUp()

        if connection.vendor != "postgresql":
            self.skipTest(
                "These concurrency tests require PostgreSQL."
            )

        self.dispatchers = [
            self._make_user(
                f"race_dispatcher_{i}",
                "DISPATCHER",
            )
            for i in range(2)
        ]

        self.drivers = [
            self._make_user(
                f"race_driver_{i}",
                "DRIVER",
            )
            for i in range(2)
        ]

        for driver in self.drivers:
            DriverAvailability.objects.create(
                driver=driver,
                is_available=True,
            )

        self.route = Route.objects.create(
            name="Concurrency Route",
            origin="Campus",
            destination="Town",
        )

        self.spot = WaitingSpot.objects.create(
            route=self.route,
            name="Concurrency Stop",
            stop_order=1,
            latitude="-23.884500",
            longitude="29.738200",
            geofence_radius_meters=100,
        )

        passenger = self._make_user(
            "race_passenger",
            "PASSENGER",
        )

        self.waiting_request = WaitingRequest.objects.create(
            passenger=passenger,
            waiting_spot=self.spot,
            party_size=6,
            boarding_pin="R11",
            passenger_latitude=self.spot.latitude,
            passenger_longitude=self.spot.longitude,
            distance_from_spot_meters="0.00",
        )

        self.dispatch_url = reverse("dispatch-list")

    def _make_user(self, username, role):
        return User.objects.create_user(
            username=username,
            email=f"{username}@example.com",
            password="StrongPass123!",
            role=role,
        )

    def _dispatch_worker(
        self,
        dispatcher_id,
        driver_id,
        ready,
        results,
    ):
        # Each thread uses its own database connection.
        database = connections["default"]

        try:
            database.close()

            with database.cursor() as cursor:
                cursor.execute("SET lock_timeout = '20s'")
                cursor.execute("SET statement_timeout = '25s'")
                cursor.execute("SELECT pg_backend_pid()")
                backend_pid = cursor.fetchone()[0]

            dispatcher = User.objects.get(
                pk=dispatcher_id
            )

            request = APIRequestFactory().post(
                self.dispatch_url,
                {
                    "driver": driver_id,
                    "route": self.route.pk,
                },
                format="json",
            )

            force_authenticate(
                request,
                user=dispatcher,
            )

            ready.put(backend_pid)

            # Execute the real view, permissions and serializer.
            view = DispatchAssignmentViewSet.as_view(
                {"post": "create"}
            )

            response = view(request)

            results.put({
                "status": response.status_code,
                "data": repr(response.data),
                "error": None,
            })

        except Exception:
            results.put({
                "status": None,
                "data": None,
                "error": format_exc(),
            })

        finally:
            database.close()

    def _run_overlapping_dispatches(
        self,
        driver_ids,
        gate,
    ):
        ready = Queue()
        results = Queue()
        workers = []
        worker_pids = []

        overlap_observed = False
        coordination_error = None
        last_blockers = None

        try:
            with transaction.atomic():
                # Hold this row until both requests reach a lock.
                type(gate).objects.select_for_update().get(
                    pk=gate.pk
                )

                for dispatcher, driver_id in zip(
                    self.dispatchers,
                    driver_ids,
                ):
                    worker = Thread(
                        target=self._dispatch_worker,
                        args=(
                            dispatcher.pk,
                            driver_id,
                            ready,
                            results,
                        ),
                        daemon=True,
                    )

                    worker.start()
                    workers.append(worker)

                deadline = monotonic() + 10

                for _ in workers:
                    remaining = deadline - monotonic()

                    if remaining <= 0:
                        raise TimeoutError(
                            "Workers did not become ready."
                        )

                    worker_pids.append(
                        ready.get(timeout=remaining)
                    )

                while monotonic() < deadline:
                    with connection.cursor() as cursor:
                        cursor.execute(
                            "SELECT pg_blocking_pids(%s), "
                            "pg_blocking_pids(%s)",
                            worker_pids,
                        )
                        last_blockers = cursor.fetchone()

                    if all(last_blockers):
                        overlap_observed = True
                        break

                    if any(
                        not worker.is_alive()
                        for worker in workers
                    ):
                        break

                    sleep(0.05)

            # Leaving atomic releases the coordination lock.

        except Exception:
            coordination_error = format_exc()

        finally:
            deadline = monotonic() + 30

            for worker in workers:
                worker.join(
                    timeout=max(
                        0,
                        deadline - monotonic(),
                    )
                )

            # Cancel only these test workers' SQL if needed.
            if any(
                worker.is_alive()
                for worker in workers
            ):
                with connection.cursor() as cursor:
                    for backend_pid in worker_pids:
                        cursor.execute(
                            "SELECT pg_cancel_backend(pid) "
                            "FROM pg_stat_activity "
                            "WHERE pid = %s "
                            "AND datname = current_database()",
                            [backend_pid],
                        )

                deadline = monotonic() + 5

                for worker in workers:
                    worker.join(
                        timeout=max(
                            0,
                            deadline - monotonic(),
                        )
                    )

        self.assertFalse(
            any(
                worker.is_alive()
                for worker in workers
            ),
            "A test worker did not finish after the SQL timeout.",
        )

        outcomes = []

        while True:
            try:
                outcomes.append(
                    results.get_nowait()
                )
            except Empty:
                break

        errors = [
            item["error"]
            for item in outcomes
            if item["error"]
        ]

        self.assertFalse(
            errors,
            "\n\n".join(errors),
        )

        self.assertIsNone(
            coordination_error,
            coordination_error,
        )

        self.assertEqual(
            len(outcomes),
            2,
            outcomes,
        )

        self.assertEqual(
            len(set(worker_pids)),
            2,
            worker_pids,
        )

        self.assertTrue(
            overlap_observed,
            (
                "Both requests did not overlap at a database lock. "
                f"Blockers: {last_blockers}; outcomes: {outcomes}"
            ),
        )

        return outcomes

    def _assert_one_winner(self, outcomes):
        active_statuses = [
            DispatchAssignment.Status.PENDING,
            DispatchAssignment.Status.ACCEPTED,
            DispatchAssignment.Status.EN_ROUTE,
        ]

        active_links = DispatchRequest.objects.filter(
            waiting_request=self.waiting_request,
            dispatch__status__in=active_statuses,
        )

        self.assertEqual(
            active_links.count(),
            1,
            (
                "The waiting group must belong to exactly "
                "one active taxi. "
                f"Responses: {outcomes}"
            ),
        )

        self.assertEqual(
            DispatchAssignment.objects.count(),
            1,
            outcomes,
        )

        self.assertEqual(
            sorted(
                item["status"]
                for item in outcomes
            ),
            [
                status.HTTP_201_CREATED,
                status.HTTP_400_BAD_REQUEST,
            ],
            outcomes,
        )

        assignment = DispatchAssignment.objects.get()

        self.assertEqual(
            assignment.status,
            DispatchAssignment.Status.PENDING,
        )

        self.assertEqual(
            assignment.passenger_count,
            6,
        )

        self.assertEqual(
            DispatchRequest.objects.count(),
            1,
        )

        for driver in self.drivers:
            availability = DriverAvailability.objects.get(
                driver=driver
            )

            self.assertEqual(
                availability.is_available,
                driver.pk != assignment.driver_id,
                (
                    "Incorrect availability for "
                    f"driver {driver.pk}."
                ),
            )

    def test_two_dispatchers_cannot_assign_the_same_driver_twice(self):
        gate = DriverAvailability.objects.get(
            driver=self.drivers[0]
        )

        outcomes = self._run_overlapping_dispatches(
            [
                self.drivers[0].pk,
                self.drivers[0].pk,
            ],
            gate,
        )

        self._assert_one_winner(outcomes)

    def test_two_drivers_cannot_receive_the_same_waiting_group(self):
        outcomes = self._run_overlapping_dispatches(
            [
                self.drivers[0].pk,
                self.drivers[1].pk,
            ],
            self.waiting_request,
        )

        self._assert_one_winner(outcomes)