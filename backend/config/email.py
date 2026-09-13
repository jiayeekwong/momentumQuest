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

Two providers live here, both over HTTPS, chosen by EMAIL_BACKEND::

    EMAIL_BACKEND=config.email.GmailApiEmailBackend
    GMAIL_CLIENT_ID / GMAIL_CLIENT_SECRET / GMAIL_REFRESH_TOKEN

    EMAIL_BACKEND=config.email.ResendEmailBackend
    EMAIL_API_KEY

DEFAULT_FROM_EMAIL is configured separately from either, because the address a
student sees is a product decision rather than a property of the transport.

Development keeps whatever it had: console, locmem under tests, or real SMTP.
"""
import base64
import json
import logging
import urllib.error
import urllib.parse
import urllib.request
# Absolute import: this module is config.email, so "email" here is the standard
# library package and not itself.
from email.utils import parseaddr

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


class GmailApiEmailBackend(BaseEmailBackend):
    """Send through the Gmail API, authenticated by a stored refresh token.

    Gmail also speaks SMTP, and that is the obvious way to do this and the wrong
    one here: outbound SMTP ports are commonly blocked on free hosting, and the
    failure is silent -- send_mail waits for a connection that will never open,
    the registration request still returns success, and the verification link
    never arrives.

    Two HTTPS calls per batch:

        GMAIL_REFRESH_TOKEN -> oauth2.googleapis.com/token -> access token
        access token        -> gmail.googleapis.com messages.send

    The access token is short-lived and lives only in a local variable. It is
    not written to the database, to a file, or to a cache: a stored Google
    credential is a liability that has to be protected, expired and rotated, and
    one extra HTTPS round trip per batch buys the absence of all of that. This
    project sends a handful of messages a day, so there is nothing to optimise.

    The OAuth client is scoped to https://www.googleapis.com/auth/gmail.send
    alone -- no inbox read, no mailbox modification. A leaked refresh token
    should be able to send mail and learn nothing.
    """

    token_endpoint = "https://oauth2.googleapis.com/token"
    send_endpoint = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"

    def __init__(self, fail_silently=False, **kwargs):
        super().__init__(fail_silently=fail_silently, **kwargs)
        self.client_id = (getattr(settings, "GMAIL_CLIENT_ID", "") or "").strip()
        self.client_secret = (
            getattr(settings, "GMAIL_CLIENT_SECRET", "") or "").strip()
        self.refresh_token = (
            getattr(settings, "GMAIL_REFRESH_TOKEN", "") or "").strip()

        # Named, never their values: a misconfiguration message that prints a
        # client secret turns a small mistake into a disclosure, and these
        # messages end up in deployment logs and pasted into chat.
        missing = [name for name, value in (
            ("GMAIL_CLIENT_ID", self.client_id),
            ("GMAIL_CLIENT_SECRET", self.client_secret),
            ("GMAIL_REFRESH_TOKEN", self.refresh_token),
        ) if not value]

        if missing and not self.fail_silently:
            raise ImproperlyConfigured(
                "config.email.GmailApiEmailBackend needs "
                + ", ".join(missing)
                + ". Without them no verification or password-reset mail can be "
                  "sent, and a student who registers can never log in.")

        # There is no GMAIL_SENDER_EMAIL. Gmail sends as whichever account the
        # refresh token belongs to, so a second sender setting could disagree
        # with reality while looking authoritative. DEFAULT_FROM_EMAIL is the
        # one sender, and it has to be usable.
        #
        # The reason this is checked here rather than in settings: the project's
        # fallback is f"MomentumQuest <{EMAIL_HOST_USER}>", and EMAIL_HOST_USER
        # is os.getenv with no default -- so an unconfigured deployment gets the
        # literal string "MomentumQuest <None>". Harmless with the console
        # backend, which is why settings cannot refuse it, and a rejected or
        # misattributed message here. Local SMTP development is unaffected
        # because only this backend looks.
        if not self.fail_silently:
            sender = (getattr(settings, "DEFAULT_FROM_EMAIL", "") or "").strip()
            if not _usable_sender(sender):
                raise ImproperlyConfigured(
                    "config.email.GmailApiEmailBackend needs a real "
                    f"DEFAULT_FROM_EMAIL, and found {sender!r}. It must carry "
                    "an email address, e.g. "
                    "'MomentumQuest <system-account@gmail.com>'. Normally that "
                    "is the same Gmail account as GMAIL_REFRESH_TOKEN: Gmail "
                    "rewrites From to the authenticated account unless the "
                    "address is a verified 'Send mail as' alias on it.")

    # ------------------------------------------------------------------ token

    def _access_token(self):
        """Exchange the refresh token for a short-lived access token.

        Returns None on failure, having logged why. Google's error bodies name
        the problem -- invalid_grant when the token was revoked, invalid_client
        when the secret is wrong -- and carry no credential of ours, so a
        truncated body is safe to log and is the difference between a fixable
        report and "mail is broken".
        """
        body = urllib.parse.urlencode({
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": self.refresh_token,
            "grant_type": "refresh_token",
        }).encode("utf-8")

        request = urllib.request.Request(
            self.token_endpoint,
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(
                    request, timeout=TIMEOUT_SECONDS) as response:
                if not 200 <= response.status < 300:
                    logger.error("Gmail token exchange failed: HTTP %s",
                                 response.status)
                    return None
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            logger.error("Gmail token exchange failed: HTTP %s %s",
                         exc.code, _safe_detail(exc))
            return None
        except Exception:
            logger.exception("Could not reach the Google token endpoint")
            return None

        token = payload.get("access_token")
        if not token:
            # A 200 carrying no token is a contract change rather than a
            # credential problem, and the key names alone say which.
            logger.error(
                "Gmail token response carried no access_token (keys: %s)",
                sorted(payload))
            return None
        return token

    # ------------------------------------------------------------------- send

    def send_messages(self, email_messages):
        """Returns how many were accepted, as Django's contract requires."""
        if not email_messages:
            return 0

        # One token for the batch. Django hands over the whole list at once, and
        # a token per message would be an extra request per message for nothing.
        token = self._access_token()
        if token is None:
            return 0

        sent = 0
        for message in email_messages:
            if self._send(message, token):
                sent += 1
        return sent

    def _raw(self, message):
        """The message as Gmail wants it: base64url of the MIME bytes.

        Django builds the MIME, which is the point. Reassembling subject, body,
        HTML alternatives and attachments into a provider's own JSON shape is
        where those parts get quietly dropped -- the Resend backend above
        carries exactly that risk and handles only what this project happens to
        send today. Here To, Cc, Bcc, Reply-To, the text part, any HTML
        alternative and any attachment survive because nothing re-derives them.
        """
        return base64.urlsafe_b64encode(
            message.message().as_bytes()).decode("ascii")

    def _send(self, message, token):
        if not message.recipients():
            return False

        request = urllib.request.Request(
            self.send_endpoint,
            data=json.dumps({"raw": self._raw(message)}).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(
                    request, timeout=TIMEOUT_SECONDS) as response:
                if 200 <= response.status < 300:
                    return True
                logger.error("Gmail rejected a message: HTTP %s",
                             response.status)
        except urllib.error.HTTPError as exc:
            logger.error("Gmail rejected a message: HTTP %s %s",
                         exc.code, _safe_detail(exc))
        except Exception:
            # Never the recipient, the subject or the body: these logs are read
            # by people who do not need a student's address, and the body of a
            # password-reset message contains a working token.
            logger.exception("Could not reach the Gmail API")

        return False


def _usable_sender(value):
    """Is this a From address Gmail can actually send as?

    Deliberately shallow: the job is catching an unconfigured deployment, not
    validating addresses. "MomentumQuest <None>" parses to the address "None",
    which has no "@" and is exactly the case worth refusing.
    """
    if not value:
        return False
    _name, address = parseaddr(value)
    address = (address or "").strip()
    return bool(address) and "@" in address and not any(
        character.isspace() for character in address)


def _safe_detail(exc):
    """A provider's error body, truncated, for the log.

    Safe because it is the provider describing our request rather than echoing
    it: Google's OAuth and Gmail errors name the fault without repeating the
    credential or the message. Truncated so a verbose HTML error page cannot
    fill the log.
    """
    try:
        return exc.read().decode("utf-8", "replace")[:400]
    except Exception:
        return ""
