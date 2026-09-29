from django.core.exceptions import ValidationError


def validate_phone_number(value):
    phone_number = str(value or "").strip()

    if (
        len(phone_number) != 10
        or not phone_number.isascii()
        or not phone_number.isdigit()
        or not phone_number.startswith("0")
    ):
        raise ValidationError(
            "Enter a 10-digit phone number starting with 0.",
            code="invalid_phone_number",
        )


class StrongPasswordValidator:
    message = (
        "Password must contain at least one uppercase letter, "
        "one lowercase letter, one number, and one special character."
    )

    def validate(self, password, user=None):
        has_uppercase = any(
            character.isupper()
            for character in password
        )

        has_lowercase = any(
            character.islower()
            for character in password
        )

        has_number = any(
            character.isdigit()
            for character in password
        )

        has_special = any(
            not character.isalnum()
            and not character.isspace()
            for character in password
        )

        if not all(
            (
                has_uppercase,
                has_lowercase,
                has_number,
                has_special,
            )
        ):
            raise ValidationError(
                self.message,
                code="password_missing_required_characters",
            )

    def get_help_text(self):
        return self.message