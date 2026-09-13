import json
import urllib.parse
import io

from django.core import mail
from rest_framework.serializers import ValidationError
from unittest import mock

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone
from django.urls import reverse
from rest_framework.test import APIClient

from job_listings.models import JobListing
from scrape_jobs.models import (
    JobTitle, MarketRole, MarketRoleAlias, Skill,
)
from .models import (
    PrivacyAuditLog,
    StudentSkill,
    RoleTerminologyFeedback,
    SkillGap,
    Student,
    StudentTargetRole,
    User,
    UserConsent,
)
from .privacy_notice import CURRENT_VERSION
from .serializers import set_student_target_roles


class StudentTargetRoleTests(TestCase):
    """StudentTargetRole is the single writer; everything else derives."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            email="student@university.test", password="Strong1!")
        cls.student = Student.objects.create(user=cls.user, student_name="Student")

        cls.software = MarketRole.objects.create(
            name="Software Engineer", broad_area="Software & Applications")
        cls.data_scientist = MarketRole.objects.create(
            name="Data Scientist", broad_area="Data & AI")

    def held(self):
        return list(StudentTargetRole.objects
                    .filter(student=self.student)
                    .values_list("market_role__name", flat=True))

    def test_target_role_is_written(self):
        set_student_target_roles(self.student, ["Software Engineer"])

        self.assertEqual(self.held(), ["Software Engineer"])

    def test_unknown_role_names_are_rejected(self):
        with self.assertRaises(ValidationError):
            set_student_target_roles(self.student, ["Underwater Basket Weaver"])

    def test_an_invalid_name_never_erases_a_valid_target(self):
        """Validation runs before anything is deleted.

        Writing first meant a typo or a stale client value wiped the student's
        career target and returned 200.
        """
        set_student_target_roles(self.student, ["Software Engineer"])

        with self.assertRaises(ValidationError):
            set_student_target_roles(
                self.student, ["Software Engineer", "Underwater Basket Weaver"])

        self.assertEqual(self.held(), ["Software Engineer"])

    def test_an_inactive_role_cannot_be_targeted(self):
        self.data_scientist.is_active = False
        self.data_scientist.save(update_fields=["is_active"])

        with self.assertRaises(ValidationError):
            set_student_target_roles(self.student, ["Data Scientist"])

    def test_the_object_form_the_picker_sends_is_accepted(self):
        set_student_target_roles(
            self.student, [{"market_role": "Software Engineer"}])

        self.assertEqual(self.held(), ["Software Engineer"])

    def test_setting_targets_replaces_the_previous_ones(self):
        set_student_target_roles(self.student, ["Software Engineer"])
        set_student_target_roles(self.student, ["Data Scientist"])

        self.assertEqual(self.held(), ["Data Scientist"])

    def test_clearing_targets_removes_them(self):
        set_student_target_roles(self.student, ["Software Engineer"])
        set_student_target_roles(self.student, [])

        self.assertEqual(self.held(), [])

    def test_the_same_role_named_twice_yields_one_target(self):
        set_student_target_roles(
            self.student, ["Software Engineer", "Software Engineer"])

        self.assertEqual(self.held(), ["Software Engineer"])

    def test_skill_gap_history_hangs_off_the_role(self):
        set_student_target_roles(self.student, ["Software Engineer"])
        target = StudentTargetRole.objects.get(student=self.student)
        skill = Skill.objects.create(skill_name="Python")
        SkillGap.objects.create(student=self.student, skill=skill, target=target)

        # Dropping the target drops its history: a gap record is about a goal,
        # and this goal is no longer held.
        set_student_target_roles(self.student, [])

        self.assertEqual(SkillGap.objects.filter(student=self.student).count(), 0)


class PrivacyNoticeEndpointTests(TestCase):
    """The notice has to be readable before an account exists."""

    def test_current_notice_is_served_without_authentication(self):
        response = APIClient().get(reverse("privacy_notice_current"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["version"], CURRENT_VERSION)
        self.assertTrue(response.data["effective_date"])
        self.assertTrue(response.data["sections"])

    def test_notice_carries_the_wording_of_both_consents(self):
        response = APIClient().get(reverse("privacy_notice_current"))

        statements = response.data["consent_statements"]
        self.assertIn("PRIVACY_NOTICE_ACKNOWLEDGEMENT", statements)
        self.assertIn("DOCUMENT_VERIFICATION_CONSENT", statements)
        self.assertTrue(response.data["upload_notice"]["acknowledgement"])

    def test_notice_carries_every_text_the_frontend_renders(self):
        # The pages used to hold their own copies of this wording. They now
        # render whatever this endpoint returns, so anything missing here
        # would leave a consent control with no text.
        response = APIClient().get(reverse("privacy_notice_current"))

        self.assertTrue(response.data["summary"])
        for key in ("upload_notice", "transcript_notice"):
            notice = response.data[key]
            self.assertTrue(notice["heading"])
            self.assertTrue(notice["body"])
            self.assertTrue(notice["acknowledgement"])


class DepartmentEndpointTests(TestCase):
    """One list, served, instead of a copy per page."""

    def test_departments_are_served_without_authentication(self):
        response = APIClient().get(reverse("departments"))

        self.assertEqual(response.status_code, 200)
        self.assertIn("Software Engineering", response.data["departments"])

    def test_course_departments_are_a_superset(self):
        response = APIClient().get(reverse("departments"))

        departments = response.data["departments"]
        course_departments = response.data["course_departments"]

        # A course may be "Compulsory"; a student cannot belong to it.
        self.assertTrue(set(departments).issubset(course_departments))
        self.assertIn("Compulsory", course_departments)
        self.assertNotIn("Compulsory", departments)


class DepartmentValidationTests(TestCase):
    """The backend used to accept any string at all."""

    def setUp(self):
        self.client = APIClient()

    def _payload(self, **overrides):
        payload = {
            "email": "dept-student@university.edu",
            "password": "Strong1!pass",
            "confirm_password": "Strong1!pass",
            "role": "STUDENT",
            "name": "Dept Student",
            "department": "Software Engineering",
            "privacy_notice_accepted": True,
            "document_verification_consent": True,
        }
        payload.update(overrides)
        return payload

    def test_registration_refuses_an_unknown_department(self):
        response = self.client.post(
            reverse("register"), self._payload(department="Underwater Basketry"),
            format="json")

        self.assertEqual(response.status_code, 400)
        self.assertIn("department", response.data)
        self.assertFalse(User.objects.exists())

    def test_registration_accepts_a_known_department(self):
        response = self.client.post(reverse("register"), self._payload(), format="json")

        self.assertEqual(response.status_code, 201, response.data)

    def test_a_student_cannot_be_filed_under_a_course_only_department(self):
        # "Compulsory" is a course category, not a department a student is in.
        response = self.client.post(
            reverse("register"), self._payload(department="Compulsory"), format="json")

        self.assertEqual(response.status_code, 400)

    def test_profile_update_refuses_an_unknown_department(self):
        user = User.objects.create_user(
            email="dept-patch@university.edu", password="pw", role="STUDENT")
        Student.objects.create(user=user, student_name="Patcher")
        self.client.force_authenticate(user=user)

        response = self.client.patch(
            reverse("profile"), {"department": "Not A Department"}, format="json")

        self.assertEqual(response.status_code, 400)
        self.assertIn("department", response.data)


class RegistrationConsentTests(TestCase):
    """No account may come into existence without a consent record behind it."""

    def setUp(self):
        self.client = APIClient()
        self.url = reverse("register")

    def _payload(self, **overrides):
        payload = {
            "email": "consent-student@university.edu",
            "password": "Strong1!pass",
            "confirm_password": "Strong1!pass",
            "role": "STUDENT",
            "name": "Consent Student",
            "department": "Software Engineering",
            "matric_number": "S123456",
            "privacy_notice_accepted": True,
            "document_verification_consent": True,
        }
        payload.update(overrides)
        return payload

    def test_registration_records_both_consents(self):
        response = self.client.post(self.url, self._payload(), format="json")

        self.assertEqual(response.status_code, 201, response.data)
        user = User.objects.get(email="consent-student@university.edu")
        consents = UserConsent.objects.filter(user=user)

        self.assertEqual(consents.count(), 2)
        self.assertEqual(
            set(consents.values_list("consent_type", flat=True)),
            {
                UserConsent.ConsentType.PRIVACY_NOTICE_ACKNOWLEDGEMENT,
                UserConsent.ConsentType.DOCUMENT_VERIFICATION_CONSENT,
            },
        )
        for consent in consents:
            self.assertTrue(consent.accepted)
            self.assertIsNotNone(consent.accepted_at)
            self.assertEqual(consent.notice_version, CURRENT_VERSION)
            self.assertEqual(consent.source, UserConsent.Source.SIGNUP)

    def test_cannot_register_without_acknowledging_the_notice(self):
        response = self.client.post(
            self.url, self._payload(privacy_notice_accepted=False), format="json")

        self.assertEqual(response.status_code, 400)
        self.assertIn("privacy_notice_accepted", response.data)
        self.assertFalse(
            User.objects.filter(email="consent-student@university.edu").exists())

    def test_cannot_register_without_document_verification_consent(self):
        response = self.client.post(
            self.url, self._payload(document_verification_consent=False), format="json")

        self.assertEqual(response.status_code, 400)
        self.assertIn("document_verification_consent", response.data)
        self.assertFalse(
            User.objects.filter(email="consent-student@university.edu").exists())

    def test_omitting_the_consent_fields_entirely_is_refused(self):
        payload = self._payload()
        del payload["privacy_notice_accepted"]
        del payload["document_verification_consent"]

        response = self.client.post(self.url, payload, format="json")

        self.assertEqual(response.status_code, 400)
        self.assertFalse(User.objects.exists())

    def test_a_failed_registration_leaves_no_consent_behind(self):
        # Mismatched passwords: the account is never created, so neither is
        # any evidence that its owner agreed to anything.
        response = self.client.post(
            self.url, self._payload(confirm_password="Different1!pass"), format="json")

        self.assertEqual(response.status_code, 400)
        self.assertFalse(UserConsent.objects.exists())

    def test_matric_number_is_stored_on_the_student_profile(self):
        self.client.post(self.url, self._payload(), format="json")

        student = Student.objects.get(user__email="consent-student@university.edu")
        self.assertEqual(student.matric_number, "S123456")

    def test_accepting_consent_is_audited(self):
        self.client.post(self.url, self._payload(), format="json")

        entries = PrivacyAuditLog.objects.filter(
            action=PrivacyAuditLog.Action.CONSENT_ACCEPTED)
        self.assertEqual(entries.count(), 2)
        self.assertEqual(
            entries.first().resource_type, PrivacyAuditLog.ResourceType.CONSENT)

    def test_re_registering_an_unverified_account_records_fresh_consent(self):
        self.client.post(self.url, self._payload(), format="json")
        mail.outbox.clear()

        # The user never clicked the verification link and signs up again.
        # They were shown the notice a second time, so a second act of consent
        # is recorded rather than the first one being rewritten.
        response = self.client.post(self.url, self._payload(), format="json")

        self.assertEqual(response.status_code, 201, response.data)
        user = User.objects.get(email="consent-student@university.edu")
        self.assertEqual(UserConsent.objects.filter(user=user).count(), 4)


class MyConsentsEndpointTests(TestCase):
    """A user can see what they agreed to, and only their own record."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="mine@university.edu", password="pw", role="STUDENT")
        self.other = User.objects.create_user(
            email="theirs@university.edu", password="pw", role="STUDENT")

        for user in (self.user, self.other):
            UserConsent.objects.create(
                user=user,
                consent_type=UserConsent.ConsentType.PRIVACY_NOTICE_ACKNOWLEDGEMENT,
                notice_version=CURRENT_VERSION,
                accepted=True,
                source=UserConsent.Source.SIGNUP,
            )

        self.client = APIClient()

    def test_returns_only_the_requesting_users_consents(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.get(reverse("my_consents"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertTrue(response.data[0]["statement"])

    def test_anonymous_visitor_is_refused(self):
        response = self.client.get(reverse("my_consents"))

        self.assertEqual(response.status_code, 401)


class RolePickerEndpointTests(TestCase):
    """The picker's data source and the two non-canonical affordances."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            email="picker@university.test", password="Strong1!",
            role=User.Role.STUDENT)
        cls.student = Student.objects.create(user=cls.user, student_name="Picker")

        cls.busy = MarketRole.objects.create(
            name="Software Engineer", broad_area="Software & Applications")
        cls.thin = MarketRole.objects.create(
            name="Security Analyst", broad_area="Cybersecurity")

        for index in range(6):
            JobListing.objects.create(
                job_title=f"Software Engineer {index}",
                source_type=JobListing.SourceType.SCRAPED,
                source_url=f"https://example.test/picker-{index}",
                market_role=cls.busy,
                classification_method="EXACT_MARKET_ROLE")

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def roles(self):
        data = self.client.get("/api/scrape-jobs/market-roles/").json()
        return data, {r["name"]: r for a in data["results"] for r in a["roles"]}

    def test_every_role_is_offered_even_with_no_listings(self):
        _data, by_name = self.roles()

        self.assertIn("Security Analyst", by_name,
                      "a role with no adverts is still targetable")
        self.assertIn("Software Engineer", by_name)

    def test_roles_are_grouped_by_broad_area(self):
        data, _by_name = self.roles()

        areas = {area["name"]: [r["name"] for r in area["roles"]]
                 for area in data["results"]}
        self.assertEqual(areas["Software & Applications"], ["Software Engineer"])
        self.assertEqual(areas["Cybersecurity"], ["Security Analyst"])

    def test_no_raw_or_normalized_title_is_offered_as_a_career(self):
        """The picker shows Market Roles only -- never the advert wording."""
        _data, by_name = self.roles()

        self.assertNotIn("Software Engineer 1", by_name)
        self.assertNotIn("software engineer", by_name)

    def test_analysable_flag_reflects_the_evidence_floor(self):
        data, by_name = self.roles()

        self.assertTrue(by_name["Software Engineer"]["analysable"])
        self.assertEqual(by_name["Software Engineer"]["advert_count"], 6)
        self.assertFalse(by_name["Security Analyst"]["analysable"])
        self.assertEqual(by_name["Security Analyst"]["advert_count"], 0)
        self.assertEqual(data["analysable_roles"], 1)

    def test_setting_a_target_from_the_picker_persists_it(self):
        response = self.client.patch(
            "/api/auth/profile/", {"target_roles": ["Software Engineer"]},
            format="json")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            list(self.student.target_roles.values_list(
                "market_role__name", flat=True)),
            ["Software Engineer"])


    def test_browsing_a_role_does_not_save_it(self):
        self.client.get("/api/dashboard/skill-gap/?role=Software%20Engineer")

        self.assertFalse(self.student.target_roles.exists(),
                         "previewing a role must not change the saved target")

    def test_terminology_feedback_records_wording_and_nothing_else(self):
        response = self.client.post(
            "/api/auth/student/role-feedback/",
            {"searched_text": "Prompt Engineer",
             "context_broad_area": "Data & AI"},
            format="json")

        self.assertEqual(response.status_code, 201)
        feedback = RoleTerminologyFeedback.objects.get(student=self.student)
        self.assertEqual(feedback.searched_text, "Prompt Engineer")
        self.assertEqual(feedback.context_broad_area, "Data & AI")
        # No Market Role invented, no target set.
        self.assertFalse(MarketRole.objects.filter(name="Prompt Engineer").exists())
        self.assertFalse(self.student.target_roles.exists())

    def test_empty_terminology_feedback_is_refused(self):
        response = self.client.post(
            "/api/auth/student/role-feedback/", {"searched_text": "   "},
            format="json")

        self.assertEqual(response.status_code, 400)
        self.assertFalse(RoleTerminologyFeedback.objects.exists())

    def test_feedback_endpoint_is_students_only(self):
        company_user = User.objects.create_user(
            email="picker@business.test", password="Strong1!",
            role=User.Role.COMPANY)
        self.client.force_authenticate(company_user)

        response = self.client.post(
            "/api/auth/student/role-feedback/", {"searched_text": "x"},
            format="json")

        self.assertEqual(response.status_code, 403)


class RoleScopedConsentTests(TestCase):
    """Each role is asked for the consents that role actually exercises."""

    def setUp(self):
        self.client = APIClient()
        self.url = reverse("register")

    def _payload(self, role, **overrides):
        payload = {
            "email": f"{role.lower()}-scope@university.edu",
            "password": "Strong1!pass",
            "confirm_password": "Strong1!pass",
            "role": role,
            "name": f"{role.title()} User",
            "privacy_notice_accepted": True,
        }
        if role == "STUDENT":
            payload["department"] = "Software Engineering"
            payload["document_verification_consent"] = True
        payload.update(overrides)
        return payload

    def test_a_student_records_both_consents(self):
        response = self.client.post(self.url, self._payload("STUDENT"), format="json")

        self.assertEqual(response.status_code, 201, response.data)
        user = User.objects.get(email="student-scope@university.edu")
        types = set(UserConsent.objects.filter(user=user)
                    .values_list("consent_type", flat=True))
        self.assertEqual(types, {"PRIVACY_NOTICE_ACKNOWLEDGEMENT",
                                 "DOCUMENT_VERIFICATION_CONSENT"})

    def test_a_company_records_only_the_notice_acknowledgement(self):
        """A company never submits a document for verification, so consent to
        that processing would be permission that is never exercised."""
        response = self.client.post(self.url, self._payload("COMPANY"), format="json")

        self.assertEqual(response.status_code, 201, response.data)
        user = User.objects.get(email="company-scope@university.edu")
        types = set(UserConsent.objects.filter(user=user)
                    .values_list("consent_type", flat=True))
        self.assertEqual(types, {"PRIVACY_NOTICE_ACKNOWLEDGEMENT"})

    def test_a_company_need_not_send_the_document_consent_at_all(self):
        payload = self._payload("COMPANY")
        self.assertNotIn("document_verification_consent", payload)

        self.assertEqual(
            self.client.post(self.url, payload, format="json").status_code, 201)

    def test_a_student_still_cannot_skip_the_document_consent(self):
        response = self.client.post(
            self.url, self._payload("STUDENT", document_verification_consent=False),
            format="json")

        self.assertEqual(response.status_code, 400)
        self.assertIn("document_verification_consent", response.data)
        self.assertFalse(User.objects.exists())

    def test_nobody_can_skip_the_privacy_acknowledgement(self):
        for role in ("STUDENT", "COMPANY"):
            response = self.client.post(
                self.url, self._payload(role, privacy_notice_accepted=False),
                format="json")
            self.assertEqual(response.status_code, 400, role)
            self.assertIn("privacy_notice_accepted", response.data)


class PrivacyNoticeVersioningTests(TestCase):
    """Publishing 1.1 must not disturb what a 1.0 acknowledgement refers to."""

    def test_both_versions_are_available(self):
        from accounts.privacy_notice import NOTICES

        self.assertIn("1.0", NOTICES)
        self.assertIn("1.1", NOTICES)

    def test_the_published_1_0_wording_is_unchanged(self):
        from accounts.privacy_notice import get_notice

        statements = get_notice("1.0")["consent_statements"]
        self.assertEqual(
            statements["PRIVACY_NOTICE_ACKNOWLEDGEMENT"],
            "I have read and understood the MomentumQuest Personal Data Privacy Notice.")

    def test_1_1_carries_its_own_wording(self):
        from accounts.privacy_notice import get_notice

        one_one = get_notice("1.1")
        self.assertEqual(
            one_one["consent_statements"]["PRIVACY_NOTICE_ACKNOWLEDGEMENT"],
            "I have read and understood the MomentumQuest Privacy Notice.")
        self.assertNotEqual(one_one["summary"], get_notice("1.0")["summary"])

    def test_1_1_describes_cv_processing_and_disclosure(self):
        from accounts.privacy_notice import get_notice

        one_one = get_notice("1.1")
        self.assertTrue(one_one["cv_notice"]["acknowledgement"])
        self.assertTrue(one_one["application_disclosure"])
        self.assertIn("CV_PROCESSING_CONSENT", one_one["consent_statements"])
        self.assertIn("APPLICATION_DISCLOSURE_ACKNOWLEDGEMENT",
                      one_one["consent_statements"])

        text = " ".join(
            block.get("text", "") + " ".join(block.get("items", []))
            for section in one_one["sections"] for block in section["blocks"]
        ).lower()
        for topic in ("deleted", "employer", "subject codes", "withdraw"):
            self.assertIn(topic, text, f"1.1 must describe {topic}")

    def test_1_0_claims_nothing_about_cv_processing(self):
        """1.0 never described it, so it must not appear to have."""
        from accounts.privacy_notice import get_notice

        self.assertIsNone(get_notice("1.0")["cv_notice"])
        self.assertEqual(get_notice("1.0")["application_disclosure"], "")

    def test_an_unknown_version_is_an_error_not_a_guess(self):
        from accounts.privacy_notice import get_notice

        with self.assertRaises(KeyError):
            get_notice("9.9")


class NoticeVersionTransitionTests(TestCase):
    """Publishing a new version must not lock existing students out."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="existing@university.edu", password="Strong1!pass",
            role=User.Role.STUDENT, is_active=True, email_verified=True)
        self.student = Student.objects.create(
            user=self.user, student_name="Existing", matric_number="S111111")
        # Acknowledged the previous version, and nothing since.
        UserConsent.objects.create(
            user=self.user,
            consent_type=UserConsent.ConsentType.PRIVACY_NOTICE_ACKNOWLEDGEMENT,
            notice_version="1.0", accepted=True, accepted_at=timezone.now(),
            source=UserConsent.Source.SIGNUP)
        self.client = APIClient()

    def test_an_older_acknowledgement_does_not_block_login(self):
        response = self.client.post(
            reverse("login"),
            {"email": "existing@university.edu", "password": "Strong1!pass"},
            format="json")

        self.assertEqual(response.status_code, 200, response.data)

    def test_an_older_acknowledgement_does_not_block_the_profile(self):
        self.client.force_authenticate(self.user)

        self.assertEqual(self.client.get(reverse("profile")).status_code, 200)

    def test_the_next_document_upload_records_the_current_version(self):
        """The re-acknowledgement is the upload itself.

        Every document function asks at the point of use and records against
        whatever version is current, so a student who last agreed to 1.0
        acknowledges the current notice the next time they submit a document --
        without a separate gate, and without being stopped from logging in.
        """
        from accounts.privacy_notice import CURRENT_VERSION

        self.client.force_authenticate(self.user)
        skill = Skill.objects.create(skill_name="Version Test Skill")

        response = self.client.post(
            "/api/resources/certificates/",
            {"skills": json.dumps([{"skill_id": skill.id}]),
             "cert_url": "https://example.test/c",
             "document_consent_ack": True},
            format="multipart")

        self.assertEqual(response.status_code, 201, response.data)
        latest = UserConsent.objects.filter(
            user=self.user,
            consent_type="DOCUMENT_VERIFICATION_CONSENT").latest("created_at")
        self.assertEqual(latest.notice_version, CURRENT_VERSION)

    def test_the_earlier_acknowledgement_is_left_alone(self):
        """A historical consent must never be rewritten to a newer version."""
        from accounts.privacy_notice import CURRENT_VERSION

        self.client.force_authenticate(self.user)
        skill = Skill.objects.create(skill_name="Untouched Skill")
        self.client.post(
            "/api/resources/certificates/",
            {"skill": skill.id, "cert_url": "https://example.test/c",
             "document_consent_ack": True},
            format="multipart")

        original = UserConsent.objects.get(
            user=self.user, consent_type="PRIVACY_NOTICE_ACKNOWLEDGEMENT")
        self.assertEqual(original.notice_version, "1.0")
        self.assertNotEqual(original.notice_version, CURRENT_VERSION)


class ConsentWithdrawalTests(TestCase):
    """Withdrawal stops future processing. It never erases the record."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="withdraw@university.edu", password="Strong1!pass",
            role=User.Role.STUDENT)
        self.consent = UserConsent.objects.create(
            user=self.user,
            consent_type=UserConsent.ConsentType.DOCUMENT_VERIFICATION_CONSENT,
            notice_version="1.1", accepted=True, accepted_at=timezone.now(),
            source=UserConsent.Source.SIGNUP)

    def test_a_live_consent_authorises_processing(self):
        self.assertTrue(self.consent.is_live)

    def test_withdrawal_stamps_the_row_rather_than_deleting_it(self):
        self.consent.withdrawn_at = timezone.now()
        self.consent.save()

        self.consent.refresh_from_db()
        self.assertFalse(self.consent.is_live)
        # The evidence of what was agreed, and when, survives.
        self.assertTrue(self.consent.accepted)
        self.assertIsNotNone(self.consent.accepted_at)
        self.assertEqual(self.consent.notice_version, "1.1")
        self.assertTrue(UserConsent.objects.filter(pk=self.consent.pk).exists())

    def test_a_never_accepted_consent_is_not_live(self):
        backfilled = UserConsent.objects.create(
            user=self.user,
            consent_type=UserConsent.ConsentType.PRIVACY_NOTICE_ACKNOWLEDGEMENT,
            notice_version="1.0", accepted=False, accepted_at=None,
            source=UserConsent.Source.BACKFILL_PRE_NOTICE)

        self.assertFalse(backfilled.is_live)

    def test_withdrawing_leaves_the_account_intact(self):
        self.consent.withdrawn_at = timezone.now()
        self.consent.save()

        self.user.refresh_from_db()
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())
        self.assertTrue(self.user.is_active)


class WithdrawalServiceTests(TestCase):
    """One entry point, and it brings the consequences with it."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="wd@university.edu", password="Strong1!pass",
            role=User.Role.STUDENT, is_active=True, email_verified=True)
        self.student = Student.objects.create(
            user=self.user, student_name="Withdrawer", matric_number="S333333")
        self.consent = UserConsent.objects.create(
            user=self.user,
            consent_type=UserConsent.ConsentType.DOCUMENT_VERIFICATION_CONSENT,
            notice_version="1.1", accepted=True, accepted_at=timezone.now(),
            source=UserConsent.Source.SIGNUP)
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def _withdraw(self, consent_type="DOCUMENT_VERIFICATION_CONSENT"):
        return self.client.post(
            reverse("withdraw_consent"), {"consent_type": consent_type},
            format="json")

    def test_withdrawal_stamps_the_row_and_keeps_the_history(self):
        response = self._withdraw()

        self.assertEqual(response.status_code, 200, response.data)
        self.consent.refresh_from_db()
        self.assertIsNotNone(self.consent.withdrawn_at)
        self.assertFalse(self.consent.is_live)
        # The evidence of what was agreed, and when, survives.
        self.assertTrue(self.consent.accepted)
        self.assertIsNotNone(self.consent.accepted_at)
        self.assertEqual(self.consent.notice_version, "1.1")

    def test_withdrawal_writes_an_audit_row(self):
        self._withdraw()

        self.assertTrue(PrivacyAuditLog.objects.filter(
            action=PrivacyAuditLog.Action.CONSENT_WITHDRAWN,
            target_user=self.user,
            resource_id=self.consent.pk).exists())

    def test_withdrawal_disables_document_verification(self):
        """The notice says it stops future verification. It must actually."""
        self._withdraw()
        skill = Skill.objects.create(skill_name="Blocked Skill")

        response = self.client.post(
            "/api/resources/certificates/",
            {"skills": json.dumps([{"skill_id": skill.id}]),
             "cert_url": "https://example.test/c",
             "document_consent_ack": True},
            format="multipart")

        self.assertEqual(response.status_code, 400)
        self.assertIn("withdrawn", str(response.data).lower())

    @staticmethod
    def _approved_certificate(skill, consent):
        """An approved certificate evidencing one skill.

        Two rows now, not one: the document and the claim it supports are
        separate facts, and only the claim carries a level.
        """
        from resources.models import Certificate, CertificateSkillEvidence

        certificate = Certificate.objects.create(
            student=consent.user.student_profile,
            verified_status=Certificate.VerifiedStatus.APPROVED,
            upload_consent=consent)
        CertificateSkillEvidence.objects.create(
            certificate=certificate, skill=skill,
            claimed_level="INTERMEDIATE", approved_level="INTERMEDIATE",
            review_status=CertificateSkillEvidence.ReviewStatus.APPROVED)
        return certificate

    def test_withdrawal_removes_skills_left_without_live_evidence(self):
        skill = Skill.objects.create(skill_name="Evidenced Skill")
        StudentSkill.objects.create(
            student=self.student, skill=skill, skill_level="INTERMEDIATE")
        self._approved_certificate(skill, self.consent)

        response = self._withdraw()

        self.assertEqual(response.data["skills_removed"], 1)
        self.assertFalse(StudentSkill.objects.filter(
            student=self.student, skill=skill).exists())

    def test_a_skill_with_other_live_evidence_survives(self):
        skill = Skill.objects.create(skill_name="Doubly Evidenced")
        StudentSkill.objects.create(
            student=self.student, skill=skill, skill_level="INTERMEDIATE")
        self._approved_certificate(skill, self.consent)
        # A second certificate under a consent that is still live.
        other = UserConsent.objects.create(
            user=self.user,
            consent_type=UserConsent.ConsentType.DOCUMENT_VERIFICATION_CONSENT,
            notice_version="1.1", accepted=True, accepted_at=timezone.now(),
            source=UserConsent.Source.CERTIFICATE_UPLOAD)
        self._approved_certificate(skill, other)

        # Withdrawing only the first must leave the skill standing.
        from accounts.withdrawal import withdraw_consent
        withdraw_consent(self.consent)

        self.assertTrue(StudentSkill.objects.filter(
            student=self.student, skill=skill).exists())

    def test_a_skill_with_no_evidence_row_is_left_alone(self):
        """Skills predating evidence tracking must not be guessed away."""
        skill = Skill.objects.create(skill_name="Unevidenced Skill")
        StudentSkill.objects.create(
            student=self.student, skill=skill, skill_level="BEGINNER")

        self._withdraw()

        self.assertTrue(StudentSkill.objects.filter(
            student=self.student, skill=skill).exists())

    def test_withdrawing_does_not_delete_the_account(self):
        self._withdraw()

        self.user.refresh_from_db()
        self.assertTrue(self.user.is_active)
        self.assertTrue(Student.objects.filter(pk=self.student.pk).exists())

    def test_withdrawing_twice_is_refused(self):
        self._withdraw()

        response = self._withdraw()

        self.assertEqual(response.status_code, 400)

    def test_the_privacy_acknowledgement_cannot_be_withdrawn(self):
        """It records being shown the notice, which stays true."""
        response = self._withdraw("PRIVACY_NOTICE_ACKNOWLEDGEMENT")

        self.assertEqual(response.status_code, 400)
        self.assertIn("consent_type", response.data)

    def test_an_unknown_consent_type_is_refused(self):
        response = self._withdraw("SOMETHING_ELSE")

        self.assertEqual(response.status_code, 400)

    def test_a_user_cannot_withdraw_for_anybody_else(self):
        """The endpoint takes no user parameter at all."""
        stranger = User.objects.create_user(
            email="stranger-wd@university.edu", password="Strong1!pass",
            role=User.Role.STUDENT)
        stranger_consent = UserConsent.objects.create(
            user=stranger,
            consent_type=UserConsent.ConsentType.DOCUMENT_VERIFICATION_CONSENT,
            notice_version="1.1", accepted=True, accepted_at=timezone.now(),
            source=UserConsent.Source.SIGNUP)

        self._withdraw()

        stranger_consent.refresh_from_db()
        self.assertIsNone(stranger_consent.withdrawn_at)

    def test_an_unauthenticated_caller_is_refused(self):
        self.client.force_authenticate(None)

        response = self._withdraw()

        self.assertIn(response.status_code, (401, 403))

    def test_re_consenting_after_withdrawal_restores_the_function(self):
        """Consent is append-only, so 'do they consent' is about the latest row."""
        self._withdraw()
        UserConsent.objects.create(
            user=self.user,
            consent_type=UserConsent.ConsentType.DOCUMENT_VERIFICATION_CONSENT,
            notice_version="1.1", accepted=True, accepted_at=timezone.now(),
            source=UserConsent.Source.CERTIFICATE_UPLOAD)

        skill = Skill.objects.create(skill_name="Restored Skill")
        response = self.client.post(
            "/api/resources/certificates/",
            {"skills": json.dumps([{"skill_id": skill.id}]),
             "cert_url": "https://example.test/c",
             "document_consent_ack": True},
            format="multipart")

        self.assertEqual(response.status_code, 201, response.data)


class ConsentRestoreTests(TestCase):
    """Withdrawal must not be a one-way door.

    The refusal message told students to "restore it in Settings" and no such
    path existed, so a single click disabled document verification forever.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            email="restore@university.test", password="Strong1!",
            role=User.Role.STUDENT)
        self.student = Student.objects.create(user=self.user, student_name="R")
        self.consent = UserConsent.objects.create(
            user=self.user,
            consent_type=UserConsent.ConsentType.DOCUMENT_VERIFICATION_CONSENT,
            notice_version="1.1", accepted=True, accepted_at=timezone.now(),
            source=UserConsent.Source.CERTIFICATE_UPLOAD)
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def latest(self):
        return (UserConsent.objects
                .filter(user=self.user,
                        consent_type=UserConsent.ConsentType.DOCUMENT_VERIFICATION_CONSENT)
                .order_by("-created_at").first())

    def withdraw(self):
        return self.client.post(
            "/api/auth/me/consents/withdraw/",
            {"consent_type": "DOCUMENT_VERIFICATION_CONSENT"}, format="json")

    def restore(self):
        return self.client.post(
            "/api/auth/me/consents/restore/",
            {"consent_type": "DOCUMENT_VERIFICATION_CONSENT"}, format="json")

    def test_a_withdrawn_consent_can_be_given_again(self):
        self.withdraw()
        self.assertFalse(self.latest().is_live)

        response = self.restore()

        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(self.latest().is_live)

    def test_restoring_appends_rather_than_editing_the_withdrawal(self):
        """The withdrawal is a fact about what the student decided. Rewriting
        it to look like it never happened is what the table exists to prevent."""
        self.withdraw()
        withdrawn = self.latest()

        self.restore()
        withdrawn.refresh_from_db()

        self.assertIsNotNone(withdrawn.withdrawn_at)
        self.assertNotEqual(self.latest().pk, withdrawn.pk)
        self.assertEqual(self.latest().source,
                         UserConsent.Source.SETTINGS_RESTORE)

    def test_uploading_works_again_after_a_restore(self):
        skill = Skill.objects.create(skill_name="Python")
        self.withdraw()
        blocked = self.client.post(
            "/api/resources/certificates/",
            {"skills": json.dumps([{"skill_id": skill.id}]),
             "cert_url": "https://example.test/c", "document_consent_ack": True},
            format="multipart")
        self.assertEqual(blocked.status_code, 400)

        self.restore()

        allowed = self.client.post(
            "/api/resources/certificates/",
            {"skills": json.dumps([{"skill_id": skill.id}]),
             "cert_url": "https://example.test/c2", "document_consent_ack": True},
            format="multipart")
        self.assertEqual(allowed.status_code, 201, allowed.data)

    def test_restoring_an_active_consent_is_refused(self):
        response = self.restore()

        self.assertEqual(response.status_code, 400)

    def test_the_reply_says_skills_are_not_restored(self):
        self.withdraw()

        detail = self.restore().data["detail"].lower()

        self.assertIn("not restored", detail)

    def test_a_student_cannot_restore_for_somebody_else(self):
        other = User.objects.create_user(
            email="other@university.test", password="Strong1!",
            role=User.Role.STUDENT)
        Student.objects.create(user=other, student_name="O")
        self.withdraw()

        self.restore()

        self.assertFalse(UserConsent.objects.filter(user=other).exists())

    def test_the_acknowledgement_is_not_withdrawable_or_restorable(self):
        response = self.client.post(
            "/api/auth/me/consents/restore/",
            {"consent_type": "PRIVACY_NOTICE_ACKNOWLEDGEMENT"}, format="json")

        self.assertEqual(response.status_code, 400)


class PreNoticeAccountUploadTests(TestCase):
    """An account that predates the notice must still be able to consent.

    The backfill wrote accepted=False rows to record honestly that these
    accounts were never asked. The upload guard read "not live" as "withdrawn"
    and refused them permanently -- telling a student they had withdrawn a
    consent nobody had ever offered them, with no way to give it.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            email="prenotice@university.test", password="Strong1!",
            role=User.Role.STUDENT)
        self.student = Student.objects.create(user=self.user, student_name="P")
        self.skill = Skill.objects.create(skill_name="Python")
        # Exactly what accounts/0006 writes for a pre-notice account.
        UserConsent.objects.create(
            user=self.user,
            consent_type=UserConsent.ConsentType.DOCUMENT_VERIFICATION_CONSENT,
            notice_version="1.0", accepted=False, accepted_at=None,
            source=UserConsent.Source.BACKFILL_PRE_NOTICE)
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def upload(self):
        return self.client.post(
            "/api/resources/certificates/",
            {"skills": json.dumps([{"skill_id": self.skill.id}]),
             "cert_url": "https://example.test/c",
             "document_consent_ack": True},
            format="multipart")

    def test_a_pre_notice_account_can_upload_by_acknowledging(self):
        response = self.upload()

        self.assertEqual(response.status_code, 201, response.data)

    def test_the_acknowledgement_becomes_a_real_consent_row(self):
        self.upload()

        latest = (UserConsent.objects
                  .filter(user=self.user,
                          consent_type=UserConsent.ConsentType.DOCUMENT_VERIFICATION_CONSENT)
                  .order_by("-created_at").first())
        self.assertTrue(latest.accepted)
        self.assertTrue(latest.is_live)
        self.assertEqual(latest.source, UserConsent.Source.CERTIFICATE_UPLOAD)

    def test_the_backfill_row_is_left_exactly_as_it_was(self):
        """It records that the account predates the notice, which stays true."""
        self.upload()

        backfill = UserConsent.objects.get(
            user=self.user, source=UserConsent.Source.BACKFILL_PRE_NOTICE,
            consent_type=UserConsent.ConsentType.DOCUMENT_VERIFICATION_CONSENT)
        self.assertFalse(backfill.accepted)
        self.assertIsNone(backfill.withdrawn_at)

    def test_an_upload_without_the_acknowledgement_is_still_refused(self):
        response = self.client.post(
            "/api/resources/certificates/",
            {"skills": json.dumps([{"skill_id": self.skill.id}]),
             "cert_url": "https://example.test/c",
             "document_consent_ack": False},
            format="multipart")

        self.assertEqual(response.status_code, 400)


