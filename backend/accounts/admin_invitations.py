"""Token issuance and email delivery for administrator invitations."""

import hashlib
import logging
import secrets
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone


logger = logging.getLogger(__name__)


def invitation_token_hash(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_invitation_token():
    token = secrets.token_urlsafe(32)
    return (
        token,
        invitation_token_hash(token),
        timezone.now() + timedelta(
            seconds=settings.ADMIN_INVITATION_TIMEOUT_SECONDS),
    )


def issue_invitation_token(invitation):
    """Replace the invitation's bearer token and return the raw value once."""
    token, token_hash, expires_at = new_invitation_token()
    invitation.token_hash = token_hash
    invitation.expires_at = expires_at
    invitation.status = invitation.Status.PENDING
    invitation.revoked_at = None
    invitation.save(update_fields=[
        "token_hash", "expires_at", "status", "revoked_at", "updated_at",
    ])
    return token


def send_admin_invitation(invitation, token):
    """Send one invitation without allowing mail failure to corrupt its row."""
    link = (
        f"{settings.FRONTEND_URL.rstrip('/')}/accept-admin-invitation"
        f"?token={token}"
    )
    try:
        send_mail(
            subject="You have been invited to administer MomentumQuest",
            message=(
                "A MomentumQuest superadmin invited you to become the "
                f"administrator for {invitation.department.name}.\n\n"
                f"Create your administrator account: {link}\n\n"
                "This invitation is single-use and expires automatically. "
                "If you were not expecting it, you can ignore this email."
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[invitation.email],
            fail_silently=False,
        )
    except Exception:
        logger.exception("Could not send admin invitation %s", invitation.pk)
