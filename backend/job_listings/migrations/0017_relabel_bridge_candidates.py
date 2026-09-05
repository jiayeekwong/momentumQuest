"""Relabel candidates that still carry a MASCO bridge source.

The two bridge sources described evidence that no longer exists. The rows
themselves are still valid review items -- a suggested listing-to-role link
nobody has confirmed -- so they are relabelled rather than deleted.
"""

from django.db import migrations


def relabel(apps, schema_editor):
    ICTRoleCandidate = apps.get_model("job_listings", "ICTRoleCandidate")
    ICTRoleCandidate.objects.filter(
        source__in=("UNVERIFIED_BRIDGE", "AMBIGUOUS_BRIDGE")
    ).update(source="AMBIGUOUS_TITLE")


def unrelabel(apps, schema_editor):
    # One-way: the two old sources said different things and which row was
    # which is no longer recorded. Reversing would have to guess.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("job_listings", "0016_alter_ictrolecandidate_source"),
    ]

    operations = [
        migrations.RunPython(relabel, unrelabel),
    ]
