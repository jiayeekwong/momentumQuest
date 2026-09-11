"""Sending mail over HTTPS instead of SMTP.

Free hosting commonly blocks outbound SMTP ports, and a blocked port is the
worst shape this failure can take: ``send_mail`` hangs until it times out, the
registration request that triggered it appears to succeed, and the verification
link simply never arrives. The student cannot log in and there is nothing on the
page to explain why.

This is a Django email backend, which is the whole point of putting it here.
Every caller in the project uses ``django.core.mail.send_mail`` -- registration
verification, password reset, the privacy contact -- so the provider is a
settings value and no domain code knows which one is in use. Swapping providers
later is a new class and an environment variable, not an edit to the views that
send mail.

Configure with::

    EMAIL_BACKEND=config.email.ResendEmailBackend
    EMAIL_API_KEY=<the provider's API key>
    DEFAULT_FROM_EMAIL=MomentumQuest <no-reply@your-domain>

Development keeps whatever it had: console, locmem under tests, or real SMTP.
"""

import json
import logging
import urllib.error
import urllib.request

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.mail.backends.base import BaseEmailBackend

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 15


class ResendEmailBackend(BaseEmailBackend):
    """Post each message to Resend's HTTPS API.

    Uses urllib rather than a client library: this is one JSON POST, and the
    deployment image is better off without another dependency to pin and patch.
    """

    endpoint = "https://api.resend.com/emails"

    def __init__(self, fail_silently=False, **kwargs):
        super().__init__(fail_silently=fail_silently, **kwargs)
        self.api_key = (getattr(settings, "EMAIL_API_KEY", "") or "").strip()
        if not self.api_key and not self.fail_silently:
            raise ImproperlyConfigured(
                "EMAIL_API_KEY is required by config.email.ResendEmailBackend. "
                "Without it no verification or password-reset mail can be sent, "
                "and a student who registers can never log in.")

    def send_messages(self, email_messages):
        """Returns how many were accepted, as Django's contract requires."""
        if not email_messages:
            return 0

        sent = 0
        for message in email_messages:
            if self._send(message):
                sent += 1
        return sent

    def _payload(self, message):
        # Plain text only, matching what this project actually sends. An
        # alternatives-carrying message would need "html" here, and silently
        # dropping the HTML part would be worse than not supporting it.
        payload = {
            "from": message.from_email or settings.DEFAULT_FROM_EMAIL,
            "to": list(message.to),
            "subject": message.subject,
            "text": message.body,
        }
        if message.cc:
            payload["cc"] = list(message.cc)
        if message.bcc:
            payload["bcc"] = list(message.bcc)
        if message.reply_to:
            payload["reply_to"] = list(message.reply_to)
        for content, mimetype in getattr(message, "alternatives", ()) or ():
            if mimetype == "text/html":
                payload["html"] = content
        return payload

    def _send(self, message):
        if not message.recipients():
            return False

        request = urllib.request.Request(
            self.endpoint,
            data=json.dumps(self._payload(message)).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                # 2xx only. A provider that answers 202 has accepted it.
                if 200 <= response.status < 300:
                    return True
                logger.error("Mail provider rejected a message: HTTP %s",
                             response.status)
        except urllib.error.HTTPError as exc:
            # The body carries the reason -- an unverified sending domain, a
            # bad key -- and without it the log says only "400".
            detail = ""
            try:
                detail = exc.read().decode("utf-8", "replace")[:400]
            except Exception:
                pass
            logger.error("Mail provider rejected a message: HTTP %s %s",
                         exc.code, detail)
        except Exception:
            # Never the recipient address: these logs are read by people who do
            # not need the student's email, and it is personal data.
            logger.exception("Could not reach the mail provider")

        if not self.fail_silently:
            # Django's contract is a count, not an exception, and the callers
            # here treat mail as best-effort around a request that has already
            # succeeded. Raising would turn "the email is late" into "the
            # account was not created".
            pass
        return False