#: Rates small enough for a test to reach. Not override_settings: DRF binds
#: SimpleRateThrottle.THROTTLE_RATES as a class attribute when the module is
#: imported, so replacing the setting afterwards leaves the throttle reading
#: the dict it already holds. Patching that attribute is what actually takes
#: effect.
TEST_THROTTLE_RATES = {
    "login": "3/min",
    "register": "2/hour",
    "password_reset": "2/hour",
    "token_confirm": "2/hour",
    "verify_email": "2/hour",
}


class AuthThrottleTests(TestCase):
    """The public auth endpoints must refuse a flood.

    Throttling is switched off under the test runner -- history is keyed by
    scope and client IP, and every test shares 127.0.0.1, so one bucket would
    accumulate across the whole suite and fail unrelated tests by exhaustion.
    These turn it back on deliberately, at rates small enough to reach.
    """

    def setUp(self):
        from rest_framework.throttling import SimpleRateThrottle

        patcher = mock.patch.dict(SimpleRateThrottle.THROTTLE_RATES,
                                  TEST_THROTTLE_RATES)
        patcher.start()
        self.addCleanup(patcher.stop)
        # Throttle history lives in the cache and is not part of the test
        # transaction, so it survives a rollback and would leak into the next
        # test.
        cache.clear()
        self.addCleanup(cache.clear)
        self.client = APIClient()

    def test_login_is_throttled_after_the_rate_is_exhausted(self):
        """Wrong credentials still consume the allowance.

        Counting only successes would leave the guessing unlimited, which is
        the case this exists for.
        """
        payload = {"email": "nobody@example.com", "password": "wrong-password"}

        statuses = [self.client.post(reverse("login"), payload, format="json")
                    .status_code for _ in range(4)]

        self.assertEqual(statuses[:3], [401, 401, 401])
        self.assertEqual(statuses[3], 429)

    def test_registration_is_throttled(self):
        def register(n):
            return self.client.post(reverse("register"), {
                "email": f"person{n}@example.com",
                "password": "Str0ng!Passw0rd",
                "confirm_password": "Str0ng!Passw0rd",
                "name": f"Person {n}",
                "role": "STUDENT",
                "privacy_notice_accepted": True,
            }, format="json").status_code

        first, second, third = register(1), register(2), register(3)

        self.assertNotEqual(first, 429)
        self.assertNotEqual(second, 429)
        self.assertEqual(third, 429)

    def test_password_reset_is_throttled(self):
        """It sends mail to an address the caller names.

        Unthrottled, that is a way to have the system mail a stranger
        repeatedly, quite apart from any account risk.
        """
        url = reverse("password_reset")
        payload = {"email": "someone@example.com"}

        statuses = [self.client.post(url, payload, format="json").status_code
                    for _ in range(3)]

        self.assertEqual(statuses[2], 429)

    def test_reset_confirm_is_throttled_against_token_guessing(self):
        url = reverse("password_reset_confirm")
        payload = {"uid": "abc", "token": "guess", "new_password": "Str0ng!Pw1"}

        statuses = [self.client.post(url, payload, format="json").status_code
                    for _ in range(3)]

        self.assertEqual(statuses[2], 429)

    def test_scopes_do_not_share_one_allowance(self):
        """A scope per endpoint, not one bucket for all of them.

        Exhausting login must not lock a legitimate visitor out of
        registration, which is what a single shared scope would do.
        """
        for _ in range(4):
            self.client.post(reverse("login"),
                             {"email": "a@b.com", "password": "x"},
                             format="json")

        response = self.client.post(reverse("register"), {
            "email": "fresh@example.com",
            "password": "Str0ng!Passw0rd",
            "confirm_password": "Str0ng!Passw0rd",
            "name": "Fresh",
            "role": "STUDENT",
            "privacy_notice_accepted": True,
        }, format="json")

        self.assertNotEqual(response.status_code, 429)


