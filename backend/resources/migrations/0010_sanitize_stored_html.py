"""Sanitize training-programme descriptions written before the sanitizer.

These are company-authored and rendered with dangerouslySetInnerHTML on both
the student resources page and the admin approvals panel, so an unsanitized
row runs in the reviewing administrator's browser. Idempotent.
"""

from django.db import migrations

from config.sanitization import sanitize_html, sanitize_text


def sanitize(apps, schema_editor):
    TrainingProgramme = apps.get_model("resources", "TrainingProgramme")
    for programme in TrainingProgramme.objects.only(
            "id", "description", "title").iterator(chunk_size=500):
        description = sanitize_html(programme.description)
        title = sanitize_text(programme.title)
        if (description, title) != (programme.description, programme.title):
            TrainingProgramme.objects.filter(pk=programme.pk).update(
                description=description, title=title)


class Migration(migrations.Migration):

    dependencies = [
        ("resources", "0009_alter_transcriptupload_verification_method"),
    ]

    operations = [
        migrations.RunPython(sanitize, migrations.RunPython.noop),
    ]
