"""Production exceptions must reach the logs, and personal data must not.

A production login returned 500 while the deployment logs showed only gunicorn's
access line. Django did log the exception, with its traceback, but its default
handlers both discard that record when DEBUG is false, and gunicorn gives the
root logger no handler to fall back on. These pin the fix: an unexpected
exception is written to stderr with its traceback, the client still sees nothing
of it, and what is written carries no email address, password or token.
"""

import io
import logging
from unittest import mock

from django.db.utils import IntegrityError, ProgrammingError
from django.test import Client, TestCase

from config.log_redaction import RedactingFormatter, redact

EMAIL = "production-student@example.edu"
PASSWORD = "Correct-Horse-Battery-9"


class CapturedRequestLog:
    """Point the configured django.request handler at a buffer, then restore it.

    Uses the handler settings.LOGGING actually builds, so a test of it is a test
    of the production configuration rather than of a handler made up for the
    occasion.
    """

    def __enter__(self):
        logger = logging.getLogger("django.request")
        streams = [h for h in logger.handlers if isinstance(h, logging.StreamHandler)]
        if not streams:
            raise AssertionError("django.request has no stream handler configured")
        self.handler = streams[0]
        self.buffer = io.StringIO()
        self.previous = self.handler.setStream(self.buffer)
        return self

    def __exit__(self, *exc):
        self.handler.setStream(self.previous)

    @property
    def text(self):
        return self.buffer.getvalue()


def failing_throttle(*_args, **_kwargs):
    """The production failure: the throttle's cache table does not exist."""
    raise ProgrammingError('relation "django_cache" does not exist')


class RequestExceptionLoggingConfigurationTests(TestCase):

    def test_django_request_writes_to_a_stream(self):
        """Not to mail_admins alone, which with no ADMINS sends nothing."""
        logger = logging.getLogger("django.request")

        self.assertTrue(any(isinstance(h, logging.StreamHandler)
                            for h in logger.handlers))

    def test_it_does_not_propagate(self):
        """Otherwise development prints every error twice: once here, once
        through Django's own console handler."""
        self.assertFalse(logging.getLogger("django.request").propagate)

    def test_its_output_is_redacted(self):
        handler = next(h for h in logging.getLogger("django.request").handlers
                       if isinstance(h, logging.StreamHandler))

        self.assertIsInstance(handler.formatter, RedactingFormatter)


class UnexpectedLoginExceptionTests(TestCase):
    """The production failure, reproduced without its cause.

    The test cache is in memory, so the missing table cannot occur here; the
    throttle is made to raise the same error instead. That exercises exactly the
    path that failed -- DRF's check_throttles, before authentication runs.
    """

    def _login(self):
        client = Client(raise_request_exception=False)
        return client.post(
            "/api/auth/login/",
            data={"email": EMAIL, "password": PASSWORD},
            content_type="application/json",
        )

    def test_the_traceback_reaches_the_log(self):
        with mock.patch("rest_framework.throttling.ScopedRateThrottle.allow_request",
                        failing_throttle), CapturedRequestLog() as log:
            response = self._login()

        self.assertEqual(response.status_code, 500)
        self.assertIn("Internal Server Error: /api/auth/login/", log.text)
        self.assertIn("Traceback", log.text)
        self.assertIn('relation "django_cache" does not exist', log.text)

    def test_the_client_receives_no_exception_detail(self):
        """DEBUG is false under the test runner, as in production."""
        with mock.patch("rest_framework.throttling.ScopedRateThrottle.allow_request",
                        failing_throttle), CapturedRequestLog():
            response = self._login()

        body = response.content.decode("utf-8", "replace")
        self.assertNotIn("django_cache", body)
        self.assertNotIn("Traceback", body)
        self.assertNotIn("ProgrammingError", body)

    def test_the_submitted_credentials_are_not_logged(self):
        with mock.patch("rest_framework.throttling.ScopedRateThrottle.allow_request",
                        failing_throttle), CapturedRequestLog() as log:
            self._login()

        self.assertNotIn(EMAIL, log.text)
        self.assertNotIn(PASSWORD, log.text)

    def test_an_email_inside_the_exception_message_is_redacted(self):
        """The realistic leak. User.email is unique, so a duplicate-address race
        fails in the database with the address quoted in the error."""
        def duplicate_email(*_args, **_kwargs):
            raise IntegrityError(
                'duplicate key value violates unique constraint '
                '"accounts_user_email_key"\n'
                f'DETAIL:  Key (email)=({EMAIL}) already exists.')

        with mock.patch("rest_framework.throttling.ScopedRateThrottle.allow_request",
                        duplicate_email), CapturedRequestLog() as log:
            self._login()

        self.assertIn("accounts_user_email_key", log.text)   # still diagnosable
        self.assertNotIn(EMAIL, log.text)
        self.assertIn("[redacted-email]", log.text)


class RedactionTests(TestCase):

    def test_email_addresses(self):
        self.assertEqual(redact("Key (email)=(a.b+tag@uni.edu.my) exists"),
                         "Key (email)=([redacted-email]) exists")

    def test_json_web_tokens(self):
        token = ("eyJhbGciOiJIUzI1NiJ9.eyJ1c2VyX2lkIjo0Mn0."
                 "k3r5tYx9Qm2Lp8Zw1Vb6Nc4Hd7Jf0Sg3")

        self.assertEqual(redact(f"token {token} rejected"),
                         "token [redacted-token] rejected")

    def test_bearer_credentials(self):
        self.assertEqual(redact("Authorization: Bearer abc.def.ghi"),
                         "Authorization: Bearer [redacted-token]")

    def test_password_reset_tokens(self):
        self.assertEqual(redact("bad token cv2x7q-8e2b1f4c9a7d3e6b5f0a1c2d"),
                         "bad token [redacted-token]")

    def test_an_ordinary_traceback_line_is_left_alone(self):
        """Redaction that mangled the diagnosis would defeat the purpose."""
        line = ('  File "/app/rest_framework/throttling.py", line 123, in allow_request\n'
                'django.db.utils.ProgrammingError: relation "django_cache" does not exist')

        self.assertEqual(redact(line), line)

    def test_a_uuid_is_not_mistaken_for_a_reset_token(self):
        text = "object 550e8400-e29b-41d4-a716-446655440000"

        self.assertEqual(redact(text), text)

    def test_the_formatter_redacts_the_traceback_not_only_the_message(self):
        formatter = RedactingFormatter("%(message)s")
        try:
            raise ValueError(f"lookup failed for {EMAIL}")
        except ValueError:
            import sys
            record = logging.LogRecord("t", logging.ERROR, __file__, 1,
                                       "request failed", None, sys.exc_info())

        output = formatter.format(record)

        self.assertIn("Traceback", output)
        self.assertNotIn(EMAIL, output)
