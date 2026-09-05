"""Deriving StudentSkill from the evidence that currently backs it.

StudentSkill is a *materialized result*, not a place things are written to.
Its level must always equal the highest level supported by evidence that is
live right now:

    highest approved certificate level
    highest accepted transcript level          -> StudentSkill.skill_level
    (any future accepted evidence)

``apply_skills`` remains as the upgrade-only path used while a transcript or
an endorsement is being processed, because raising a level as evidence arrives
is the right behaviour at that moment. It is not authoritative, and it cannot
be: it has no way to lower a level, so removing a student's only Advanced
certificate used to leave them showing Advanced forever, backed by nothing.

This module is the authority. It reads every live source, takes the maximum,
and writes -- or deletes -- accordingly. It must run after anything that can
change what evidence exists:

    certificate approval, rejection, withdrawal or deletion
    transcript verification, rejection, withdrawal or deletion
    an evidence-level correction

A recalculation never consults the existing StudentSkill row, deliberately.
Reading the current level to decide whether to keep it is exactly how a level
outlives its evidence.
"""

import logging

from django.db import transaction

from accounts.models import StudentSkill

from .transcript_parser import LEVEL_RANK

logger = logging.getLogger(__name__)


def _rank(level):
    return LEVEL_RANK.get(level, 0)


def certificate_levels(student, skills=None):
    """{skill_id: level} from approved claims on approved certificates.

    Both conditions matter and are checked here rather than trusted from the
    caller: an approved certificate can carry rejected claims, and a rejected
    certificate's approved-looking claims must not count.
    """
    from .models import Certificate, CertificateSkillEvidence

    rows = (CertificateSkillEvidence.objects
            .filter(certificate__student=student,
                    review_status=CertificateSkillEvidence.ReviewStatus.APPROVED,
                    certificate__verified_status=Certificate.VerifiedStatus.APPROVED)
            # A document whose upload consent has been withdrawn is no longer
            # something this platform may act on, whatever it once proved.
            .exclude(certificate__upload_consent__withdrawn_at__isnull=False)
            .exclude(approved_level="")
            .values_list("skill_id", "approved_level"))
    if skills is not None:
        rows = rows.filter(skill_id__in=[s.id for s in skills])

    best = {}
    for skill_id, level in rows:
        if _rank(level) > _rank(best.get(skill_id)):
            best[skill_id] = level
    return best


def transcript_levels(student, skills=None):
    """{skill_id: level} from transcripts whose issuer was accepted.

    Read from TranscriptSkillEvidence, which records which transcript granted
    which skill at which level, joined against the transcript's *current*
    verification status. That join is what makes withdrawal work: a transcript
    later rejected stops contributing without anything having to remember what
    it once granted, and a deleted transcript takes its evidence with it by
    cascade.

    A transcript still pending review contributes nothing, including the
    legacy uploads that applied skills before issuer verification existed.
    Those skills were never backed by a checked document, so they are not
    evidence now.
    """
    from .models import TranscriptSkillEvidence, TranscriptUpload

    rows = (TranscriptSkillEvidence.objects
            .filter(transcript__student=student,
                    transcript__verification_status__in=TranscriptUpload.VERIFIED_STATUSES)
            .exclude(transcript__upload_consent__withdrawn_at__isnull=False)
            .values_list("skill_id", "skill_level"))
    if skills is not None:
        rows = rows.filter(skill_id__in=[s.id for s in skills])

    best = {}
    for skill_id, level in rows:
        if _rank(level) > _rank(best.get(skill_id)):
            best[skill_id] = level
    return best


def live_skill_levels(student, skills=None):
    """{skill_id: level} the student's evidence currently supports.

    The highest level across all sources. A later, lower-level certificate
    never pulls an existing higher level down, because the maximum is taken
    over evidence rather than applied in arrival order -- and equally, losing
    the Advanced evidence drops the student to the next-highest rather than
    stranding them at Advanced.
    """
    levels = {}
    for source in (certificate_levels(student, skills),
                   transcript_levels(student, skills)):
        for skill_id, level in source.items():
            if _rank(level) > _rank(levels.get(skill_id)):
                levels[skill_id] = level
    return levels


def evidenced_skill_ids(student):
    """Skill ids this platform has ever recorded provenance for.

    The removal scope when the caller does not name one. Skills outside it
    predate evidence tracking -- transcripts uploaded before issuer
    verification existed applied skills with nothing recorded about where they
    came from -- and deleting those would be guessing, not recalculating.

    A caller that *knows* which skills an operation affected passes them
    explicitly instead, which is how deleting a certificate still removes the
    skill it was the last support for: the skills are read off the document
    before it goes.
    """
    from .models import CertificateSkillEvidence, TranscriptSkillEvidence

    return set(
        CertificateSkillEvidence.objects
        .filter(certificate__student=student)
        .values_list("skill_id", flat=True)
    ) | set(
        TranscriptSkillEvidence.objects
        .filter(transcript__student=student)
        .values_list("skill_id", flat=True)
    )


@transaction.atomic
def recalculate_student_skills(student, skills=None, refresh_gaps=True):
    """Rebuild ``student``'s skills from live evidence. Returns a summary.

    ``skills`` names the skills a decision touched. It is also the *removal*
    scope: a skill outside it keeps whatever level it has. Omit it to rebuild
    the whole profile, in which case removal falls back to the skills with
    recorded provenance -- see evidenced_skill_ids.

    Returns ``{"created": n, "updated": n, "removed": n}``.
    """
    levels = live_skill_levels(student, skills)

    existing = StudentSkill.objects.filter(student=student)
    if skills is not None:
        existing = existing.filter(skill_id__in=[s.id for s in skills])
        removable = {s.id for s in skills}
    else:
        removable = evidenced_skill_ids(student)
    existing = {row.skill_id: row for row in existing}

    created = updated = removed = 0

    for skill_id, level in levels.items():
        row = existing.get(skill_id)
        if row is None:
            StudentSkill.objects.create(
                student=student, skill_id=skill_id, skill_level=level)
            created += 1
        elif row.skill_level != level:
            row.skill_level = level
            row.save(update_fields=["skill_level"])
            updated += 1

    # A skill with no evidence left is not a skill this platform can claim the
    # student has. Removing the row is the honest outcome; leaving it would
    # show a company a verified skill whose proof has been withdrawn.
    orphaned = [skill_id for skill_id in existing
                if skill_id not in levels and skill_id in removable]
    if orphaned:
        removed = StudentSkill.objects.filter(
            student=student, skill_id__in=orphaned).delete()[0]

    if refresh_gaps and (created or updated or removed):
        _refresh_gaps(student)

    return {"created": created, "updated": updated, "removed": removed}


def recalculate_student_skill(student, skill):
    """Rebuild one skill. Returns the StudentSkill row, or None if removed."""
    recalculate_student_skills(student, skills=[skill])
    return StudentSkill.objects.filter(student=student, skill=skill).first()


def _refresh_gaps(student):
    # Imported here, not at module level: dashboard.skill_gap_snapshots
    # reaches dashboard.views, which imports resources.models, and a top-level
    # import would close that cycle.
    from dashboard.skill_gap_snapshots import refresh_skill_gaps

    # Never a reason to fail the decision that triggered it: the skills are
    # already written and are what the live analysis reads.
    try:
        refresh_skill_gaps(student)
    except Exception:
        logger.exception(
            "Skill-gap refresh failed for student %s after a recalculation",
            student.pk,
        )
