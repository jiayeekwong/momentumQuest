"""Undo the entity-escaping 0010 left in training-programme titles.

Same defect as job_listings/0021. No rows needed repairing when this was
written, but the migration ships anyway: whether a deployment has an affected
row depends on its own data, not on ours. Idempotent.
"""

from django.db import migrations

from config.sanitization import sanitize_text


def repair(apps, schema_editor):
    TrainingProgramme = apps.get_model("resources", "TrainingProgramme")
    for programme in TrainingProgramme.objects.only("id", "title").iterator(chunk_size=500):
        title = sanitize_text(programme.title)
        if title != programme.title:
            TrainingProgramme.objects.filter(pk=programme.pk).update(title=title)


class Migration(migrations.Migration):

    dependencies = [
        ("resources", "0013_remove_certificate_skill"),
    ]

    operations = [
        migrations.RunPython(repair, migrations.RunPython.noop),
    ]
