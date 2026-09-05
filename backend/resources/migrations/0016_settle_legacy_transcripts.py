"""Settle the legacy transcripts 0015 left behind.

0015 skipped rows marked ``LEGACY_UNVERIFIED`` -- uploads that predate
document classification entirely, so there is no classification result to
auto-verify them from. It discarded their PDFs along with everything else,
which leaves them stranded: pending review that no longer exists, with no
document to review.

Under the current policy there is no administrator step, so the question
"should a human look at this?" has no answer to wait for. What the row does
hold is the subjects and grades read from the document at the time, and those
are as good now as they were then -- deleting the PDF did not make them wrong.

So each one grants its skills and is marked verified by classification, with
the LEGACY_UNVERIFIED marker left in place: it stays true that this document
was never classified, and that is worth keeping on the record.
"""

from django.db import migrations
from django.utils import timezone

LEVEL_RANKS = {"BEGINNER": 1, "INTERMEDIATE": 2, "ADVANCED": 3}


def settle(apps, schema_editor):
    from resources.skill_recognition import resolve_skills

    TranscriptUpload = apps.get_model("resources", "TranscriptUpload")
    TranscriptSkillEvidence = apps.get_model("resources", "TranscriptSkillEvidence")
    StudentSkill = apps.get_model("accounts", "StudentSkill")

    now = timezone.now()

    for transcript in (TranscriptUpload.objects
                       .filter(status="PARSED", verification_status="PENDING")
                       .iterator(chunk_size=100)):
        if not transcript.parsed_subjects:
            continue

        levels = {
            skill.pk: level for skill, level in
            resolve_skills([dict(row, skills=[])
                            for row in transcript.parsed_subjects]).items()
        }
        for skill_id, level in levels.items():
            TranscriptSkillEvidence.objects.update_or_create(
                transcript_id=transcript.pk, skill_id=skill_id,
                defaults={"skill_level": level})
            row = StudentSkill.objects.filter(
                student_id=transcript.student_id, skill_id=skill_id).first()
            if row is None:
                StudentSkill.objects.create(
                    student_id=transcript.student_id, skill_id=skill_id,
                    skill_level=level)
            elif LEVEL_RANKS.get(level, 0) > LEVEL_RANKS.get(row.skill_level, 0):
                row.skill_level = level
                row.save(update_fields=["skill_level"])

        transcript.verification_status = "AUTO_VERIFIED"
        transcript.verification_method = "CLASSIFICATION"
        transcript.reviewed_at = now
        transcript.skills_applied_at = now
        transcript.skills_added = len(levels)
        transcript.save(update_fields=[
            "verification_status", "verification_method", "reviewed_at",
            "skills_applied_at", "skills_added",
        ])


class Migration(migrations.Migration):

    dependencies = [
        ("resources", "0015_discard_stored_transcripts"),
    ]

    operations = [
        migrations.RunPython(settle, migrations.RunPython.noop),
    ]
