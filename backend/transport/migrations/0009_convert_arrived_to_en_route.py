from django.db import migrations


def convert_arrived_to_en_route(apps, schema_editor):
    DispatchAssignment = apps.get_model(
        "transport",
        "DispatchAssignment",
    )

    DispatchAssignment.objects.filter(
        status="ARRIVED"
    ).update(status="EN_ROUTE")


class Migration(migrations.Migration):

    dependencies = [
        ("transport", "0008_alter_dispatchassignment_waiting_spot"),
    ]

    operations = [
        migrations.RunPython(
            convert_arrived_to_en_route,
            migrations.RunPython.noop,
        ),
    ]