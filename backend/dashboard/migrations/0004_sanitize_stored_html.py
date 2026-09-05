"""Sanitize announcement bodies written before the sanitizer existed.

Announcements are rendered with dangerouslySetInnerHTML on the student,
company and admin dashboards -- the widest audience of any content in the
platform. Idempotent.
"""

from django.db import migrations

from config.sanitization import sanitize_html, sanitize_text


def sanitize(apps, schema_editor):
    Announcement = apps.get_model("dashboard", "Announcement")
    for announcement in Announcement.objects.only(
            "id", "message", "title").iterator(chunk_size=500):
        message = sanitize_html(announcement.message)
        title = sanitize_text(announcement.title)
        if (message, title) != (announcement.message, announcement.title):
            Announcement.objects.filter(pk=announcement.pk).update(
                message=message, title=title)


class Migration(migrations.Migration):

    dependencies = [
        ("dashboard", "0003_revert_supporting_doc_to_urlfield"),
    ]

    operations = [
        migrations.RunPython(sanitize, migrations.RunPython.noop),
    ]
