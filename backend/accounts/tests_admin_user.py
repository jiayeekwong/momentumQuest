"""A user created in the Django admin must be able to log in.

None of this was covered, and that is how it reached production. `accounts.User`
replaces the username with an email, so Django's stock admin forms -- declared
against django.contrib.auth.User and its `username` field -- did not fit, and the
model was registered with `admin.site.register(User)` instead. That gives the
default ModelAdmin, which builds a plain ModelForm over every editable field.
`password` is an ordinary CharField on AbstractBaseUser, so the Add User page
showed one visible text box and stored exactly what was typed.

Two consequences, and the quieter one is worse. The account could not log in,
because check_password compares a raw string against something that is not a
hash. And the password sat in the database in clear text, readable by anyone
with access to the table or a backup.

These tests exercise the admin pages over HTTP rather than the forms in
isolation, because the defect was in which form the admin chose, not in any
form's behaviour.
"""

from django.contrib.auth import authenticate
from django.contrib.auth.hashers import identify_hasher
from django.test import TestCase

from .models import User

ADMIN_EMAIL = "root@example.edu"
ADMIN_PASSWORD = "Root-Pass-123"
NEW_EMAIL = "made-in-admin@example.edu"
NEW_PASSWORD = "AdminTyped-Password-123"

ADD_URL = "/admin/accounts/user/add/"


class AdminCreatedUserTests(TestCase):

    def setUp(self):
        User.objects.create_superuser(email=ADMIN_EMAIL, password=ADMIN_PASSWORD)
        self.client.login(email=ADMIN_EMAIL, password=ADMIN_PASSWORD)

    def _add(self, **overrides):
        payload = {
            "email": NEW_EMAIL,
            "role": User.Role.ADMIN,
            "usable_password": "true",
            "password1": NEW_PASSWORD,
            "password2": NEW_PASSWORD,
            "_save": "Save",
        }
        payload.update(overrides)
        return self.client.post(ADD_URL, payload, follow=True)

    # ---- what the page asks for -------------------------------------------

    def test_the_page_asks_for_the_password_twice(self):
        """One password box is the visible symptom of the wrong form."""
        page = self.client.get(ADD_URL).content.decode()

        self.assertIn("password1", page)
        self.assertIn("password2", page)
        self.assertNotIn('name="password"', page)

    # ---- the four that would have caught the bug ---------------------------

    def test_the_stored_password_is_a_django_hash(self):
        self._add()
        user = User.objects.get(email=NEW_EMAIL)

        self.assertEqual(identify_hasher(user.password).algorithm, "pbkdf2_sha256")

    def test_the_raw_password_is_not_stored(self):
        self._add()
        user = User.objects.get(email=NEW_EMAIL)

        self.assertNotEqual(user.password, NEW_PASSWORD)
        self.assertNotIn(NEW_PASSWORD, user.password)

    def test_the_created_user_can_authenticate(self):
        self._add()

        self.assertTrue(User.objects.get(email=NEW_EMAIL).check_password(NEW_PASSWORD))
        self.assertIsNotNone(
            authenticate(username=NEW_EMAIL, password=NEW_PASSWORD))

    def test_a_wrong_password_is_refused(self):
        self._add()

        self.assertFalse(
            User.objects.get(email=NEW_EMAIL).check_password("not-the-password"))
        self.assertIsNone(
            authenticate(username=NEW_EMAIL, password="not-the-password"))

    # ---- confirmation and validation ---------------------------------------

    def test_a_mismatched_confirmation_creates_nothing(self):
        self._add(password2="something-else")

        self.assertFalse(User.objects.filter(email=NEW_EMAIL).exists())

    def test_the_configured_password_validators_apply(self):
        """A generic ModelForm applied none of them."""
        self._add(password1="123", password2="123")

        self.assertFalse(User.objects.filter(email=NEW_EMAIL).exists())

    def test_the_old_single_field_payload_no_longer_creates_a_user(self):
        """The exact shape that used to store plain text."""
        self.client.post(ADD_URL, {
            "email": NEW_EMAIL, "role": User.Role.ADMIN,
            "password": NEW_PASSWORD, "_save": "Save"}, follow=True)

        self.assertFalse(User.objects.filter(email=NEW_EMAIL).exists())

    # ---- the change page ---------------------------------------------------

    def test_editing_a_user_cannot_replace_the_hash_with_plain_text(self):
        """The change form shows the hash read-only. Posting a password anyway
        must leave the stored hash alone rather than writing the raw string."""
        self._add()
        user = User.objects.get(email=NEW_EMAIL)
        stored = user.password

        self.client.post(f"/admin/accounts/user/{user.pk}/change/", {
            "email": user.email, "role": User.Role.ADMIN,
            "password": "PLAINTEXT-ATTEMPT", "is_active": "on",
            "created_time_0": "2026-09-23", "created_time_1": "10:00:00",
            "_save": "Save"}, follow=True)
        user.refresh_from_db()

        self.assertEqual(user.password, stored)
        self.assertTrue(user.check_password(NEW_PASSWORD))


class OtherUserCreationPathsAreUnaffectedTests(TestCase):
    """The admin was the only broken path; the others must stay working."""

    def test_createsuperuser_still_hashes(self):
        """The known-good reference: UserManager.create_user calls
        set_password, which is why this path always worked."""
        user = User.objects.create_superuser(email="ref@example.edu",
                                             password=NEW_PASSWORD)

        self.assertEqual(identify_hasher(user.password).algorithm, "pbkdf2_sha256")
        self.assertIsNotNone(
            authenticate(username="ref@example.edu", password=NEW_PASSWORD))

    def test_api_registration_still_hashes(self):
        from rest_framework.test import APIClient

        response = APIClient().post("/api/auth/register/", {
            "email": "registered@example.edu",
            "password": NEW_PASSWORD,
            "confirm_password": NEW_PASSWORD,
            "role": User.Role.STUDENT,
            "name": "Registered Student",
            "privacy_notice_accepted": True,
            "document_verification_consent": True,
        }, format="json")

        self.assertEqual(response.status_code, 201)
        user = User.objects.get(email="registered@example.edu")
        self.assertEqual(identify_hasher(user.password).algorithm, "pbkdf2_sha256")
        self.assertNotEqual(user.password, NEW_PASSWORD)

    def test_the_create_admin_command_still_hashes(self):
        """It takes --email and --name and reads ADMIN_PASSWORD from the
        environment, which is the documented way to make the first admin."""
        import os
        from io import StringIO
        from unittest import mock

        from django.core.management import call_command

        with mock.patch.dict(os.environ, {"ADMIN_PASSWORD": NEW_PASSWORD}):
            call_command("create_admin", email="cli@example.edu",
                         name="CLI Admin", stdout=StringIO())
        user = User.objects.get(email="cli@example.edu")

        self.assertEqual(identify_hasher(user.password).algorithm, "pbkdf2_sha256")
        self.assertIsNotNone(
            authenticate(username="cli@example.edu", password=NEW_PASSWORD))