class ThrottleConfigurationTests(TestCase):
    """Every public auth view must actually carry a scope.

    A ScopedRateThrottle on a view with no throttle_scope silently does
    nothing, so the configuration is the whole control and a missing attribute
    is invisible at runtime.
    """

    def test_every_public_auth_view_declares_a_scope(self):
        from .views import (
            CustomTokenObtainPairView, EmailChangeConfirmView,
            EmailChangeRequestView, PasswordChangeConfirmView,
            PasswordChangeView, PasswordResetConfirmView,
            PasswordResetRequestView, RegisterView, VerifyEmailView,
        )

        for view in (RegisterView, CustomTokenObtainPairView, VerifyEmailView,
                     PasswordResetRequestView, PasswordResetConfirmView,
                     EmailChangeRequestView, EmailChangeConfirmView,
                     PasswordChangeView, PasswordChangeConfirmView):
            with self.subTest(view=view.__name__):
                self.assertTrue(getattr(view, "throttle_scope", ""),
                                f"{view.__name__} has no throttle_scope")

    def test_every_declared_scope_resolves_to_a_rate_at_runtime(self):
        """A scope with no rate does not fall back -- it raises.

        ScopedRateThrottle.get_rate() raises ImproperlyConfigured for a scope
        it cannot find, so a throttle_scope added without its rate turns that
        endpoint into a 500 rather than leaving it unthrottled. The scope and
        the rate live in different files, so nothing else catches the mismatch.

        Resolved through the throttle class itself rather than by reading the
        settings dict, because that is the lookup that actually runs.
        """
        from rest_framework.throttling import ScopedRateThrottle

        from .views import (
            CustomTokenObtainPairView, EmailChangeConfirmView,
            EmailChangeRequestView, PasswordChangeConfirmView,
            PasswordChangeView, PasswordResetConfirmView,
            PasswordResetRequestView, RegisterView, VerifyEmailView,
        )

        for view in (RegisterView, CustomTokenObtainPairView, VerifyEmailView,
                     PasswordResetRequestView, PasswordResetConfirmView,
                     EmailChangeRequestView, EmailChangeConfirmView,
                     PasswordChangeView, PasswordChangeConfirmView):
            with self.subTest(view=view.__name__):
                throttle = ScopedRateThrottle()
                throttle.scope = view.throttle_scope
                self.assertTrue(throttle.get_rate())

    def test_the_shipped_rates_cover_every_scope_the_views_declare(self):
        """The production dict, not the relaxed one the test runner installs.

        Tests run against permissive rates, so a scope missing from the real
        configuration would otherwise only be discovered in production.
        """
        from config.settings import _THROTTLE_RATES

        from .views import (
            CustomTokenObtainPairView, EmailChangeConfirmView,
            EmailChangeRequestView, PasswordChangeConfirmView,
            PasswordChangeView, PasswordResetConfirmView,
            PasswordResetRequestView, RegisterView, VerifyEmailView,
        )

        for view in (RegisterView, CustomTokenObtainPairView, VerifyEmailView,
                     PasswordResetRequestView, PasswordResetConfirmView,
                     EmailChangeRequestView, EmailChangeConfirmView,
                     PasswordChangeView, PasswordChangeConfirmView):
            with self.subTest(view=view.__name__):
                self.assertIn(view.throttle_scope, _THROTTLE_RATES)


