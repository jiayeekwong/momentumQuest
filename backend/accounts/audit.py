"""Recording of sensitive privacy events.

One rule governs this module: an audit write must never break the operation it
is auditing. An admin approving a certificate should not see a 500 because the
log table was momentarily unavailable, so every failure here is swallowed and
reported to the application log instead -- the same defensive shape as the
refresh_skill_gaps call in resources.skill_recognition.

The second rule is what is *not* recorded. Uploaded documents carry NRIC/MyKad
and passport numbers, so nothing derived from a document's contents is passed
to these helpers, and PrivacyAuditLog has no free-text column that could hold
one. The log answers "who did what, to whose record, when" and nothing more.
"""

import logging

from .models import PrivacyAuditLog

logger = logging.getLogger(__name__)


def client_ip(request):
    """Best-effort client IP, or None when it cannot be determined.

    X-Forwarded-For is honoured because the app is expected to sit behind a
    reverse proxy in deployment; the left-most entry is the original client.
    """
    if request is None:
        return None

    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        candidate = forwarded.split(",")[0].strip()
        if candidate:
            return candidate

    return request.META.get("REMOTE_ADDR") or None


def record_privacy_event(action, actor=None, target=None, resource_id=None,
                         resource_type=PrivacyAuditLog.ResourceType.CERTIFICATE,
                         request=None):
    """Append one row to the privacy audit log.

    Returns the created row, or None if the write failed. Callers are not
    expected to check: the return value exists for tests, not for control flow.
    """
    try:
        return PrivacyAuditLog.objects.create(
            actor_user=actor if getattr(actor, "is_authenticated", False) else None,
            target_user=target,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            ip_address=client_ip(request),
        )
    except Exception:
        # Deliberately broad: there is no failure mode here worth propagating
        # to a student mid-upload or an admin mid-decision.
        logger.exception("Privacy audit write failed for action %s on resource %s",
                         action, resource_id)
        return None
