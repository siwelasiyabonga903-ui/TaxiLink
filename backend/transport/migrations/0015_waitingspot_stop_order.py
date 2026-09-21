from django.db import migrations, models
import django.core.validators


def assign_stop_orders(
    apps,
    schema_editor,
):
    Route = apps.get_model(
        "transport",
        "Route",
    )

    WaitingSpot = apps.get_model(
        "transport",
        "WaitingSpot",
    )

    for route in Route.objects.all():
        spots = (
            WaitingSpot.objects
            .filter(route=route)
            .order_by(
                "created_at",
                "id",
            )
        )

        for index, spot in enumerate(
            spots,
            start=1,
        ):
            spot.stop_order = index

            spot.save(
                update_fields=[
                    "stop_order",
                ]
            )


class Migration(migrations.Migration):

    dependencies = [
        (
            "transport",
            "0014_devicetoken_notification",
        ),
    ]

    operations = [
        migrations.AddField(
            model_name="waitingspot",
            name="stop_order",
            field=models.PositiveIntegerField(
                null=True,
                blank=True,
            ),
        ),

        migrations.RunPython(
            assign_stop_orders,
            migrations.RunPython.noop,
        ),

        migrations.AlterField(
            model_name="waitingspot",
            name="stop_order",
            field=models.PositiveIntegerField(
                default=1,
                validators=[
                    django.core.validators.MinValueValidator(
                        1
                    ),
                ],
            ),
        ),

        migrations.AddConstraint(
            model_name="waitingspot",
            constraint=models.UniqueConstraint(
                fields=(
                    "route",
                    "stop_order",
                ),
                name=(
                    "unique_waiting_spot_order_per_route"
                ),
            ),
        ),
    ]