"""A log formatter that removes personal data and credentials from its output.

Used for django.request, which records every unhandled exception with its
traceback. Once that traceback reaches the deployment's logs it is read by
people who have no need for students' personal data, so what it prints matters.

The request body is never printed: django.request attaches the request as
``extra``, which a format string does not render, and a traceback shows source
lines rather than the values of local variables. So a submitted password or
token is not in the output to begin with.

Exception *messages* are another matter, because they can carry values from the
statement that failed. accounts.User.email is unique, so a duplicate-address
race reaches the database and fails with

    DETAIL:  Key (email)=(student@example.edu) already exists.

and that line would go straight into the logs. The same risk applies to any
token that ends up in an error message. So the fully formatted record, traceback
included, has those patterns replaced before it is written.

This is redaction by pattern, which means it is a safety net and not a licence:
code should still avoid putting personal data into exception messages.
"""

import logging
import re

#: An email address. Deliberately broad: a false positive costs a log reader a
#: few characters, a false negative costs a student their address.
EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")

#: A JSON Web Token -- three base64url segments, the first always starting "eyJ"
#: because it encodes '{"'. These are the access and refresh tokens SimpleJWT
#: issues, and each one is a working credential until it expires.
JWT = re.compile(r"eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+")

#: Anything following "Bearer", whatever its shape.
BEARER = re.compile(r"(?i)(bearer\s+)\S+")

#: A Django password-reset style token: base36 timestamp, a hyphen, then hex.
#: This project carries them in request bodies rather than URLs, but a token
#: quoted in an error message would otherwise be printed in full.
RESET_TOKEN = re.compile(r"\b[0-9a-z]{1,13}-[0-9a-f]{20,}\b")


def redact(text):
    """Replace personal data and credentials in already-formatted log text."""
    text = JWT.sub("[redacted-token]", text)
    text = BEARER.sub(r"\1[redacted-token]", text)
    text = RESET_TOKEN.sub("[redacted-token]", text)
    return EMAIL.sub("[redacted-email]", text)


class RedactingFormatter(logging.Formatter):
    """A standard formatter whose output, traceback included, is redacted.

    Redacting the final string rather than the record's fields is the point:
    the traceback text is produced inside format(), from the exception, and
    would not pass through any field a filter could clean beforehand.
    """

    def format(self, record):
        return redact(super().format(record))
