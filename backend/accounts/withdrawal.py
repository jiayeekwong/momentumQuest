"""Withdrawing a consent, in one place.

The privacy notice promises that a consent can be withdrawn, that withdrawal
stops future processing, that the record survives, and that skills resting only
on withdrawn evidence are recalculated. Each of those is a separate mechanism,
and doing them piecemeal at call sites is how they drift apart -- one endpoint
stamps the row, another forgets the audit entry, a third leaves a granted skill
standing on evidence the student has revoked.

So there is exactly one entry point: ``withdraw_consent``.

What withdrawal is
------------------
Setting ``withdrawn_at``. It never deletes the row and never clears ``accepted``
or ``accepted_at`` -- a record that could be erased would not be evidence, and
the fact that consent *was* given on a date remains true afterwards. Past
processing that happened while the consent was live stays lawful.

What it is not
--------------
Account deletion. A student who withdraws document-verification consent keeps
their account, their applications and their history; what stops is MomentumQuest
verifying anything new for them.
"""

import logging

from django.db import transaction
from django.utils import timezone

from .audit import record_privacy_event
from .models import PrivacyAuditLog, UserConsent

logger = logging.getLogger(__name__)


class WithdrawalError(Exception):
    """The consent cannot be withdrawn."""


def live_consent(user, consent_type):
    """The most recent consent of this type that still authorises processing.

    Consent is append-only, so "does this user consent" is a question about the
    latest row, not about any row: a student who accepted, withdrew, and
    accepted again is consenting now, and one who accepted then withdrew is not.
    """
    latest = (
        UserConsent.objects
        .filter(user=user, consent_type=consent_type)
        .order_by("-created_at")
        .first()
    )
    return latest if (latest and latest.is_live) else None


def has_live_consent(user, consent_type):
    return live_consent(user, consent_type) is not None


def _recalculate_skills_for(student):
    """Drop skills whose only support was evidence that is gone or withdrawn.

    A skill is kept when *any* live evidence still supports it: an approved
    certificate, or a verified transcript. Skills with no evidence row at all
    are left alone -- they predate evidence tracking, and there is nothing
    recorded to say they came from a withdrawn document. Removing them would be
    guessing, and the guess would silently strip a student's profile.

    Returns the number of skills removed.
    """
    # Imported here: accounts must not import resources at module scope, or the
    # app registry loads in the wrong order.
    from accounts.models import StudentSkill
    from resources.models import Certificate, TranscriptSkillEvidence, TranscriptUpload

    supported_by_certificate = set(
        Certificate.objects
        .filter(student=student,
                verified_status=Certificate.VerifiedStatus.APPROVED)
        .exclude(upload_consent__withdrawn_at__isnull=False)
        .values_list("skill_id", flat=True)
    )

    verified_transcripts = TranscriptUpload.objects.filter(
        student=student,
        verification_status__in=(
            TranscriptUpload.VerificationStatus.AUTO_VERIFIED,
            TranscriptUpload.VerificationStatus.MANUALLY_VERIFIED,
        ),
    ).exclude(upload_consent__withdrawn_at__isnull=False)

    supported_by_transcript = set(
        TranscriptSkillEvidence.objects
        .filter(transcript__in=verified_transcripts)
        .values_list("skill_id", flat=True)
    )

    still_supported = supported_by_certificate | supported_by_transcript

    # Only skills that some evidence row once pointed at are in scope. Anything
    # never backed by a recorded document is outside this mechanism entirely.
    ever_evidenced = set(
        Certificate.objects.filter(student=student)
        .values_list("skill_id", flat=True)
    ) | set(
        TranscriptSkillEvidence.objects
        .filter(transcript__student=student)
        .values_list("skill_id", flat=True)
    )

    orphaned = ever_evidenced - still_supported
    if not orphaned:
        return 0

    removed, _ = StudentSkill.objects.filter(
        student=student, skill_id__in=orphaned
    ).delete()

    if removed:
        # The student's gaps are computed from the skills they hold, so they
        # are wrong the moment a skill goes.
        try:
            from dashboard.skill_gap_snapshots import refresh_skill_gaps
            refresh_skill_gaps(student)
        except Exception:
            logger.exception(
                "Skill-gap refresh failed after withdrawal for student %s", student.pk)

    return removed


@transaction.atomic
def withdraw_consent(consent, actor=None, request=None):
    """Withdraw one consent and bring the consequences with it.

    Everything happens together or not at all: a consent stamped as withdrawn
    while the skills it supported still stand would be the worst of both -- the
    student told the processing stopped, the employer still shown the result.

    Returns ``(consent, skills_removed)``.
    """
    if consent.withdrawn_at is not None:
        raise WithdrawalError("This consent has already been withdrawn.")
    if not consent.accepted:
        raise WithdrawalError("This consent was never given, so it cannot be withdrawn.")

    consent.withdrawn_at = timezone.now()
    consent.save(update_fields=["withdrawn_at", "updated_at"])

    skills_removed = 0
    student = getattr(consent.user, "student_profile", None)
    if (student is not None
            and consent.consent_type ==
            UserConsent.ConsentType.DOCUMENT_VERIFICATION_CONSENT):
        skills_removed = _recalculate_skills_for(student)

    record_privacy_event(
        PrivacyAuditLog.Action.CONSENT_WITHDRAWN,
        actor=actor or consent.user,
        target=consent.user,
        resource_id=consent.pk,
        resource_type=PrivacyAuditLog.ResourceType.CONSENT,
        request=request,
    )

    return consent, skills_removed


def withdraw_latest(user, consent_type, actor=None, request=None):
    """Withdraw whichever consent of this type is currently authorising."""
    consent = live_consent(user, consent_type)
    if consent is None:
        raise WithdrawalError(
            "There is no active consent of this type to withdraw.")
    return withdraw_consent(consent, actor=actor, request=request)