class HTTPSEmailBackendTests(TestCase):
    """Mail must not depend on an SMTP port a free host may block.

    The failure this replaces is quiet: send_mail hangs until timeout, the
    registration request still returns 201, and the student never receives the
    verification link. Nothing in the response says so.

    The HTTP boundary is mocked -- these test the payload and the failure
    handling, not the provider.
    """

    def _backend(self, **kwargs):
        from config.email import ResendEmailBackend

        with override_settings(EMAIL_API_KEY="test-key"):
            return ResendEmailBackend(**kwargs)

    def _message(self, **kwargs):
        from django.core.mail import EmailMessage

        defaults = {
            "subject": "Verify your MomentumQuest account",
            "body": "Open this link to verify.",
            "from_email": "MomentumQuest <no-reply@example.edu>",
            "to": ["student@example.edu"],
        }
        defaults.update(kwargs)
        return EmailMessage(**defaults)

    def test_a_message_is_posted_as_json_to_the_provider(self):
        import json
        from unittest.mock import MagicMock, patch

        captured = {}

        class Response:
            status = 200
            def __enter__(self): return self
            def __exit__(self, *a): return False

        def fake_urlopen(request, timeout=None):
            captured["url"] = request.full_url
            captured["headers"] = dict(request.headers)
            captured["body"] = json.loads(request.data.decode("utf-8"))
            return Response()

        backend = self._backend()
        with patch("urllib.request.urlopen", fake_urlopen):
            sent = backend.send_messages([self._message()])

        self.assertEqual(sent, 1)
        self.assertTrue(captured["url"].startswith("https://"))
        self.assertEqual(captured["body"]["to"], ["student@example.edu"])
        self.assertEqual(captured["body"]["subject"],
                         "Verify your MomentumQuest account")

    def test_the_api_key_is_sent_as_a_bearer_token_and_not_in_the_url(self):
        """A key in a query string lands in provider access logs."""
        from unittest.mock import patch

        class Response:
            status = 200
            def __enter__(self): return self
            def __exit__(self, *a): return False

        captured = {}

        def fake_urlopen(request, timeout=None):
            captured["url"] = request.full_url
            captured["auth"] = request.get_header("Authorization")
            return Response()

        backend = self._backend()
        with patch("urllib.request.urlopen", fake_urlopen):
            backend.send_messages([self._message()])

        self.assertEqual(captured["auth"], "Bearer test-key")
        self.assertNotIn("test-key", captured["url"])

    def test_a_provider_failure_reports_zero_sent_rather_than_raising(self):
        """Mail is best-effort around a request that already succeeded.

        Raising would turn "the verification email is late" into "the account
        was not created", which is strictly worse for the student.
        """
        from unittest.mock import patch

        backend = self._backend()
        with patch("urllib.request.urlopen",
                   side_effect=OSError("connection refused")):
            sent = backend.send_messages([self._message()])

        self.assertEqual(sent, 0)

    def test_a_missing_api_key_is_refused_at_construction(self):
        """Not at the first send, which would be during a registration."""
        from django.core.exceptions import ImproperlyConfigured

        from config.email import ResendEmailBackend

        with override_settings(EMAIL_API_KEY=""):
            with self.assertRaises(ImproperlyConfigured):
                ResendEmailBackend()

    def test_an_html_alternative_is_forwarded_when_present(self):
        from unittest.mock import patch

        from django.core.mail import EmailMultiAlternatives

        class Response:
            status = 200
            def __enter__(self): return self
            def __exit__(self, *a): return False

        captured = {}

        def fake_urlopen(request, timeout=None):
            import json
            captured.update(json.loads(request.data.decode("utf-8")))
            return Response()

        message = EmailMultiAlternatives(
            subject="s", body="plain", from_email="a@b.c", to=["d@e.f"])
        message.attach_alternative("<p>rich</p>", "text/html")

        backend = self._backend()
        with patch("urllib.request.urlopen", fake_urlopen):
            backend.send_messages([message])

        self.assertEqual(captured["text"], "plain")
        self.assertEqual(captured["html"], "<p>rich</p>")

    def test_sending_nothing_is_not_an_error(self):
        self.assertEqual(self._backend().send_messages([]), 0)


