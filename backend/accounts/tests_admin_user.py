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


class TheAdminOffersTheProfileForTheRoleTests(TestCase):
    """A user row is half an account, and the admin only ever made that half.

    Everything the application reads about a person -- a student's name and
    department, a company's details, the administrator a record is attributed
    to -- lives in a table joined one-to-one. Sign-up creates those through the
    registration serializer and `create_admin` creates an AdminProfile; the
    Add User page went through neither, so an account made here was missing the
    half that gets used. It first showed up as a 500 on publishing an
    announcement, weeks after the account was made.

    The profile is offered as an inline rather than conjured by a signal: an
    administrator filling one in is making a decision, and a second silent path
    to an AdminProfile is the shape of a bug this codebase replaced once.
    """

    def setUp(self):
        User.objects.create_superuser(email=ADMIN_EMAIL, password=ADMIN_PASSWORD)
        self.client.login(email=ADMIN_EMAIL, password=ADMIN_PASSWORD)

    def _change_page(self, user):
        return self.client.get(f"/admin/accounts/user/{user.pk}/change/").content.decode()

    def test_an_admin_account_offers_an_administrator_profile(self):
        user = User.objects.create_user(email="new-admin@example.edu",
                                        password=NEW_PASSWORD,
                                        role=User.Role.ADMIN)

        self.assertIn("admin_profile-0-admin_name", self._change_page(user))

    def test_a_student_account_offers_a_student_profile(self):
        user = User.objects.create_user(email="new-student@example.edu",
                                        password=NEW_PASSWORD,
                                        role=User.Role.STUDENT)
        page = self._change_page(user)

        self.assertIn("student_profile-0-student_name", page)
        self.assertNotIn("admin_profile-0-admin_name", page)

    def test_a_company_account_offers_a_company_profile(self):
        user = User.objects.create_user(email="new-company@example.edu",
                                        password=NEW_PASSWORD,
                                        role=User.Role.COMPANY)
        page = self._change_page(user)

        self.assertIn("company_profile-0-company_name", page)
        self.assertNotIn("student_profile-0-student_name", page)

    def test_the_add_page_offers_none_of_them(self):
        """The role is chosen in the same submission, so nothing yet decides
        which profile applies. Django goes to the change page next, which is
        where it appears."""
        page = self.client.get(ADD_URL).content.decode()

        for prefix in ("admin_profile-0-", "student_profile-0-",
                       "company_profile-0-"):
            self.assertNotIn(prefix, page)

    def test_a_profile_can_be_filled_in_from_the_user_page(self):
        """The whole point: the account can be completed where it was made."""
        from accounts.models import AdminProfile

        user = User.objects.create_user(email="fill-me@example.edu",
                                        password=NEW_PASSWORD,
                                        role=User.Role.ADMIN)

        self.client.post(f"/admin/accounts/user/{user.pk}/change/", {
            "email": user.email, "role": User.Role.ADMIN, "is_active": "on",
            "created_time_0": "2026-09-27", "created_time_1": "10:00:00",
            "admin_profile-TOTAL_FORMS": "1",
            "admin_profile-INITIAL_FORMS": "0",
            "admin_profile-MIN_NUM_FORMS": "0",
            "admin_profile-MAX_NUM_FORMS": "1",
            "admin_profile-0-admin_name": "Filled In",
            "_save": "Save"}, follow=True)

        self.assertEqual(AdminProfile.objects.get(user=user).admin_name,
                         "Filled In")


class UnfinishedAccountsAreReportedTests(TestCase):
    """The inline stops new half-built accounts. This finds the existing ones.

    An account with no profile passes every permission check and then fails the
    moment something needs the profile -- which may be weeks later, and was a
    500 before it was a 409. The check says so where somebody can act on it,
    rather than waiting for the administrator to try to do something.
    """

    def _warnings(self):
        from accounts.checks import accounts_have_their_profiles

        return accounts_have_their_profiles(None)

    def test_an_administrator_without_a_profile_is_reported(self):
        User.objects.create_user(email="unprofiled@example.edu",
                                 password=NEW_PASSWORD, role=User.Role.ADMIN)

        messages = self._warnings()

        self.assertEqual(len(messages), 1)
        self.assertIn("unprofiled@example.edu", messages[0].msg)
        self.assertIn("AdminProfile", messages[0].msg)

    def test_the_report_names_the_command_that_fixes_it(self):
        """An operator reading this should not have to come and ask."""
        User.objects.create_user(email="unprofiled@example.edu",
                                 password=NEW_PASSWORD, role=User.Role.ADMIN)

        self.assertIn("create_admin", self._warnings()[0].hint)

    def test_it_is_a_warning_and_not_an_error(self):
        """A half-built account is a thing to repair, not a reason to refuse to
        start. The deployment still works for everybody else."""
        from django.core.checks import WARNING

        User.objects.create_user(email="unprofiled@example.edu",
                                 password=NEW_PASSWORD, role=User.Role.ADMIN)

        self.assertEqual(self._warnings()[0].level, WARNING)

    def test_students_and_companies_are_reported_too(self):
        """The gap was never only about administrators: the Add User page made
        every role without its profile."""
        User.objects.create_user(email="s@example.edu", password=NEW_PASSWORD,
                                 role=User.Role.STUDENT)
        User.objects.create_user(email="c@example.edu", password=NEW_PASSWORD,
                                 role=User.Role.COMPANY)

        reported = " ".join(m.msg for m in self._warnings())

        self.assertIn("Student", reported)
        self.assertIn("Company", reported)

    def test_a_complete_account_is_not_reported(self):
        from accounts.models import AdminProfile

        user = User.objects.create_user(email="complete@example.edu",
                                        password=NEW_PASSWORD,
                                        role=User.Role.ADMIN)
        AdminProfile.objects.create(user=user, admin_name="Complete")

        self.assertEqual(self._warnings(), [])

    def test_nothing_is_reported_on_an_empty_database(self):
        self.assertEqual(self._warnings(), [])


