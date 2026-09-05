"""Undo the entity-escaping 0004 left in announcement titles.

Same defect as job_listings/0021: ``sanitize_text`` returned HTML-escaped
output for a field that is rendered as a React text node, so an ampersand
reached the reader as "&amp;". Idempotent.
"""

from django.db import migrations

from config.sanitization import sanitize_text


def repair(apps, schema_editor):
    Announcement = apps.get_model("dashboard", "Announcement")
    for announcement in Announcement.objects.only("id", "title").iterator(chunk_size=500):
        title = sanitize_text(announcement.title)
        if title != announcement.title:
            Announcement.objects.filter(pk=announcement.pk).update(title=title)


class Migration(migrations.Migration):

    dependencies = [
        ("dashboard", "0004_sanitize_stored_html"),
    ]

    operations = [
        migrations.RunPython(repair, migrations.RunPython.noop),
    ]