class GmailApiEmailBackendTests(TestCase):
    """Mail over the Gmail API, not SMTP.

    Same reason as the Resend backend: outbound SMTP ports are commonly blocked
    on free hosting, and the failure is silent -- send_mail waits for a
    connection that never opens, the registration request still returns 201, and
    the verification link never arrives.

    Nothing here contacts Google. Both endpoints are faked, so these test this
    project's code: the payload shape, the token exchange, and what happens to a
    student's registration when delivery fails.
    """

    #: No sender setting: Gmail sends as the account the refresh token belongs
    #: to, and DEFAULT_FROM_EMAIL is the only sender the application configures.
    CREDENTIALS = {
        "GMAIL_CLIENT_ID": "test-client-id",
        "GMAIL_CLIENT_SECRET": "test-client-secret",
        "GMAIL_REFRESH_TOKEN": "test-refresh-token",
        "DEFAULT_FROM_EMAIL": "MomentumQuest <system@example.edu>",
    }

    # ---------------------------------------------------------------- helpers

    def _backend(self, **kwargs):
        from config.email import GmailApiEmailBackend

        with override_settings(**self.CREDENTIALS):
            return GmailApiEmailBackend(**kwargs)

    def _message(self, **kwargs):
        from django.core.mail import EmailMessage

        defaults = {
            "subject": "Verify your MomentumQuest account",
            "body": "Open this link to verify.",
            "from_email": "MomentumQuest <system@example.edu>",
            "to": ["student@example.edu"],
        }
        defaults.update(kwargs)
        return EmailMessage(**defaults)

    def _fake_transport(self, token_status=200, send_status=200,
                        token_body=None, send_error=None):
        """Stand in for both endpoints, recording what was asked of each.

        Returns (calls, urlopen). `calls` accumulates one dict per request so a
        test can assert on the payload rather than only on the outcome.
        """
        import json as _json

        calls = []

        class Response:
            def __init__(self, status, body=b"{}"):
                self.status = status
                self._body = body

            def read(self):
                return self._body

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        def urlopen(request, timeout=None):
            entry = {
                "url": request.full_url,
                "method": request.method,
                "headers": dict(request.headers),
                "raw_body": request.data,
            }
            calls.append(entry)

            if "oauth2.googleapis.com" in request.full_url:
                entry["form"] = dict(urllib.parse.parse_qsl(
                    request.data.decode("utf-8")))
                body = token_body if token_body is not None else {
                    "access_token": "test-access-token",
                    "expires_in": 3600,
                    "token_type": "Bearer",
                }
                return Response(token_status, _json.dumps(body).encode("utf-8"))

            entry["json"] = _json.loads(request.data.decode("utf-8"))
            if send_error is not None:
                raise send_error
            return Response(send_status)

        return calls, urlopen

    # ------------------------------------------------------- the DRF contract

    def test_an_empty_list_sends_nothing_and_returns_zero(self):
        """Django calls this with an empty list; it must not cost a token."""
        from unittest.mock import patch

        backend = self._backend()
        with patch("urllib.request.urlopen") as urlopen:
            self.assertEqual(backend.send_messages([]), 0)

        urlopen.assert_not_called()

    def test_the_count_returned_is_the_number_accepted(self):
        from unittest.mock import patch

        backend = self._backend()
        _calls, urlopen = self._fake_transport()
        messages = [self._message(to=[f"s{n}@example.edu"]) for n in range(3)]

        with patch("urllib.request.urlopen", urlopen):
            self.assertEqual(backend.send_messages(messages), 3)

    def test_one_token_is_fetched_for_the_whole_batch(self):
        """A token per message would be an extra round trip per message."""
        from unittest.mock import patch

        backend = self._backend()
        calls, urlopen = self._fake_transport()
        messages = [self._message(to=[f"s{n}@example.edu"]) for n in range(3)]

        with patch("urllib.request.urlopen", urlopen):
            backend.send_messages(messages)

        token_calls = [c for c in calls if "oauth2" in c["url"]]
        send_calls = [c for c in calls if "gmail.googleapis" in c["url"]]
        self.assertEqual((len(token_calls), len(send_calls)), (1, 3))

    def test_a_message_with_no_recipient_is_not_sent(self):
        from unittest.mock import patch

        backend = self._backend()
        calls, urlopen = self._fake_transport()

        with patch("urllib.request.urlopen", urlopen):
            sent = backend.send_messages([self._message(to=[])])

        self.assertEqual(sent, 0)
        self.assertEqual([c for c in calls if "gmail.googleapis" in c["url"]], [])

    # ------------------------------------------------------------ credentials

    def test_a_missing_client_id_is_refused_at_construction(self):
        """Not at the first send, which would be during a registration."""
        from django.core.exceptions import ImproperlyConfigured

        from config.email import GmailApiEmailBackend

        with override_settings(**{**self.CREDENTIALS, "GMAIL_CLIENT_ID": ""}):
            with self.assertRaises(ImproperlyConfigured) as caught:
                GmailApiEmailBackend()

        self.assertIn("GMAIL_CLIENT_ID", str(caught.exception))

    def test_a_missing_client_secret_is_refused(self):
        from django.core.exceptions import ImproperlyConfigured

        from config.email import GmailApiEmailBackend

        with override_settings(**{**self.CREDENTIALS,
                                  "GMAIL_CLIENT_SECRET": ""}):
            with self.assertRaises(ImproperlyConfigured) as caught:
                GmailApiEmailBackend()

        self.assertIn("GMAIL_CLIENT_SECRET", str(caught.exception))

    def test_a_missing_refresh_token_is_refused(self):
        from django.core.exceptions import ImproperlyConfigured

        from config.email import GmailApiEmailBackend

        with override_settings(**{**self.CREDENTIALS,
                                  "GMAIL_REFRESH_TOKEN": ""}):
            with self.assertRaises(ImproperlyConfigured) as caught:
                GmailApiEmailBackend()

        self.assertIn("GMAIL_REFRESH_TOKEN", str(caught.exception))

    def test_the_refusal_names_the_settings_but_never_their_values(self):
        """These messages reach deployment logs and get pasted into chat."""
        from django.core.exceptions import ImproperlyConfigured

        from config.email import GmailApiEmailBackend

        with override_settings(**{**self.CREDENTIALS, "GMAIL_CLIENT_ID": ""}):
            with self.assertRaises(ImproperlyConfigured) as caught:
                GmailApiEmailBackend()

        message = str(caught.exception)
        self.assertNotIn("test-client-secret", message)
        self.assertNotIn("test-refresh-token", message)

    def test_fail_silently_allows_construction_without_credentials(self):
        """Django builds a backend in places that must not raise."""
        from config.email import GmailApiEmailBackend

        with override_settings(GMAIL_CLIENT_ID="", GMAIL_CLIENT_SECRET="",
                               GMAIL_REFRESH_TOKEN="", DEFAULT_FROM_EMAIL=""):
            backend = GmailApiEmailBackend(fail_silently=True)

        self.assertEqual(backend.send_messages([]), 0)

    # ---------------------------------------------------------------- token

    def test_the_token_request_is_a_refresh_token_grant(self):
        from unittest.mock import patch

        backend = self._backend()
        calls, urlopen = self._fake_transport()

        with patch("urllib.request.urlopen", urlopen):
            backend.send_messages([self._message()])

        token_call = next(c for c in calls if "oauth2" in c["url"])
        self.assertEqual(token_call["url"],
                         "https://oauth2.googleapis.com/token")
        self.assertEqual(token_call["form"]["grant_type"], "refresh_token")
        self.assertEqual(token_call["form"]["refresh_token"],
                         "test-refresh-token")
        self.assertEqual(token_call["headers"]["Content-type"],
                         "application/x-www-form-urlencoded")

    def test_the_access_token_is_used_as_a_bearer_token(self):
        from unittest.mock import patch

        backend = self._backend()
        calls, urlopen = self._fake_transport()

        with patch("urllib.request.urlopen", urlopen):
            backend.send_messages([self._message()])

        send_call = next(c for c in calls if "gmail.googleapis" in c["url"])
        self.assertEqual(send_call["headers"]["Authorization"],
                         "Bearer test-access-token")

    def test_a_failed_token_exchange_sends_nothing(self):
        """Attempting the send would fail anyway, with a worse message."""
        from unittest.mock import patch

        backend = self._backend()
        # A revoked or expired refresh token answers 400 with invalid_grant.
        calls, urlopen = self._fake_transport(token_status=400)

        with patch("urllib.request.urlopen", urlopen):
            sent = backend.send_messages([self._message()])

        self.assertEqual(sent, 0)
        self.assertEqual([c for c in calls if "gmail.googleapis" in c["url"]], [])

    def test_a_token_response_without_a_token_is_treated_as_failure(self):
        from unittest.mock import patch

        backend = self._backend()
        calls, urlopen = self._fake_transport(token_body={"expires_in": 3600})

        with patch("urllib.request.urlopen", urlopen):
            sent = backend.send_messages([self._message()])

        self.assertEqual(sent, 0)
        self.assertEqual([c for c in calls if "gmail.googleapis" in c["url"]], [])

    # ------------------------------------------------------------------ send

    def test_the_send_request_goes_to_the_gmail_messages_send_endpoint(self):
        from unittest.mock import patch

        backend = self._backend()
        calls, urlopen = self._fake_transport()

        with patch("urllib.request.urlopen", urlopen):
            backend.send_messages([self._message()])

        send_call = next(c for c in calls if "gmail.googleapis" in c["url"])
        self.assertEqual(
            send_call["url"],
            "https://gmail.googleapis.com/gmail/v1/users/me/messages/send")
        self.assertEqual(send_call["method"], "POST")

    def test_the_payload_is_django_s_own_mime_message_base64url_encoded(self):
        """The reason this backend does not rebuild the message itself.

        Reassembling subject, body and alternatives into a provider's JSON shape
        is where parts get silently dropped. Handing over Django's MIME bytes
        means To, Cc, Bcc, Reply-To and every part survive untouched.
        """
        import base64
        from unittest.mock import patch

        backend = self._backend()
        calls, urlopen = self._fake_transport()
        message = self._message(cc=["tutor@example.edu"],
                                reply_to=["help@example.edu"])

        with patch("urllib.request.urlopen", urlopen):
            backend.send_messages([message])

        send_call = next(c for c in calls if "gmail.googleapis" in c["url"])
        self.assertEqual(list(send_call["json"]), ["raw"])

        mime = base64.urlsafe_b64decode(
            send_call["json"]["raw"]).decode("utf-8", "replace")
        self.assertIn("student@example.edu", mime)
        self.assertIn("tutor@example.edu", mime)
        self.assertIn("help@example.edu", mime)
        self.assertIn("Open this link to verify.", mime)

    def test_the_subject_survives_the_mime_round_trip(self):
        import base64
        from email import message_from_bytes
        from unittest.mock import patch

        backend = self._backend()
        calls, urlopen = self._fake_transport()

        with patch("urllib.request.urlopen", urlopen):
            backend.send_messages([self._message()])

        send_call = next(c for c in calls if "gmail.googleapis" in c["url"])
        parsed = message_from_bytes(
            base64.urlsafe_b64decode(send_call["json"]["raw"]))
        self.assertEqual(parsed["Subject"],
                         "Verify your MomentumQuest account")

    def test_an_html_alternative_survives_mime_construction(self):
        import base64
        from email import message_from_bytes
        from unittest.mock import patch

        from django.core.mail import EmailMultiAlternatives

        backend = self._backend()
        calls, urlopen = self._fake_transport()
        message = EmailMultiAlternatives(
            subject="Reset your password", body="Plain text version",
            from_email="MomentumQuest <system@example.edu>",
            to=["student@example.edu"])
        message.attach_alternative("<p>Rich version</p>", "text/html")

        with patch("urllib.request.urlopen", urlopen):
            backend.send_messages([message])

        send_call = next(c for c in calls if "gmail.googleapis" in c["url"])
        parsed = message_from_bytes(
            base64.urlsafe_b64decode(send_call["json"]["raw"]))

        self.assertTrue(parsed.is_multipart())
        types = {part.get_content_type() for part in parsed.walk()}
        self.assertIn("text/plain", types)
        self.assertIn("text/html", types)

    def test_an_attachment_survives_mime_construction(self):
        import base64
        from email import message_from_bytes
        from unittest.mock import patch

        backend = self._backend()
        calls, urlopen = self._fake_transport()
        message = self._message()
        message.attach("notes.txt", b"attached bytes", "text/plain")

        with patch("urllib.request.urlopen", urlopen):
            backend.send_messages([message])

        send_call = next(c for c in calls if "gmail.googleapis" in c["url"])
        parsed = message_from_bytes(
            base64.urlsafe_b64decode(send_call["json"]["raw"]))
        filenames = {p.get_filename() for p in parsed.walk()}
        self.assertIn("notes.txt", filenames)

    # --------------------------------------------------------------- failure

    def test_a_gmail_rejection_reports_zero_rather_than_raising(self):
        """Mail is best-effort around a request that already succeeded.

        Raising would turn "the verification email is late" into "the account
        was not created", which is strictly worse for the student.
        """
        import urllib.error
        from unittest.mock import patch

        backend = self._backend()
        _calls, urlopen = self._fake_transport(
            send_error=urllib.error.HTTPError(
                "https://gmail.googleapis.com", 403,
                "Forbidden", {}, io.BytesIO(b'{"error": "insufficient scope"}')))

        with patch("urllib.request.urlopen", urlopen):
            sent = backend.send_messages([self._message()])

        self.assertEqual(sent, 0)

    def test_a_network_failure_reports_zero_rather_than_raising(self):
        from unittest.mock import patch

        backend = self._backend()
        _calls, urlopen = self._fake_transport(
            send_error=OSError("connection refused"))

        with patch("urllib.request.urlopen", urlopen):
            sent = backend.send_messages([self._message()])

        self.assertEqual(sent, 0)

    def test_a_non_2xx_status_is_not_treated_as_accepted(self):
        from unittest.mock import patch

        backend = self._backend()
        _calls, urlopen = self._fake_transport(send_status=302)

        with patch("urllib.request.urlopen", urlopen):
            sent = backend.send_messages([self._message()])

        self.assertEqual(sent, 0)

    def test_one_failure_does_not_stop_the_rest_of_the_batch(self):
        from unittest.mock import patch

        backend = self._backend()
        attempts = {"n": 0}
        base_calls, base_urlopen = self._fake_transport()

        def urlopen(request, timeout=None):
            if "gmail.googleapis" in request.full_url:
                attempts["n"] += 1
                if attempts["n"] == 1:
                    raise OSError("transient")
            return base_urlopen(request, timeout=timeout)

        messages = [self._message(to=[f"s{n}@example.edu"]) for n in range(3)]
        with patch("urllib.request.urlopen", urlopen):
            sent = backend.send_messages(messages)

        self.assertEqual(sent, 2)

    def test_no_secret_or_message_content_is_logged_on_failure(self):
        """These logs are read by people who need none of it, and a
        password-reset body carries a working token."""
        import urllib.error
        from unittest.mock import patch

        backend = self._backend()
        _calls, urlopen = self._fake_transport(
            send_error=urllib.error.HTTPError(
                "https://gmail.googleapis.com", 400, "Bad Request", {},
                io.BytesIO(b'{"error": "invalid argument"}')))

        with patch("urllib.request.urlopen", urlopen):
            with self.assertLogs("config.email", level="ERROR") as logged:
                backend.send_messages([self._message(
                    body="Reset link: https://example.edu/reset/SECRET-TOKEN")])

        output = "\n".join(logged.output)
        for forbidden in ("student@example.edu", "SECRET-TOKEN",
                          "test-client-secret", "test-refresh-token",
                          "test-access-token"):
            self.assertNotIn(forbidden, output)

    # ----------------------------------------------------- the whole contract

    def test_send_mail_reaches_gmail_without_any_caller_knowing(self):
        """The acceptance criterion: application code stays provider-agnostic.

        accounts/serializers.py and accounts/views.py call send_mail and were
        not touched by this migration.
        """
        from unittest.mock import patch

        from django.core.mail import send_mail

        calls, urlopen = self._fake_transport()

        with override_settings(
                EMAIL_BACKEND="config.email.GmailApiEmailBackend",
                **self.CREDENTIALS):
            with patch("urllib.request.urlopen", urlopen):
                sent = send_mail(
                    "Verify your MomentumQuest account",
                    "Open this link to verify.",
                    "MomentumQuest <system@example.edu>",
                    ["student@example.edu"],
                )

        self.assertEqual(sent, 1)
        self.assertEqual(
            [c["url"] for c in calls],
            ["https://oauth2.googleapis.com/token",
             "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"])


