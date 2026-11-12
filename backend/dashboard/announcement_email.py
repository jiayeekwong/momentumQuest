"""Email the accounts that can see a newly published announcement.

Announcements remain visible in the in-app feed. Email is an additional,
mandatory notification for active, verified accounts in the selected audience.
Each recipient gets an individual message so their address is never disclosed
to another recipient.
"""

import logging
from html import unescape

from django.conf import settings
from django.core.mail import EmailMultiAlternatives, get_connection
from django.utils.html import strip_tags

from accounts.models import User

from .models import Announcement


logger = logging.getLogger(__name__)


def _plain_text(value):
    """Make the sanitized announcement body suitable for a text email."""
    return " ".join(unescape(strip_tags(value)).split())


def send_announcement_email_notifications(announcement_id):
    """Send one notification per eligible student and return the accepted count.

    The announcement is fetched again because this runs from ``on_commit``;
    it must never send for a transaction that did not commit. Mail failures are
    logged rather than turning a successfully published announcement into a
    failed admin request.
    """
    try:
        announcement = Announcement.objects.get(pk=announcement_id)
    except Announcement.DoesNotExist:
        return 0

    audience_roles = {
        Announcement.AudienceChoice.STUDENTS: [User.Role.STUDENT],
        Announcement.AudienceChoice.COMPANIES: [User.Role.COMPANY],
        Announcement.AudienceChoice.EVERYONE: [User.Role.STUDENT, User.Role.COMPANY],
    }.get(announcement.audience)
    if not audience_roles:
        return 0

    recipients = list(
        User.objects
        .filter(
            role__in=audience_roles,
            is_active=True,
            email_verified=True,
        )
        .values_list("email", flat=True)
    )
    if not recipients:
        return 0

    dashboard_url = f"{settings.FRONTEND_URL.rstrip('/')}/dashboard"
    body = _plain_text(announcement.message)
    attachment_text = (
        f"View attachment: {announcement.supporting_doc}\n\n"
        if announcement.supporting_doc else ""
    )
    text = (
        "A new MomentumQuest announcement has been published.\n\n"
        f"{body}\n\n"
        f"{attachment_text}"
        f"View it in MomentumQuest: {dashboard_url}\n"
    )
    subject = f"New MomentumQuest announcement: {announcement.title}"
    messages = [
        EmailMultiAlternatives(
            subject=subject,
            body=text,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[email],
        )
        for email in recipients
    ]

    try:
        sent = get_connection().send_messages(messages)
    except Exception:
        # No recipient data appears in this log. The mail backend has the
        # provider-level error details and must not expose addresses either.
        logger.exception(
            "Could not send announcement email notifications for announcement %s",
            announcement.pk,
        )
        return 0

    if sent != len(messages):
        logger.error(
            "Announcement %s email delivery accepted %s of %s messages",
            announcement.pk, sent, len(messages),
        )
    return sent
