from django.contrib.auth import get_user_model
from django.urls import reverse

from rest_framework import status
from rest_framework.test import APITestCase
from unittest.mock import patch

from django.test import override_settings
from django.contrib.auth.tokens import (
    default_token_generator,
)
from django.core import mail
from django.utils.encoding import force_bytes
from django.utils.http import (
    urlsafe_base64_encode,
)
from .serializers import (
    PassengerRegistrationSerializer,
)
User = get_user_model()


class DriverRegistrationTests(APITestCase):
    def setUp(self):
        self.dispatcher = User.objects.create_user(
            username="dispatcher_test@example.com",
            email="dispatcher_test@example.com",
            password="StrongPass123!",
            role=User.Role.DISPATCHER,
        )

        self.passenger = User.objects.create_user(
            username="passenger_test@example.com",
            email="passenger_test@example.com",
            password="StrongPass123!",
            role=User.Role.PASSENGER,
        )

        self.driver_email = (
            "driver_test@example.com"
        )

        self.url = reverse(
            "driver-register"
        )

        self.valid_data = {
            "first_name": "Thabo",
            "last_name": "Mokoena",
            "email": self.driver_email,
            "phone_number": "0712345678",
            "number_plate": "ABC 123 L",
        }

    def create_driver(self):
        self.client.force_authenticate(
            user=self.dispatcher
        )

        return self.client.post(
            self.url,
            self.valid_data,
            format="json",
        )

    def get_driver(self):
        return User.objects.get(
            email=self.driver_email
        )

    def test_dispatcher_can_create_driver(self):
        response = self.create_driver()

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )

        driver = self.get_driver()

        self.assertEqual(
            driver.username,
            self.driver_email,
        )

    def test_created_user_role_is_driver(self):
        self.create_driver()

        driver = self.get_driver()

        self.assertEqual(
            driver.role,
            User.Role.DRIVER,
        )

    def test_created_driver_must_change_password(
        self,
    ):
        self.create_driver()

        driver = self.get_driver()

        self.assertTrue(
            driver.must_change_password
        )

    def test_temporary_password_is_generated(self):
        response = self.create_driver()

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )

        self.assertIn(
            "temporary_password",
            response.data,
        )

        self.assertTrue(
            response.data[
                "temporary_password"
            ]
        )

    def test_generated_temporary_password_is_valid(
        self,
    ):
        response = self.create_driver()

        temporary_password = (
            response.data[
                "temporary_password"
            ]
        )

        driver = self.get_driver()

        self.assertTrue(
            driver.check_password(
                temporary_password
            )
        )

    def test_temporary_password_not_exposed_in_profile(
        self,
    ):
        response = self.create_driver()

        temporary_password = (
            response.data[
                "temporary_password"
            ]
        )

        driver = self.get_driver()

        self.client.force_authenticate(
            user=driver
        )

        profile_response = self.client.get(
            reverse(
                "current-user-profile"
            )
        )

        self.assertEqual(
            profile_response.status_code,
            status.HTTP_200_OK,
        )

        self.assertNotIn(
            "temporary_password",
            profile_response.data,
        )

        self.assertNotIn(
            temporary_password,
            str(profile_response.data),
        )

    def test_driver_number_plate_is_saved(self):
        self.client.force_authenticate(
            user=self.dispatcher
        )

        data = self.valid_data.copy()

        data["number_plate"] = (
            "abc   123 l"
        )

        response = self.client.post(
            self.url,
            data,
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )

        driver = self.get_driver()

        self.assertEqual(
            driver.number_plate,
            "ABC 123 L",
        )

    def test_number_plate_is_required(self):
        self.client.force_authenticate(
            user=self.dispatcher
        )

        data = self.valid_data.copy()
        data.pop("number_plate")

        response = self.client.post(
            self.url,
            data,
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

        self.assertIn(
            "number_plate",
            response.data,
        )

    def test_duplicate_number_plate_is_rejected(
        self,
    ):
        existing_email = (
            "existing_driver@example.com"
        )

        User.objects.create_user(
            username=existing_email,
            email=existing_email,
            password="StrongPass123!",
            role=User.Role.DRIVER,
            number_plate="ABC 123 L",
        )

        self.client.force_authenticate(
            user=self.dispatcher
        )

        data = self.valid_data.copy()

        data["number_plate"] = (
            "abc 123 l"
        )

        response = self.client.post(
            self.url,
            data,
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

        self.assertIn(
            "number_plate",
            response.data,
        )

    def test_passenger_cannot_create_driver(self):
        self.client.force_authenticate(
            user=self.passenger
        )

        response = self.client.post(
            self.url,
            self.valid_data,
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_unauthenticated_user_cannot_create_driver(
        self,
    ):
        response = self.client.post(
            self.url,
            self.valid_data,
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

class DriverPasswordChangeTests(APITestCase):
    def setUp(self):
        self.driver = User.objects.create_user(
            username="temp_driver",
            email="temp_driver@example.com",
            password="TempPass123!",
            role=User.Role.DRIVER,
            number_plate="TMP 123 LP",
            must_change_password=True,
        )

        self.passenger = User.objects.create_user(
            username="password_passenger",
            email="password_passenger@example.com",
            password="StrongPass123!",
            role=User.Role.PASSENGER,
        )

        self.url = reverse(
            "driver-change-password"
        )

        self.client.force_authenticate(
            user=self.driver
        )

    def test_driver_can_change_temporary_password(self):
        response = self.client.post(
            self.url,
            {
                "current_password": "TempPass123!",
                "new_password": "DriverOwnPass456!",
                "new_password_confirm": "DriverOwnPass456!",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.driver.refresh_from_db()

        self.assertFalse(
            self.driver.must_change_password
        )

        self.assertTrue(
            self.driver.check_password(
                "DriverOwnPass456!"
            )
        )

    def test_old_temporary_password_stops_working(self):
        self.client.post(
            self.url,
            {
                "current_password": "TempPass123!",
                "new_password": "DriverOwnPass456!",
                "new_password_confirm": "DriverOwnPass456!",
            },
            format="json",
        )

        self.driver.refresh_from_db()

        self.assertFalse(
            self.driver.check_password(
                "TempPass123!"
            )
        )

    def test_wrong_current_password_is_rejected(self):
        response = self.client.post(
            self.url,
            {
                "current_password": "WrongPass123!",
                "new_password": "DriverOwnPass456!",
                "new_password_confirm": "DriverOwnPass456!",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

        self.driver.refresh_from_db()

        self.assertTrue(
            self.driver.must_change_password
        )

    def test_new_passwords_must_match(self):
        response = self.client.post(
            self.url,
            {
                "current_password": "TempPass123!",
                "new_password": "DriverOwnPass456!",
                "new_password_confirm": "DifferentPass789!",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_new_password_cannot_match_temporary_password(self):
        response = self.client.post(
            self.url,
            {
                "current_password": "TempPass123!",
                "new_password": "TempPass123!",
                "new_password_confirm": "TempPass123!",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_passenger_cannot_use_driver_password_change_endpoint(self):
        self.client.force_authenticate(
            user=self.passenger
        )

        response = self.client.post(
            self.url,
            {
                "current_password": "StrongPass123!",
                "new_password": "PassengerNewPass456!",
                "new_password_confirm": "PassengerNewPass456!",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

class DriverTemporaryPasswordAccessTests(APITestCase):
    def setUp(self):
        self.driver = User.objects.create_user(
            username="locked_driver",
            email="locked_driver@example.com",
            password="TempPass123!",
            role=User.Role.DRIVER,
            number_plate="LOCK 123 LP",
            must_change_password=True,
        )

        self.client.force_authenticate(
            user=self.driver
        )

    def test_temporary_password_driver_cannot_access_availability(self):
        response = self.client.get(
            "/api/transport/drivers/availability/"
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_temporary_password_driver_cannot_access_dispatches(self):
        response = self.client.get(
            "/api/transport/dispatches/"
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_temporary_password_driver_cannot_access_routes(self):
        response = self.client.get(
            "/api/transport/routes/"
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_driver_can_access_transport_after_password_change(self):
        password_response = self.client.post(
            reverse("driver-change-password"),
            {
                "current_password": "TempPass123!",
                "new_password": "DriverOwnPass456!",
                "new_password_confirm": "DriverOwnPass456!",
            },
            format="json",
        )

        self.assertEqual(
            password_response.status_code,
            status.HTTP_200_OK,
        )

        self.driver.refresh_from_db()

        self.assertFalse(
            self.driver.must_change_password
        )

        availability_response = self.client.get(
            "/api/transport/drivers/availability/"
        )

        dispatch_response = self.client.get(
            "/api/transport/dispatches/"
        )

        routes_response = self.client.get(
            "/api/transport/routes/"
        )

        self.assertEqual(
            availability_response.status_code,
            status.HTTP_200_OK,
        )

        self.assertEqual(
            dispatch_response.status_code,
            status.HTTP_200_OK,
        )

        self.assertEqual(
            routes_response.status_code,
            status.HTTP_200_OK,
        )

class DriverTemporaryPasswordResetTests(
    APITestCase
):
    def setUp(self):
        self.dispatcher = User.objects.create_user(
            username="dispatcher_reset",
            email="dispatcher_reset@example.com",
            password="DispatcherPass123!",
            role=User.Role.DISPATCHER,
        )

        self.passenger = User.objects.create_user(
            username="passenger_reset",
            email="passenger_reset@example.com",
            password="PassengerPass123!",
            role=User.Role.PASSENGER,
        )

        self.old_temporary_password = (
            "OldTempPass123!"
        )

        self.driver = User.objects.create_user(
            username="driver_reset",
            email="driver_reset@example.com",
            password=self.old_temporary_password,
            role=User.Role.DRIVER,
            number_plate="RESET 123",
            must_change_password=True,
        )

        self.url = reverse(
            "driver-reset-temporary-password",
            kwargs={
                "pk": self.driver.pk,
            },
        )

    def test_dispatcher_can_reset_temporary_password(
        self
    ):
        self.client.force_authenticate(
            user=self.dispatcher
        )

        response = self.client.post(
            self.url,
            {},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.assertIn(
            "temporary_password",
            response.data,
        )

    def test_old_temporary_password_stops_working(
        self
    ):
        self.client.force_authenticate(
            user=self.dispatcher
        )

        response = self.client.post(
            self.url,
            {},
            format="json",
        )

        self.driver.refresh_from_db()

        self.assertFalse(
            self.driver.check_password(
                self.old_temporary_password
            )
        )

        self.assertTrue(
            self.driver.check_password(
                response.data[
                    "temporary_password"
                ]
            )
        )

    def test_reset_keeps_driver_in_password_setup(
        self
    ):
        self.client.force_authenticate(
            user=self.dispatcher
        )

        self.client.post(
            self.url,
            {},
            format="json",
        )

        self.driver.refresh_from_db()

        self.assertTrue(
            self.driver.must_change_password
        )

    def test_passenger_cannot_reset_driver_password(
        self
    ):
        self.client.force_authenticate(
            user=self.passenger
        )

        response = self.client.post(
            self.url,
            {},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_dispatcher_cannot_reset_permanent_password(
        self
    ):
        permanent_password = (
            "PermanentPass123!"
        )

        self.driver.set_password(
            permanent_password
        )

        self.driver.must_change_password = False

        self.driver.save(
            update_fields=[
                "password",
                "must_change_password",
            ]
        )

        self.client.force_authenticate(
            user=self.dispatcher
        )

        response = self.client.post(
            self.url,
            {},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

        self.driver.refresh_from_db()

        self.assertTrue(
            self.driver.check_password(
                permanent_password
            )
        )

        self.assertFalse(
            self.driver.must_change_password
        )

    def test_unknown_driver_returns_404(self):
        self.client.force_authenticate(
            user=self.dispatcher
        )

        url = reverse(
            "driver-reset-temporary-password",
            kwargs={
                "pk": 999999,
            },
        )

        response = self.client.post(
            url,
            {},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND,
        )

class DriverManagementListTests(
    APITestCase
):
    def setUp(self):
        self.dispatcher = User.objects.create_user(
            username="dispatcher_manage",
            email="dispatcher_manage@example.com",
            password="DispatcherPass123!",
            role=User.Role.DISPATCHER,
        )

        self.passenger = User.objects.create_user(
            username="passenger_manage",
            email="passenger_manage@example.com",
            password="PassengerPass123!",
            role=User.Role.PASSENGER,
        )

        self.driver_pending = User.objects.create_user(
            username="driver_pending",
            first_name="Thabo",
            last_name="Mokoena",
            email="driver_pending@example.com",
            password="TempPass123!",
            role=User.Role.DRIVER,
            number_plate="ABC 123 L",
            must_change_password=True,
        )

        self.driver_complete = User.objects.create_user(
            username="driver_complete",
            first_name="Sipho",
            last_name="Nkosi",
            email="driver_complete@example.com",
            password="PermanentPass123!",
            role=User.Role.DRIVER,
            number_plate="XYZ 456 L",
            must_change_password=False,
        )

        self.url = reverse(
            "driver-management-list"
        )

    def test_dispatcher_can_list_drivers(self):
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

        self.assertEqual(
            len(response.data),
            2,
        )

    def test_list_contains_password_setup_status(
        self
    ):
        self.client.force_authenticate(
            user=self.dispatcher
        )

        response = self.client.get(
            self.url
        )

        drivers = {
            driver["username"]: driver
            for driver in response.data
        }

        self.assertTrue(
            drivers[
                "driver_pending"
            ]["must_change_password"]
        )

        self.assertFalse(
            drivers[
                "driver_complete"
            ]["must_change_password"]
        )

    def test_passenger_cannot_list_drivers(self):
        self.client.force_authenticate(
            user=self.passenger
        )

        response = self.client.get(
            self.url
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_unauthenticated_user_cannot_list_drivers(
        self
    ):
        response = self.client.get(
            self.url
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

class PasswordResetTests(APITestCase):
    def setUp(self):
        self.request_url = reverse(
            "password-reset"
        )

        self.confirm_url = reverse(
            "password-reset-confirm"
        )

        self.passenger = User.objects.create_user(
            username="reset_passenger",
            email="reset_passenger@example.com",
            password="OldPassengerPass123!",
            role=User.Role.PASSENGER,
        )

        self.driver = User.objects.create_user(
            username="reset_driver",
            email="reset_driver@example.com",
            password="OldDriverPass123!",
            role=User.Role.DRIVER,
            number_plate="RESET 456",
            must_change_password=False,
        )

        self.dispatcher = User.objects.create_user(
            username="reset_dispatcher",
            email="reset_dispatcher@example.com",
            password="OldDispatcherPass123!",
            role=User.Role.DISPATCHER,
        )

    def reset_data(
        self,
        user,
        new_password,
    ):
        uid = urlsafe_base64_encode(
            force_bytes(user.pk)
        )

        token = (
            default_token_generator
            .make_token(user)
        )

        return {
            "uid": uid,
            "token": token,
            "new_password": new_password,
            "new_password_confirm":
                new_password,
        }

    def test_existing_email_returns_generic_response(
        self
    ):
        response = self.client.post(
            self.request_url,
            {
                "email":
                    self.passenger.email
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.assertEqual(
            response.data["detail"],
            (
                "If an account exists for "
                "this email, password reset "
                "instructions have been sent."
            ),
        )

        self.assertEqual(
            len(mail.outbox),
            1,
        )

    def test_unknown_email_returns_same_response(
        self
    ):
        response = self.client.post(
            self.request_url,
            {
                "email":
                    "unknown@example.com"
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.assertEqual(
            response.data["detail"],
            (
                "If an account exists for "
                "this email, password reset "
                "instructions have been sent."
            ),
        )

        self.assertEqual(
            len(mail.outbox),
            0,
        )

    def test_passenger_can_reset_password(self):
        new_password = (
            "NewPassengerPass456!"
        )

        response = self.client.post(
            self.confirm_url,
            self.reset_data(
                self.passenger,
                new_password,
            ),
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.passenger.refresh_from_db()

        self.assertTrue(
            self.passenger.check_password(
                new_password
            )
        )

        self.assertFalse(
            self.passenger.check_password(
                "OldPassengerPass123!"
            )
        )

    def test_driver_can_reset_password(self):
        new_password = (
            "NewDriverPass456!"
        )

        response = self.client.post(
            self.confirm_url,
            self.reset_data(
                self.driver,
                new_password,
            ),
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.driver.refresh_from_db()

        self.assertTrue(
            self.driver.check_password(
                new_password
            )
        )

        self.assertFalse(
            self.driver.check_password(
                "OldDriverPass123!"
            )
        )

    def test_dispatcher_can_reset_password(self):
        new_password = (
            "NewDispatcherPass456!"
        )

        response = self.client.post(
            self.confirm_url,
            self.reset_data(
                self.dispatcher,
                new_password,
            ),
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.dispatcher.refresh_from_db()

        self.assertTrue(
            self.dispatcher.check_password(
                new_password
            )
        )

        self.assertFalse(
            self.dispatcher.check_password(
                "OldDispatcherPass123!"
            )
        )

    def test_driver_reset_clears_temporary_password_flag(
        self
    ):
        self.driver.must_change_password = True

        self.driver.save(
            update_fields=[
                "must_change_password",
            ]
        )

        response = self.client.post(
            self.confirm_url,
            self.reset_data(
                self.driver,
                "RecoveredDriverPass456!",
            ),
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.driver.refresh_from_db()

        self.assertFalse(
            self.driver.must_change_password
        )

    def test_invalid_token_is_rejected(self):
        uid = urlsafe_base64_encode(
            force_bytes(
                self.passenger.pk
            )
        )

        response = self.client.post(
            self.confirm_url,
            {
                "uid": uid,
                "token": "invalid-token",
                "new_password":
                    "NewPassengerPass456!",
                "new_password_confirm":
                    "NewPassengerPass456!",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_reset_token_cannot_be_reused(self):
        data = self.reset_data(
            self.passenger,
            "NewPassengerPass456!",
        )

        first_response = self.client.post(
            self.confirm_url,
            data,
            format="json",
        )

        second_response = self.client.post(
            self.confirm_url,
            data,
            format="json",
        )

        self.assertEqual(
            first_response.status_code,
            status.HTTP_200_OK,
        )

        self.assertEqual(
            second_response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_new_passwords_must_match(self):
        data = self.reset_data(
            self.passenger,
            "NewPassengerPass456!",
        )

        data["new_password_confirm"] = (
            "DifferentPass456!"
        )

        response = self.client.post(
            self.confirm_url,
            data,
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

class AccountPasswordChangeTests(
    APITestCase
):
    def setUp(self):
        self.url = reverse(
            "account-change-password"
        )

        self.passenger = User.objects.create_user(
            username="change_passenger",
            email="change_passenger@example.com",
            password="OldPassengerPass123!",
            role=User.Role.PASSENGER,
        )

        self.driver = User.objects.create_user(
            username="change_driver",
            email="change_driver@example.com",
            password="OldDriverPass123!",
            role=User.Role.DRIVER,
            number_plate="CHANGE 123",
            must_change_password=False,
        )

        self.dispatcher = User.objects.create_user(
            username="change_dispatcher",
            email="change_dispatcher@example.com",
            password="OldDispatcherPass123!",
            role=User.Role.DISPATCHER,
        )

    def change_password(
        self,
        user,
        current_password,
        new_password,
    ):
        self.client.force_authenticate(
            user=user
        )

        return self.client.post(
            self.url,
            {
                "current_password":
                    current_password,
                "new_password":
                    new_password,
                "new_password_confirm":
                    new_password,
            },
            format="json",
        )

    def test_passenger_can_change_password(self):
        response = self.change_password(
            self.passenger,
            "OldPassengerPass123!",
            "NewPassengerPass456!",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.passenger.refresh_from_db()

        self.assertTrue(
            self.passenger.check_password(
                "NewPassengerPass456!"
            )
        )

    def test_driver_can_change_password(self):
        response = self.change_password(
            self.driver,
            "OldDriverPass123!",
            "NewDriverPass456!",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.driver.refresh_from_db()

        self.assertTrue(
            self.driver.check_password(
                "NewDriverPass456!"
            )
        )

    def test_dispatcher_can_change_password(self):
        response = self.change_password(
            self.dispatcher,
            "OldDispatcherPass123!",
            "NewDispatcherPass456!",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.dispatcher.refresh_from_db()

        self.assertTrue(
            self.dispatcher.check_password(
                "NewDispatcherPass456!"
            )
        )

    def test_old_password_stops_working(self):
        self.change_password(
            self.passenger,
            "OldPassengerPass123!",
            "NewPassengerPass456!",
        )

        self.passenger.refresh_from_db()

        self.assertFalse(
            self.passenger.check_password(
                "OldPassengerPass123!"
            )
        )

    def test_wrong_current_password_is_rejected(self):
        response = self.change_password(
            self.passenger,
            "WrongPassword123!",
            "NewPassengerPass456!",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_new_password_cannot_match_current_password(
        self
    ):
        response = self.change_password(
            self.passenger,
            "OldPassengerPass123!",
            "OldPassengerPass123!",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_temporary_password_driver_is_blocked(
        self
    ):
        self.driver.must_change_password = True

        self.driver.save(
            update_fields=[
                "must_change_password"
            ]
        )

        response = self.change_password(
            self.driver,
            "OldDriverPass123!",
            "NewDriverPass456!",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_unauthenticated_user_is_blocked(self):
        self.client.force_authenticate(
            user=None
        )

        response = self.client.post(
            self.url,
            {
                "current_password":
                    "OldPassengerPass123!",
                "new_password":
                    "NewPassengerPass456!",
                "new_password_confirm":
                    "NewPassengerPass456!",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

class PassengerRegistrationValidationTests(
    APITestCase
):
    def valid_data(self):
        return {
            "username": "new_passenger",
            "first_name": "Test",
            "last_name": "Passenger",
            "email": "passenger@example.com",
            "phone_number": "0712345678",
            "password": "StrongPass123!",
            "password_confirm": "StrongPass123!",
        }

    def test_valid_registration_data_is_accepted(
        self
    ):
        serializer = (
            PassengerRegistrationSerializer(
                data=self.valid_data()
            )
        )

        self.assertTrue(
            serializer.is_valid(),
            serializer.errors,
        )

    def test_phone_number_must_start_with_zero(
        self
    ):
        data = self.valid_data()
        data["phone_number"] = "7112345678"

        serializer = (
            PassengerRegistrationSerializer(
                data=data
            )
        )

        self.assertFalse(
            serializer.is_valid()
        )

        self.assertIn(
            "phone_number",
            serializer.errors,
        )

    def test_phone_number_must_have_ten_digits(
        self
    ):
        for phone_number in (
            "071234567",
            "07123456789",
            "07123abc78",
        ):
            with self.subTest(
                phone_number=phone_number
            ):
                data = self.valid_data()

                data["phone_number"] = (
                    phone_number
                )

                serializer = (
                    PassengerRegistrationSerializer(
                        data=data
                    )
                )

                self.assertFalse(
                    serializer.is_valid()
                )

                self.assertIn(
                    "phone_number",
                    serializer.errors,
                )

    def test_invalid_email_is_rejected(self):
        data = self.valid_data()
        data["email"] = "not-an-email"

        serializer = (
            PassengerRegistrationSerializer(
                data=data
            )
        )

        self.assertFalse(
            serializer.is_valid()
        )

        self.assertIn(
            "email",
            serializer.errors,
        )

    def test_duplicate_email_is_case_insensitive(
        self
    ):
        User.objects.create_user(
            username="existing_passenger",
            email="Existing@Example.com",
            password="StrongPass123!",
            role=User.Role.PASSENGER,
        )

        data = self.valid_data()
        data["email"] = "existing@example.com"

        serializer = (
            PassengerRegistrationSerializer(
                data=data
            )
        )

        self.assertFalse(
            serializer.is_valid()
        )

        self.assertIn(
            "email",
            serializer.errors,
        )

    def test_password_complexity_is_enforced(
        self
    ):
        weak_passwords = (
            "lowercase123!",
            "UPPERCASE123!",
            "NoNumberHere!",
            "NoSpecial123",
        )

        for password in weak_passwords:
            with self.subTest(
                password=password
            ):
                data = self.valid_data()
                data["password"] = password
                data[
                    "password_confirm"
                ] = password

                serializer = (
                    PassengerRegistrationSerializer(
                        data=data
                    )
                )

                self.assertFalse(
                    serializer.is_valid()
                )

                self.assertIn(
                    "password",
                    serializer.errors,
                )
@override_settings(
    EMAIL_BACKEND=(
        "django.core.mail.backends."
        "locmem.EmailBackend"
    ),
    FRONTEND_URL="http://frontend.test",
)
@override_settings(
    EMAIL_BACKEND=(
        "django.core.mail.backends."
        "locmem.EmailBackend"
    ),
    FRONTEND_URL="http://frontend.test",
)
class EmailVerificationFlowTests(
    APITestCase
):
    def setUp(self):
        self.passenger_email = (
            "emailtest@example.com"
        )

        self.driver_email = (
            "driver@example.com"
        )

        self.registration_url = reverse(
            "passenger-register"
        )

        self.login_url = reverse(
            "token-obtain-pair"
        )

        self.resend_url = reverse(
            "email-verification-resend"
        )

        self.registration_data = {
            "first_name": "Email",
            "last_name": "Tester",
            "email": self.passenger_email,
            "phone_number": "0712345678",
            "password": "StrongPass123!",
            "password_confirm": (
                "StrongPass123!"
            ),
        }

    def register_passenger(self):
        return self.client.post(
            self.registration_url,
            self.registration_data,
            format="json",
        )

    def get_passenger(self):
        return User.objects.get(
            email=self.passenger_email
        )

    def create_driver(self):
        dispatcher_email = (
            "dispatcher@example.com"
        )

        dispatcher = (
            User.objects.create_user(
                username=dispatcher_email,
                email=dispatcher_email,
                password="StrongPass123!",
                role=User.Role.DISPATCHER,
                email_verified=True,
            )
        )

        self.client.force_authenticate(
            user=dispatcher
        )

        return self.client.post(
            reverse("driver-register"),
            {
                "first_name": "Driver",
                "last_name": "Tester",
                "email": self.driver_email,
                "phone_number": (
                    "0723456789"
                ),
                "number_plate": "EMAIL 01",
            },
            format="json",
        )

    def test_registration_creates_unverified_user_and_sends_email(
        self,
    ):
        response = (
            self.register_passenger()
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )

        user = self.get_passenger()

        self.assertEqual(
            user.username,
            self.passenger_email,
        )

        self.assertFalse(
            user.email_verified
        )

        self.assertTrue(
            response.data["email_sent"]
        )

        self.assertEqual(
            len(mail.outbox),
            1,
        )

        self.assertIn(
            reverse("email-verify"),
            mail.outbox[0].body,
        )

    def test_unverified_user_cannot_login(
        self,
    ):
        self.register_passenger()

        response = self.client.post(
            self.login_url,
            {
                "username": (
                    self.passenger_email
                ),
                "password": (
                    "StrongPass123!"
                ),
            },
            format="json",
        )

        self.assertIn(
            response.status_code,
            (
                status.HTTP_400_BAD_REQUEST,
                status.HTTP_401_UNAUTHORIZED,
            ),
        )

        self.assertNotIn(
            "access",
            response.data,
        )

    def test_valid_link_verifies_user_and_allows_login(
        self,
    ):
        self.register_passenger()

        user = self.get_passenger()

        uid = urlsafe_base64_encode(
            force_bytes(user.pk)
        )

        token = (
            default_token_generator
            .make_token(user)
        )

        verification_url = (
            f"{reverse('email-verify')}"
            f"?uid={uid}&token={token}"
        )

        response = self.client.get(
            verification_url
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_302_FOUND,
        )

        self.assertEqual(
            response["Location"],
            (
                "http://frontend.test"
                "/login?verification=success"
            ),
        )

        user.refresh_from_db()

        self.assertTrue(
            user.email_verified
        )

        login_response = (
            self.client.post(
                self.login_url,
                {
                    "username": user.email,
                    "password": (
                        "StrongPass123!"
                    ),
                },
                format="json",
            )
        )

        self.assertEqual(
            login_response.status_code,
            status.HTTP_200_OK,
        )

        self.assertIn(
            "access",
            login_response.data,
        )

    def test_invalid_link_does_not_verify_user(
        self,
    ):
        self.register_passenger()

        user = self.get_passenger()

        uid = urlsafe_base64_encode(
            force_bytes(user.pk)
        )

        response = self.client.get(
            (
                f"{reverse('email-verify')}"
                f"?uid={uid}"
                "&token=invalid-token"
            )
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_302_FOUND,
        )

        self.assertEqual(
            response["Location"],
            (
                "http://frontend.test"
                "/login?verification=invalid"
            ),
        )

        user.refresh_from_db()

        self.assertFalse(
            user.email_verified
        )

    def test_resend_sends_email_without_revealing_accounts(
        self,
    ):
        self.register_passenger()
        mail.outbox.clear()

        existing_response = (
            self.client.post(
                self.resend_url,
                {
                    "email": (
                        self.passenger_email
                    ),
                },
                format="json",
            )
        )

        self.assertEqual(
            existing_response.status_code,
            status.HTTP_200_OK,
        )

        self.assertEqual(
            len(mail.outbox),
            1,
        )

        mail.outbox.clear()

        unknown_response = (
            self.client.post(
                self.resend_url,
                {
                    "email": (
                        "unknown@example.com"
                    ),
                },
                format="json",
            )
        )

        self.assertEqual(
            unknown_response.status_code,
            status.HTTP_200_OK,
        )

        self.assertEqual(
            len(mail.outbox),
            0,
        )

        self.assertEqual(
            existing_response.data[
                "detail"
            ],
            unknown_response.data[
                "detail"
            ],
        )

    def test_driver_receives_temporary_password_email(
        self,
    ):
        response = self.create_driver()

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )

        driver = User.objects.get(
            email=self.driver_email
        )

        self.assertEqual(
            driver.username,
            self.driver_email,
        )

        self.assertFalse(
            driver.email_verified
        )

        temporary_password = (
            response.data[
                "temporary_password"
            ]
        )

        self.assertTrue(
            response.data["email_sent"]
        )

        self.assertEqual(
            len(mail.outbox),
            1,
        )

        self.assertIn(
            driver.email,
            mail.outbox[0].body,
        )

        self.assertIn(
            temporary_password,
            mail.outbox[0].body,
        )

        self.assertIn(
            reverse("email-verify"),
            mail.outbox[0].body,
        )

    def test_regenerated_driver_password_is_emailed(
        self,
    ):
        create_response = (
            self.create_driver()
        )

        driver = User.objects.get(
            email=self.driver_email
        )

        old_password = (
            create_response.data[
                "temporary_password"
            ]
        )

        mail.outbox.clear()

        response = self.client.post(
            reverse(
                (
                    "driver-reset-"
                    "temporary-password"
                ),
                kwargs={"pk": driver.pk},
            ),
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        new_password = (
            response.data[
                "temporary_password"
            ]
        )

        self.assertNotEqual(
            old_password,
            new_password,
        )

        self.assertTrue(
            response.data["email_sent"]
        )

        self.assertEqual(
            len(mail.outbox),
            1,
        )

        self.assertIn(
            new_password,
            mail.outbox[0].body,
        )

        driver.refresh_from_db()

        self.assertTrue(
            driver.check_password(
                new_password
            )
        )

    @patch(
        (
            "accounts.views."
            "send_verification_email"
        ),
        return_value=False,
    )
    def test_email_failure_does_not_delete_registration(
        self,
        mocked_email,
    ):
        response = (
            self.register_passenger()
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )

        self.assertFalse(
            response.data["email_sent"]
        )

        self.assertTrue(
            User.objects.filter(
                email=self.passenger_email,
                email_verified=False,
            ).exists()
        )

        mocked_email.assert_called_once()