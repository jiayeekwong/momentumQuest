"""Signed, time-limited proof that a CV was parsed with consent.

An application is assembled from information a CV parser proposed and the
student then confirmed. The receipt is what ties those two requests together:
it says *this* student consented to *this* parse at *this* time, and it expires.

It exists so the submit endpoint can record which CV_PROCESSING_CONSENT the
application was built on without trusting the client to name one. A client-supplied
consent ID could be any row; a signed receipt can only be one this server issued,
to this user, recently.

What the receipt deliberately does **not** claim: that the extracted information
is accurate, verified, or genuinely from the CV. The student edits the parsed
result before submitting, and is meant to. It proves consented processing
happened, nothing about the content.

Built on ``django.core.signing``, the same mechanism the email- and
password-change flows use, so there is no new key material and no new
dependency.
"""

from django.core import signing
from django.utils import timezone

# Long enough to read a parsed CV, correct it and press submit without
# rushing; short enough that a leaked receipt is not a standing credential.
RECEIPT_MAX_AGE_SECONDS = 60 * 60  # 1 hour

SALT = "mq-cv-parse-receipt"


class InvalidReceipt(Exception):
    """The receipt is absent, malformed, expired, or another user's."""


def issue(user_id, consent_id):
    """Sign a receipt for a completed, consented parse."""
    now = timezone.now()
    return signing.dumps(
        {
            "user_id": user_id,
            "consent_id": consent_id,
            "issued_at": now.isoformat(),
            "expires_at": (
                now + timezone.timedelta(seconds=RECEIPT_MAX_AGE_SECONDS)
            ).isoformat(),
        },
        salt=SALT,
    )


def verify(token, user_id):
    """Return the payload of a valid receipt belonging to ``user_id``.

    Raises InvalidReceipt for a missing, tampered, expired or foreign receipt.
    The user check is what stops one student presenting another's receipt: the
    signature only proves this server issued it, not who to.
    """
    if not token:
        raise InvalidReceipt("A CV parse receipt is required.")

    try:
        payload = signing.loads(
            token, salt=SALT, max_age=RECEIPT_MAX_AGE_SECONDS
        )
    except signing.SignatureExpired:
        raise InvalidReceipt(
            "Your CV was read too long ago. Please upload it again."
        )
    except signing.BadSignature:
        raise InvalidReceipt("This CV parse receipt is not valid.")

    if payload.get("user_id") != user_id:
        raise InvalidReceipt("This CV parse receipt belongs to another account.")

    return payload
