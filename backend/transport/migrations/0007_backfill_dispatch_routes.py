from django.db import migrations


def backfill_dispatch_routes(apps, schema_editor):
    DispatchAssignment = apps.get_model(
        "transport",
        "DispatchAssignment",
    )

    assignments = DispatchAssignment.objects.filter(
        route__isnull=True
    ).select_related("waiting_spot__route")

    for assignment in assignments:
        assignment.route_id = assignment.waiting_spot.route_id
        assignment.save(update_fields=["route"])


def reverse_backfill(apps, schema_editor):
    DispatchAssignment = apps.get_model(
        "transport",
        "DispatchAssignment",
    )

    DispatchAssignment.objects.update(route=None)


class Migration(migrations.Migration):

    dependencies = [
        ("transport", "0006_dispatchassignment_route"),
    ]

    operations = [
        migrations.RunPython(
            backfill_dispatch_routes,
            reverse_backfill,
        ),
    ]