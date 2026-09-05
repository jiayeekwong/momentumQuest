"""Retire the IMDA-derived career targets before Market Roles replace them.

An existing StudentTargetRole names an IMDA framework rung. Those rungs are
not Market Roles, and translating one into the other by name would be exactly
the automatic conversion the Market Role migration forbids: the picker's
vocabulary changed wholesale, from 124 framework rungs to a reviewed set of
career groups derived from Malaysian ICT adverts, and a name that appears in
both does not mean the student was offered the same thing.

So the targets are cleared and students re-pick from the new list. SkillGap
rows hang off a target and go with it; they are point-in-time records of a
gap measured against a scope that no longer exists, and keeping them would
attribute old numbers to a new career group.

Nothing scraped is touched.
"""

from django.db import migrations


def clear_targets(apps, schema_editor):
    apps.get_model("accounts", "SkillGap").objects.all().delete()
    apps.get_model("accounts", "StudentTargetRole").objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0013_remove_studenttargetoccupation_unique_student_target_occupation_and_more"),
    ]

    operations = [
        # Irreversible by design: the rows named a vocabulary that no longer
        # exists, so there is nothing truthful to restore them to.
        migrations.RunPython(clear_targets, migrations.RunPython.noop),
    ]
