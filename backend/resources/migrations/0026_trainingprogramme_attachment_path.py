import re
from urllib.parse import unquote, urlsplit

from django.db import migrations, models

STORED_NAME = re.compile(r"^[0-9a-f]{32}\.[a-z0-9]{1,5}$")


def backfill_attachment_paths(apps, schema_editor):
    TrainingProgramme = apps.get_model("resources", "TrainingProgramme")
    for programme in TrainingProgramme.objects.exclude(
            supporting_doc__isnull=True).iterator():
        path = unquote(urlsplit(programme.supporting_doc or "").path)
        if "/resources/training/attachment/" not in path:
            continue
        name = path.rsplit("/", 1)[-1]
        if STORED_NAME.fullmatch(name):
            stored_path = f"training/{name}"
            if TrainingProgramme.objects.filter(
                    attachment_path=stored_path).exists():
                continue
            programme.attachment_path = stored_path
            programme.save(update_fields=["attachment_path"])


class Migration(migrations.Migration):

    dependencies = [
        ("resources", "0025_course_departments"),
    ]

    operations = [
        migrations.AddField(
            model_name="trainingprogramme",
            name="attachment_path",
            field=models.CharField(
                blank=True, editable=False, max_length=255,
                null=True, unique=True),
        ),
        migrations.RunPython(backfill_attachment_paths, migrations.RunPython.noop),
    ]
