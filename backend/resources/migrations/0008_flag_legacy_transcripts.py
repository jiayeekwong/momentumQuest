"""Queue every pre-verification transcript for administrator review.

Transcripts uploaded before this change applied skills to the student's
profile immediately, with no check that the document came from a university
at all. Those skills are already in StudentSkill.

**They are deliberately not revoked.** Nothing in the old schema recorded
which transcript granted which skill -- TranscriptSkillEvidence exists from
this release onwards precisely to close that gap -- so a blanket deletion
would also destroy skills that came from endorsed certificates, and a
targeted deletion is not possible. Re-deriving them from parsed_subjects
would still not say whether a *certificate* had independently granted the
same skill at a higher level.

So the honest action is: mark the documents as never-verified, put them in
the review queue, and leave the skills alone. An administrator approving a
legacy transcript re-applies its skills through the normal path, which then
writes the evidence rows that were missing.

Known limitation, recorded here and in the README: until every legacy
transcript is reviewed, a student's skills may include entries whose issuer
was never checked.
"""

from django.db import migrations


def flag_legacy_transcripts(apps, schema_editor):
    TranscriptUpload = apps.get_model("resources", "TranscriptUpload")

    TranscriptUpload.objects.filter(status="PARSED").update(
        document_type_status="LEGACY_UNVERIFIED",
        verification_status="PENDING",
        verification_method="NONE",
        classification_score=0,
        classification_reasons=[
            "Uploaded before document classification existed.",
            "Skills were applied without any issuer verification.",
            "Queued for administrator review.",
        ],
    )

    # A failed upload never applied skills, so it needs no review -- but it
    # must not sit in the pending queue either.
    TranscriptUpload.objects.filter(status="FAILED").update(
        document_type_status="NOT_TRANSCRIPT",
        verification_status="REJECTED",
        rejection_reason="Upload could not be parsed.",
    )


def unflag(apps, schema_editor):
    TranscriptUpload = apps.get_model("resources", "TranscriptUpload")
    TranscriptUpload.objects.update(
        document_type_status="UNCERTAIN",
        verification_status="PENDING",
        classification_reasons=[],
    )


class Migration(migrations.Migration):

    dependencies = [
        ("resources", "0007_transcriptupload_classification_reasons_and_more"),
    ]

    operations = [
        migrations.RunPython(flag_legacy_transcripts, unflag),
    ]
