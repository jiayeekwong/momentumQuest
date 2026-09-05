"""Report which StudentSkill rows were probably granted by an unverified transcript.

The problem this addresses: legacy transcripts applied skills with no issuer
check, and the old schema recorded no link between a transcript and the skills
it granted. The scoring engine trusts every StudentSkill equally, so those
rows currently influence match percentages, skill-gap results and recommended
learning.

Provenance cannot be recovered exactly -- that is the whole reason
TranscriptSkillEvidence now exists -- but it can be *narrowed*. A skill is
attributable to a legacy transcript when all of these hold:

  * the student has a LEGACY_UNVERIFIED transcript,
  * that transcript's parsed_subjects map to the skill,
  * no TranscriptSkillEvidence row claims it (so no verified transcript
    granted it), and
  * no approved Certificate covers it.

That last condition is what stops the report blaming a transcript for a skill
an endorsed certificate independently granted.

Reports by default. --revoke deletes the attributable rows, and should be run
only after the legacy review queue has been worked through, because an
administrator approving a legacy transcript re-grants its skills properly.
"""

from collections import defaultdict

from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.models import StudentSkill
from resources.models import (
    Certificate, CertificateSkillEvidence, TranscriptSkillEvidence,
    TranscriptUpload,
)
from resources.skill_recognition import resolve_skills


class Command(BaseCommand):
    help = "Report (or revoke) skills granted by never-verified legacy transcripts"

    def add_arguments(self, parser):
        parser.add_argument(
            "--revoke", action="store_true",
            help="Delete the attributable skills instead of only reporting them.")

    @transaction.atomic
    def handle(self, *args, **options):
        revoke = options["revoke"]

        legacy = (
            TranscriptUpload.objects
            .filter(document_type_status=TranscriptUpload.DocumentTypeStatus.LEGACY_UNVERIFIED)
            .select_related("student")
        )
        if not legacy.exists():
            self.stdout.write(self.style.SUCCESS(
                "No legacy transcripts. Every transcript-granted skill has evidence."))
            return

        attributable = defaultdict(set)   # student_id -> {skill_id}
        by_student = {}

        for transcript in legacy:
            by_student[transcript.student_id] = transcript.student
            for skill in resolve_skills(transcript.parsed_subjects or []):
                attributable[transcript.student_id].add(skill.id)

        total_flagged = total_protected = 0
        for student_id, skill_ids in attributable.items():
            student = by_student[student_id]

            # A skill with evidence came from a verified transcript.
            evidenced = set(
                TranscriptSkillEvidence.objects
                .filter(transcript__student_id=student_id, skill_id__in=skill_ids)
                .values_list("skill_id", flat=True)
            )
            # A skill an approved certificate covers was granted independently.
            #
            # Read from CertificateSkillEvidence, not Certificate.skill_id: one
            # document evidences several skills and each carries its own
            # decision, so that column was dropped. This query still referenced
            # it and the command raised before printing anything.
            #
            # Both halves must hold. An approved document can still carry a
            # skill claim the reviewer refused, and that skill was not granted
            # by the certificate -- so it must not be treated as protected.
            certified = set(
                CertificateSkillEvidence.objects
                .filter(certificate__student_id=student_id,
                        skill_id__in=skill_ids,
                        review_status=CertificateSkillEvidence.ReviewStatus.APPROVED,
                        certificate__verified_status=Certificate.VerifiedStatus.APPROVED)
                .values_list("skill_id", flat=True)
            )
            protected = evidenced | certified
            flagged = skill_ids - protected

            held = StudentSkill.objects.filter(
                student_id=student_id, skill_id__in=flagged
            ).select_related("skill")

            if held:
                self.stdout.write(
                    f"\n{student.student_name}: {held.count()} skill(s) from an "
                    f"unverified transcript")
                for row in held:
                    self.stdout.write(f"    {row.skill.skill_name} ({row.skill_level})")
            if protected:
                self.stdout.write(
                    f"  ({len(protected)} skill(s) protected by a verified "
                    f"transcript or approved certificate)")

            total_flagged += held.count()
            total_protected += len(protected)

            if revoke and held:
                held.delete()

        if revoke:
            self.stdout.write(self.style.WARNING(
                f"\nRevoked {total_flagged} unverified skill(s). Students may "
                "re-earn them when an administrator approves the legacy "
                "transcript, which then records proper evidence."))
        else:
            self.stdout.write(self.style.SUCCESS(
                f"\n{total_flagged} skill(s) attributable to an unverified "
                f"transcript, {total_protected} independently supported. "
                "Re-run with --revoke to remove them, ideally after working "
                "through the legacy review queue."))
