import secrets
import string

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from rest_framework import serializers


User = get_user_model()


def generate_temporary_password(length=12):
    special_characters = "!@#$%"

    characters = (
        string.ascii_letters
        + string.digits
        + special_characters
    )

    password_characters = [
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.digits),
        secrets.choice(special_characters),
    ]

    password_characters.extend(
        secrets.choice(characters)
        for _ in range(length - 4)
    )

    secrets.SystemRandom().shuffle(
        password_characters
    )

    return "".join(password_characters)


class PassengerRegistrationSerializer(
    serializers.ModelSerializer
):
    password = serializers.CharField(
        write_only=True,
        min_length=8,
        style={"input_type": "password"},
    )

    password_confirm = serializers.CharField(
        write_only=True,
        style={"input_type": "password"},
    )

    class Meta:
        model = User

        fields = (
            "username",
            "first_name",
            "last_name",
            "email",
            "phone_number",
            "password",
            "password_confirm",
        )

    def validate(self, attrs):
        if (
            attrs["password"]
            != attrs["password_confirm"]
        ):
            raise serializers.ValidationError(
                {
                    "password_confirm": (
                        "Passwords do not match."
                    )
                }
            )

        return attrs

    def create(self, validated_data):
        validated_data.pop(
            "password_confirm"
        )

        password = validated_data.pop(
            "password"
        )

        user = User.objects.create_user(
            password=password,
            role=User.Role.PASSENGER,
            **validated_data,
        )

        return user


class UserProfileSerializer(
    serializers.ModelSerializer
):
    role_display = serializers.CharField(
        source="get_role_display",
        read_only=True,
    )

    class Meta:
        model = User

        fields = (
            "id",
            "username",
            "first_name",
            "last_name",
            "email",
            "phone_number",
            "role",
            "role_display",
            "number_plate",
            "must_change_password",
        )

        read_only_fields = (
            "id",
            "username",
            "email",
            "role",
            "role_display",
            "number_plate",
            "must_change_password",
        )

class DriverManagementSerializer(
    serializers.ModelSerializer
):
    full_name = serializers.SerializerMethodField()

    class Meta:
        model = User

        fields = (
            "id",
            "username",
            "full_name",
            "email",
            "phone_number",
            "number_plate",
            "must_change_password",
        )

        read_only_fields = fields

    def get_full_name(self, obj):
        return obj.get_full_name().strip() or obj.username

class DriverRegistrationSerializer(
    serializers.ModelSerializer
):
    temporary_password = (
        serializers.SerializerMethodField()
    )

    number_plate = serializers.CharField(
        required=True,
        allow_blank=False,
        max_length=20,
    )

    class Meta:
        model = User

        fields = (
            "username",
            "first_name",
            "last_name",
            "email",
            "phone_number",
            "number_plate",
            "temporary_password",
        )

        read_only_fields = (
            "temporary_password",
        )

    def validate_number_plate(
        self,
        value,
    ):
        normalized_plate = " ".join(
            value.upper().split()
        )

        if not normalized_plate:
            raise serializers.ValidationError(
                "Number plate is required."
            )

        if User.objects.filter(
            number_plate__iexact=normalized_plate
        ).exists():
            raise serializers.ValidationError(
                (
                    "A driver with this number "
                    "plate already exists."
                )
            )

        return normalized_plate

    def create(self, validated_data):
        temporary_password = (
            generate_temporary_password()
        )

        user = User.objects.create_user(
            password=temporary_password,
            role=User.Role.DRIVER,
            must_change_password=True,
            **validated_data,
        )

        # Stored only temporarily in memory so it can
        # be returned once in the creation response.
        user._temporary_password = (
            temporary_password
        )

        return user

    def get_temporary_password(
        self,
        obj,
    ):
        return getattr(
            obj,
            "_temporary_password",
            None,
        )


