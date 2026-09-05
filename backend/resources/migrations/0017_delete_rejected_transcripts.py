"""Remove transcript uploads that were refused.

A refused upload is now discarded as it is refused: nothing was extracted from
it, its file is already gone, and there is no administrator to escalate it to.
Keeping the row left a filename and an error message sitting in the student's
list looking like a submission they still had to deal with.

The rows written before that change are cleared here. Their UserConsent rows
are deliberately left standing: consent is append-only evidence, the student
did agree, and the document was processed under that agreement.
"""

from django.db import migrations


def delete_refused(apps, schema_editor):
    TranscriptUpload = apps.get_model("resources", "TranscriptUpload")
    TranscriptUpload.objects.filter(verification_status="REJECTED").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("resources", "0016_settle_legacy_transcripts"),
    ]

    operations = [
        migrations.RunPython(delete_refused, migrations.RunPython.noop),
    ]
