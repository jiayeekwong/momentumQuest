import re
from urllib.parse import unquote, urlsplit

from django.db import migrations, models

STORED_NAME = re.compile(r"^[0-9a-f]{32}\.[a-z0-9]{1,5}$")


def backfill_attachment_paths(apps, schema_editor):
    Announcement = apps.get_model("dashboard", "Announcement")
    for announcement in Announcement.objects.exclude(
            supporting_doc__isnull=True).iterator():
        path = unquote(urlsplit(announcement.supporting_doc or "").path)
        if "/dashboard/announcements/attachment/" not in path:
            continue
        name = path.rsplit("/", 1)[-1]
        if STORED_NAME.fullmatch(name):
            stored_path = f"announcements/{name}"
            if Announcement.objects.filter(
                    attachment_path=stored_path).exists():
                continue
            announcement.attachment_path = stored_path
            announcement.save(update_fields=["attachment_path"])


class Migration(migrations.Migration):

    dependencies = [
        ("dashboard", "0005_repair_escaped_titles"),
    ]

    operations = [
        migrations.AddField(
            model_name="announcement",
            name="attachment_path",
            field=models.CharField(
                blank=True, editable=False, max_length=255,
                null=True, unique=True),
        ),
        migrations.RunPython(backfill_attachment_paths, migrations.RunPython.noop),
    ]