class DriverPasswordChangeSerializer(
    serializers.Serializer
):
    current_password = serializers.CharField(
        write_only=True,
    )

    new_password = serializers.CharField(
        write_only=True,
        min_length=8,
    )

    new_password_confirm = serializers.CharField(
        write_only=True,
    )

    def validate_current_password(
        self,
        value,
    ):
        user = self.context[
            "request"
        ].user

        if not user.check_password(value):
            raise serializers.ValidationError(
                "Current password is incorrect."
            )

        return value

    def validate(self, attrs):
        if (
            attrs["new_password"]
            != attrs["new_password_confirm"]
        ):
            raise serializers.ValidationError(
                {
                    "new_password_confirm": (
                        "Passwords do not match."
                    )
                }
            )

        user = self.context[
            "request"
        ].user

        if user.check_password(
            attrs["new_password"]
        ):
            raise serializers.ValidationError(
                {
                    "new_password": (
                        "Your new password must "
                        "be different from the "
                        "temporary password."
                    )
                }
            )

        validate_password(
            attrs["new_password"],
            user=user,
        )

        return attrs

    def save(self):
        user = self.context[
            "request"
        ].user

        user.set_password(
            self.validated_data[
                "new_password"
            ]
        )

        user.must_change_password = False

        user.save(
            update_fields=[
                "password",
                "must_change_password",
            ]
        )

        return user


class PasswordResetConfirmSerializer(
    serializers.Serializer
):
    uid = serializers.CharField(
        write_only=True,
    )

    token = serializers.CharField(
        write_only=True,
    )

    new_password = serializers.CharField(
        write_only=True,
        min_length=8,
    )

    new_password_confirm = serializers.CharField(
        write_only=True,
    )

    def validate(self, attrs):
        if (
            attrs["new_password"]
            != attrs["new_password_confirm"]
        ):
            raise serializers.ValidationError(
                {
                    "new_password_confirm": (
                        "Passwords do not match."
                    )
                }
            )

        try:
            user_id = force_str(
                urlsafe_base64_decode(
                    attrs["uid"]
                )
            )

            user = User.objects.get(
                pk=user_id
            )
        except (
            TypeError,
            ValueError,
            OverflowError,
            User.DoesNotExist,
        ):
            raise serializers.ValidationError(
                {
                    "detail": (
                        "This password reset link "
                        "is invalid or has expired."
                    )
                }
            )

        if not default_token_generator.check_token(
            user,
            attrs["token"],
        ):
            raise serializers.ValidationError(
                {
                    "detail": (
                        "This password reset link "
                        "is invalid or has expired."
                    )
                }
            )

        validate_password(
            attrs["new_password"],
            user=user,
        )

        attrs["user"] = user

        return attrs

    def save(self):
        user = self.validated_data["user"]

        user.set_password(
            self.validated_data[
                "new_password"
            ]
        )

        update_fields = [
            "password",
        ]

        if (
            user.role == User.Role.DRIVER
            and user.must_change_password
        ):
            user.must_change_password = False

            update_fields.append(
                "must_change_password"
            )

        user.save(
            update_fields=update_fields
        )

        return user

class PasswordResetRequestSerializer(
    serializers.Serializer
):
    email = serializers.EmailField()

    def validate_email(self, value):
        return value.strip().lower()

class AccountPasswordChangeSerializer(
    serializers.Serializer
):
    current_password = serializers.CharField(
        write_only=True,
    )

    new_password = serializers.CharField(
        write_only=True,
        min_length=8,
    )

    new_password_confirm = serializers.CharField(
        write_only=True,
    )

    def validate_current_password(
        self,
        value,
    ):
        user = self.context[
            "request"
        ].user

        if not user.check_password(value):
            raise serializers.ValidationError(
                "Current password is incorrect."
            )

        return value

    def validate(self, attrs):
        if (
            attrs["new_password"]
            != attrs["new_password_confirm"]
        ):
            raise serializers.ValidationError(
                {
                    "new_password_confirm": (
                        "Passwords do not match."
                    )
                }
            )

        user = self.context[
            "request"
        ].user

        if user.check_password(
            attrs["new_password"]
        ):
            raise serializers.ValidationError(
                {
                    "new_password": (
                        "Your new password must "
                        "be different from your "
                        "current password."
                    )
                }
            )

        validate_password(
            attrs["new_password"],
            user=user,
        )

        return attrs

    def save(self):
        user = self.context[
            "request"
        ].user

        user.set_password(
            self.validated_data[
                "new_password"
            ]
        )

        user.save(
            update_fields=[
                "password",
            ]
        )

        return user