class GmailSenderConfigurationTests(TestCase):
    """DEFAULT_FROM_EMAIL is the only sender, and it has to be usable.

    There is deliberately no GMAIL_SENDER_EMAIL. Gmail sends as whichever
    account the refresh token belongs to, so a second sender setting could
    disagree with reality while looking authoritative -- and misleading
    production configuration is worse than none.

    The guard exists because of the project's own fallback:
    f"MomentumQuest <{EMAIL_HOST_USER}>", where EMAIL_HOST_USER is os.getenv
    with no default. An unconfigured deployment therefore gets the literal
    string "MomentumQuest <None>", which the console backend prints happily and
    Gmail cannot send.
    """

    CREDENTIALS = {
        "GMAIL_CLIENT_ID": "test-client-id",
        "GMAIL_CLIENT_SECRET": "test-client-secret",
        "GMAIL_REFRESH_TOKEN": "test-refresh-token",
    }

    def _build(self, **overrides):
        from config.email import GmailApiEmailBackend

        with override_settings(**{**self.CREDENTIALS, **overrides}):
            return GmailApiEmailBackend()

    # ------------------------------------------------- the removed setting

    def test_the_backend_works_with_no_sender_setting_at_all(self):
        """GMAIL_SENDER_EMAIL is gone; nothing reads it."""
        backend = self._build(
            DEFAULT_FROM_EMAIL="MomentumQuest <system@example.edu>")

        self.assertFalse(hasattr(backend, "sender"))

    def test_gmail_sender_email_is_no_longer_a_setting(self):
        """A removed variable that lingers in settings invites someone to set it
        and expect it to matter."""
        from django.conf import settings

        self.assertFalse(hasattr(settings, "GMAIL_SENDER_EMAIL"))

    def test_setting_it_anyway_changes_nothing(self):
        """Proves it is inert rather than merely undocumented."""
        backend = self._build(
            DEFAULT_FROM_EMAIL="MomentumQuest <system@example.edu>",
            GMAIL_SENDER_EMAIL="someone-else@example.edu")

        self.assertFalse(hasattr(backend, "sender"))

    # --------------------------------------------------- accepted senders

    def test_a_name_and_address_is_accepted(self):
        self._build(DEFAULT_FROM_EMAIL="MomentumQuest <system@example.edu>")

    def test_a_bare_address_is_accepted(self):
        self._build(DEFAULT_FROM_EMAIL="system@example.edu")

    def test_surrounding_whitespace_is_tolerated(self):
        self._build(DEFAULT_FROM_EMAIL="  system@example.edu  ")

    # --------------------------------------------------- refused senders

    def test_a_blank_sender_is_refused(self):
        from django.core.exceptions import ImproperlyConfigured

        with self.assertRaises(ImproperlyConfigured) as caught:
            self._build(DEFAULT_FROM_EMAIL="")

        self.assertIn("DEFAULT_FROM_EMAIL", str(caught.exception))

    def test_whitespace_only_is_refused(self):
        from django.core.exceptions import ImproperlyConfigured

        with self.assertRaises(ImproperlyConfigured):
            self._build(DEFAULT_FROM_EMAIL="   ")

    def test_the_unconfigured_smtp_fallback_is_refused(self):
        """The case this guard was added for.

        settings computes f"MomentumQuest <{EMAIL_HOST_USER}>" and
        EMAIL_HOST_USER has no default, so this exact string is what an
        unconfigured deployment produces.
        """
        from django.core.exceptions import ImproperlyConfigured

        with self.assertRaises(ImproperlyConfigured) as caught:
            self._build(DEFAULT_FROM_EMAIL="MomentumQuest <None>")

        self.assertIn("DEFAULT_FROM_EMAIL", str(caught.exception))

    def test_a_display_name_with_no_address_is_refused(self):
        from django.core.exceptions import ImproperlyConfigured

        for value in ("MomentumQuest", "MomentumQuest <>", "None"):
            with self.subTest(value=value):
                with self.assertRaises(ImproperlyConfigured):
                    self._build(DEFAULT_FROM_EMAIL=value)

    def test_the_refusal_names_the_setting_but_no_credential(self):
        from django.core.exceptions import ImproperlyConfigured

        with self.assertRaises(ImproperlyConfigured) as caught:
            self._build(DEFAULT_FROM_EMAIL="MomentumQuest <None>")

        message = str(caught.exception)
        self.assertIn("DEFAULT_FROM_EMAIL", message)
        for secret in ("test-client-secret", "test-refresh-token",
                       "test-client-id"):
            self.assertNotIn(secret, message)

    # ------------------------------------------------------ fail_silently

    def test_fail_silently_skips_the_sender_check(self):
        """Django constructs backends in places that must not raise."""
        from config.email import GmailApiEmailBackend

        with override_settings(**self.CREDENTIALS,
                               DEFAULT_FROM_EMAIL="MomentumQuest <None>"):
            backend = GmailApiEmailBackend(fail_silently=True)

        self.assertEqual(backend.send_messages([]), 0)

    # ------------------------------------------- the other backends unmoved

    def test_the_resend_backend_does_not_require_a_usable_sender(self):
        """Resend validates the sending domain itself, and this check is
        specific to the Gmail path -- so adding it globally would have changed
        an unrelated provider's behaviour."""
        from config.email import ResendEmailBackend

        with override_settings(EMAIL_API_KEY="test-key",
                               DEFAULT_FROM_EMAIL="MomentumQuest <None>"):
            ResendEmailBackend()

    def test_local_smtp_development_is_unaffected(self):
        """The reason the check lives in the backend and not in settings: with
        the console or locmem backend, "MomentumQuest <None>" is harmless and
        refusing it would break every developer's clone."""
        from django.core.mail import get_connection, send_mail

        with override_settings(
                EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
                DEFAULT_FROM_EMAIL="MomentumQuest <None>"):
            get_connection()
            sent = send_mail("Subject", "Body", None, ["student@example.edu"])

        self.assertEqual(sent, 1)
