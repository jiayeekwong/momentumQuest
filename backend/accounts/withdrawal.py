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
    """Re-derive the student's skills now that some evidence is withdrawn.

    Delegates to resources.skill_evidence, which is the single authority on
    what level each skill is currently supported at. This used to be a second,
    boolean-only implementation living here: it could drop a skill whose
    evidence had gone entirely, but not *lower* one whose remaining evidence
    supported less -- so withdrawing an Advanced certificate left the student
    at Advanced on the strength of a Beginner one.

    Skills with no recorded provenance are outside the scope of this mechanism
    and are left alone; see evidenced_skill_ids.

    Returns the number of skills removed.
    """
    # Imported here: accounts must not import resources at module scope, or the
    # app registry loads in the wrong order.
    from resources.skill_evidence import recalculate_student_skills

    return recalculate_student_skills(student)["removed"]


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


@transaction.atomic
def restore_consent(user, consent_type, request=None):
    """Give a withdrawn consent again, as a new row.

    Withdrawal used to be a one-way door: the notice told the student to
    "restore it in Settings" and no such path existed, so a single click
    locked them out of document verification permanently.

    Append-only, like every other consent event. The withdrawn row keeps its
    ``withdrawn_at`` -- that withdrawal is a fact about what the student
    decided, and rewriting it to look like it never happened is exactly what
    the table exists to prevent. What changes is that a *newer* row now says
    yes, and every check reads the latest one.

    Skills are **not** brought back. Their evidence was removed when the
    consent went, and re-consenting does not re-verify a document nobody has
    looked at since. The student uploads again, which is the honest path.

    Returns the new consent. Raises WithdrawalError if there is nothing to
    restore.
    """
    from .privacy_notice import CURRENT_VERSION

    latest = (
        UserConsent.objects
        .filter(user=user, consent_type=consent_type)
        .order_by("-created_at")
        .first()
    )
    if latest is not None and latest.is_live:
        raise WithdrawalError("This consent is already active.")

    consent = UserConsent.objects.create(
        user=user,
        consent_type=consent_type,
        notice_version=CURRENT_VERSION,
        accepted=True,
        accepted_at=timezone.now(),
        source=UserConsent.Source.SETTINGS_RESTORE,
    )

    record_privacy_event(
        PrivacyAuditLog.Action.CONSENT_ACCEPTED,
        actor=user,
        target=user,
        resource_id=consent.pk,
        resource_type=PrivacyAuditLog.ResourceType.CONSENT,
        request=request,
    )
    return consent
