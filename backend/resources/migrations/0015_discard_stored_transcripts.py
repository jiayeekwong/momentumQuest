"""Apply the skills every stored transcript already proves, then delete it.

Transcripts are no longer kept. The upload reads the PDF, records the
subjects, grades and skills, and discards the document before it responds --
so the rows written under the old flow are the only ones left holding a file,
and the only ones still waiting for an administrator who will never come.

Each one is settled the way the new flow would have settled it at upload:

  * a transcript that parsed and classified is auto-verified from its own
    classification, its skills applied, and its evidence rows written;
  * one that was already rejected keeps that decision;
  * every stored PDF is unlinked and ``file_path`` cleared, whichever way it
    went.

The extracted subjects and grades stay. They are the record now.
"""

from django.db import migrations
from django.utils import timezone


def settle_and_discard(apps, schema_editor):
    from resources import private_storage
    from resources.skill_recognition import resolve_skills

    TranscriptUpload = apps.get_model("resources", "TranscriptUpload")
    TranscriptSkillEvidence = apps.get_model("resources", "TranscriptSkillEvidence")
    StudentSkill = apps.get_model("accounts", "StudentSkill")
    Skill = apps.get_model("scrape_jobs", "Skill")

    now = timezone.now()
    ranks = {"BEGINNER": 1, "INTERMEDIATE": 2, "ADVANCED": 3}

    for transcript in TranscriptUpload.objects.iterator(chunk_size=100):
        pending = transcript.verification_status == "PENDING"
        usable = transcript.document_type_status in (
            "LIKELY_TRANSCRIPT", "UNCERTAIN") and transcript.status == "PARSED"

        if pending and usable and transcript.parsed_subjects:
            # resolve_skills works on the live Skill model, which is the same
            # table; the historical model is only needed for the write.
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
                elif ranks.get(level, 0) > ranks.get(row.skill_level, 0):
                    row.skill_level = level
                    row.save(update_fields=["skill_level"])

            transcript.verification_status = "AUTO_VERIFIED"
            transcript.verification_method = "CLASSIFICATION"
            transcript.reviewed_at = now
            transcript.skills_applied_at = now
            transcript.skills_added = len(levels)

        if transcript.file_path:
            private_storage.delete(transcript.file_path)
            transcript.file_path = ""

        transcript.save()


class Migration(migrations.Migration):

    dependencies = [
        ("resources", "0014_repair_escaped_titles"),
    ]

    operations = [
        # Irreversible: the documents are gone.
        migrations.RunPython(settle_and_discard, migrations.RunPython.noop),
    ]
