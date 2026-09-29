from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    class Role(models.TextChoices):
        PASSENGER = "PASSENGER", "Passenger"
        DRIVER = "DRIVER", "Driver"
        DISPATCHER = "DISPATCHER", "Dispatcher"

    email = models.EmailField(unique=True)
    email_verified = models.BooleanField(
        default=True,
    )

    phone_number = models.CharField(
        max_length=20,
        blank=True,
    )

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.PASSENGER,
    )

    number_plate = models.CharField(
        max_length=20,
        unique=True,
        null=True,
        blank=True,
    )

    must_change_password = models.BooleanField(
    default=False,
    )

    def save(self, *args, **kwargs):
        if self.number_plate:
            self.number_plate = " ".join(
                self.number_plate.upper().split()
            )
        else:
            self.number_plate = None

        super().save(*args, **kwargs)

    def __str__(self):
        return (
            f"{self.username} "
            f"({self.get_role_display()})"
        )