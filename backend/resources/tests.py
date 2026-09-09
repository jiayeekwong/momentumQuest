import json
import os
import shutil
import tempfile
from unittest import mock
from unittest.mock import patch

from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import (
    AdminProfile,
    Company,
    PrivacyAuditLog,
    Student,
    StudentSkill,
    User,
    UserConsent,
)
from scrape_jobs.models import Skill, SkillAlias
from .file_validation import InvalidUpload, validate_document
from .models import (
    Certificate,
    CertificateSkillEvidence, CourseCatalogue, LearningResource,
    SubjectSkillMapping, TranscriptSkillEvidence, TranscriptUpload,
)
from .skill_evidence import (
    recalculate_student_skill, recalculate_student_skills,
)
from .skill_recognition import apply_skills, resolve_skills
from .transcript_classifier import classify_transcript
from .transcript_parser import parse_transcript_text


# A faithful excerpt of the Universiti Malaya transcript text layer, including
# the collapsed spaces the real PDF produces ("COMPUTER SYSTEMS ANDORGANIZATION",
# "PROJECTMANAGEMENT"). Personal details are omitted deliberately.
SAMPLE_TRANSCRIPT = """STUDENT ACADEMIC PERFORMANCE RECORD
No Module Module Description Credit Grade Grade Point
Examination Result for Semester 1, Session 2023/2024
1. GIG1012 PHILOSOPHY AND CURRENT ISSUES 2 A 8.00
2. WIA1001 INFORMATION SYSTEMS 3 A 12.00
3. WIX1001 COMPUTING MATHEMATICS I 3 B 9.00
4. WIX1002 FUNDAMENTALS OF PROGRAMMING 5 B- 13.50
5. WIX1003 COMPUTER SYSTEMS ANDORGANIZATION 3 A 12.00
GPA : 3.47 Credit Taken : 18 Credit Given : 18 Result : Pass
CGPA : 3.47 Cumulative Credit Taken : 18 Cumulative Credit Given : 18
Examination Result for Semester 2, Session 2023/2024
1. WIA1002 DATA STRUCTURE 5 B 15.00
2. WIA1005 NETWORK TECHNOLOGY FOUNDATION 4 A- 14.80
3. WIA1006 MACHINE LEARNING 3 A- 11.10
GPA : 3.52 Credit Taken : 21 Credit Given : 21 Result : Pass
Examination Result for Semester 1, Session 2024/2025
1. WIA2001 DATABASE 3 A 12.00
2. WIX2002 PROJECTMANAGEMENT 3 A 12.00
GPA : 3.94 Credit Taken : 21 Credit Given : 21 Result : Pass (Dean's Award)
Notes
1.Students are required to complete the final verification and declaration.
2.The information declared in your profile will be used for all documents.
"""


class TranscriptParserTests(TestCase):
    """The regex layer — no database involved."""

    def test_extracts_every_subject_row(self):
        subjects, warnings = parse_transcript_text(SAMPLE_TRANSCRIPT)

        self.assertEqual(len(subjects), 10)
        self.assertEqual(warnings, [])

    def test_ignores_gpa_and_notes_lines(self):
        subjects, _ = parse_transcript_text(SAMPLE_TRANSCRIPT)
        codes = [subject["code"] for subject in subjects]

        # "1.Students are required..." looks like a subject row until you
        # require a module code, which is exactly why the regex does.
        self.assertNotIn("", codes)
        self.assertEqual(len(codes), len(set(codes)))

    def test_parses_fields_correctly(self):
        subjects, _ = parse_transcript_text(SAMPLE_TRANSCRIPT)
        data_structure = next(s for s in subjects if s["code"] == "WIA1002")

        self.assertEqual(data_structure["name"], "DATA STRUCTURE")
        self.assertEqual(data_structure["credit"], 5)
        self.assertEqual(data_structure["grade"], "B")
        self.assertEqual(data_structure["grade_point"], 15.00)
        self.assertEqual(data_structure["semester"], "2")
        self.assertEqual(data_structure["session"], "2023/2024")

    def test_handles_collapsed_spaces_in_names(self):
        """The PDF text layer glues words together; codes stay clean."""
        subjects, _ = parse_transcript_text(SAMPLE_TRANSCRIPT)
        by_code = {s["code"]: s for s in subjects}

        self.assertEqual(by_code["WIX1003"]["name"], "COMPUTER SYSTEMS ANDORGANIZATION")
        self.assertEqual(by_code["WIX2002"]["name"], "PROJECTMANAGEMENT")

    def test_grade_point_checksum_passes_on_valid_rows(self):
        subjects, _ = parse_transcript_text(SAMPLE_TRANSCRIPT)

        self.assertTrue(all(subject["checksum_ok"] for subject in subjects))

    def test_grade_point_checksum_catches_misparse(self):
        """A row whose grade point contradicts its grade is flagged, not trusted."""
        bad = ("Examination Result for Semester 1, Session 2023/2024\n"
               "1. WIA1002 DATA STRUCTURE 5 A 13.50\n")   # A over 5 credits is 20.00
        subjects, warnings = parse_transcript_text(bad)

        self.assertFalse(subjects[0]["checksum_ok"])
        self.assertEqual(len(warnings), 1)

    def test_semester_header_is_case_insensitive(self):
        """Real UM PDFs render "For" with a capital F; some exports use "for"."""
        text = ("Examination Result For Semester 2, Session 2025/2026\n"
                "1. WIF2003 WEB PROGRAMMING 3 A 12.00\n")
        subjects, _ = parse_transcript_text(text)

        self.assertEqual(subjects[0]["semester"], "2")
        self.assertEqual(subjects[0]["session"], "2025/2026")

    def test_empty_input_is_safe(self):
        self.assertEqual(parse_transcript_text(""), ([], []))
        self.assertEqual(parse_transcript_text(None), ([], []))


class SkillRecognitionTests(TestCase):
    """Mapping subjects onto skills, and writing them to the student."""

    def setUp(self):
        self.user = User.objects.create_user(email="s@test.com", password="x", role="STUDENT")
        self.student = Student.objects.create(user=self.user, student_name="Test Student")

        self.programming = Skill.objects.create(skill_name="Programming")
        self.java = Skill.objects.create(skill_name="Java")
        self.algorithms = Skill.objects.create(skill_name="Algorithms")

        SubjectSkillMapping.objects.create(
            subject_code="WIX1002", subject_name="FUNDAMENTALS OF PROGRAMMING",
            skill=self.programming)
        SubjectSkillMapping.objects.create(
            subject_code="WIX1002", subject_name="FUNDAMENTALS OF PROGRAMMING",
            skill=self.java)
        SubjectSkillMapping.objects.create(
            subject_code="WIA2005", subject_name="ALGORITHM DESIGN AND ANALYSIS",
            skill=self.algorithms)

    def _subject(self, code, grade, checksum_ok=True):
        return {"code": code, "name": "", "credit": 3, "grade": grade,
                "grade_point": 0.0, "semester": "1", "session": "2023/2024",
                "checksum_ok": checksum_ok, "skills": []}

    def test_maps_subject_to_all_its_skills(self):
        levels = resolve_skills([self._subject("WIX1002", "A")])

        self.assertEqual(levels, {self.programming: "ADVANCED", self.java: "ADVANCED"})

    def test_annotates_subject_with_skill_names(self):
        subjects = [self._subject("WIX1002", "A")]
        resolve_skills(subjects)

        self.assertCountEqual(subjects[0]["skills"], ["Programming", "Java"])

    def test_unmapped_subject_produces_no_skill(self):
        """General-education modules map to nothing — that is expected."""
        subjects = [self._subject("GIG1012", "A")]
        levels = resolve_skills(subjects)

        self.assertEqual(levels, {})
        self.assertEqual(subjects[0]["skills"], [])

    def test_grade_below_c_is_not_recorded(self):
        self.assertEqual(resolve_skills([self._subject("WIX1002", "D")]), {})
        self.assertEqual(resolve_skills([self._subject("WIX1002", "F")]), {})

    def test_failed_checksum_row_is_skipped(self):
        levels = resolve_skills([self._subject("WIX1002", "A", checksum_ok=False)])

        self.assertEqual(levels, {})

    def test_grade_maps_to_expected_level(self):
        for grade, expected in [("A+", "ADVANCED"), ("A", "ADVANCED"), ("A-", "ADVANCED"),
                                ("B+", "INTERMEDIATE"), ("B", "INTERMEDIATE"),
                                ("B-", "INTERMEDIATE"), ("C+", "BEGINNER"), ("C", "BEGINNER")]:
            with self.subTest(grade=grade):
                levels = resolve_skills([self._subject("WIA2005", grade)])
                self.assertEqual(levels[self.algorithms], expected)

    def test_highest_grade_wins_across_subjects(self):
        """Two subjects mapping to the same skill: the better grade decides."""
        SubjectSkillMapping.objects.create(
            subject_code="WIA2005", subject_name="ALGORITHMS", skill=self.java)

        levels = resolve_skills([
            self._subject("WIX1002", "C"),    # Java -> BEGINNER
            self._subject("WIA2005", "A"),    # Java -> ADVANCED
        ])

        self.assertEqual(levels[self.java], "ADVANCED")

    def test_apply_creates_student_skills(self):
        added, upgraded = apply_skills(self.student, {self.programming: "ADVANCED"})

        self.assertEqual((added, upgraded), (1, 0))
        row = StudentSkill.objects.get(student=self.student, skill=self.programming)
        self.assertEqual(row.skill_level, "ADVANCED")

    def test_apply_upgrades_but_never_downgrades(self):
        apply_skills(self.student, {self.programming: "ADVANCED"})

        added, upgraded = apply_skills(self.student, {self.programming: "BEGINNER"})

        self.assertEqual((added, upgraded), (0, 0))
        row = StudentSkill.objects.get(student=self.student, skill=self.programming)
        self.assertEqual(row.skill_level, "ADVANCED", "a lower grade must not downgrade")

    def test_apply_raises_level_when_grade_is_better(self):
        apply_skills(self.student, {self.programming: "BEGINNER"})

        added, upgraded = apply_skills(self.student, {self.programming: "ADVANCED"})

        self.assertEqual((added, upgraded), (0, 1))
        row = StudentSkill.objects.get(student=self.student, skill=self.programming)
        self.assertEqual(row.skill_level, "ADVANCED")

    def test_reapplying_same_skills_is_idempotent(self):
        apply_skills(self.student, {self.programming: "ADVANCED"})
        apply_skills(self.student, {self.programming: "ADVANCED"})

        self.assertEqual(StudentSkill.objects.filter(student=self.student).count(), 1)


class CertificateUploadTests(TestCase):
    """Students submit a certificate as a file or as a credential URL."""

    def setUp(self):
        self.private_root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.private_root, ignore_errors=True)

        self.user = User.objects.create_user(
            email="cert-owner@test.com", password="pw", role="STUDENT")
        self.student = Student.objects.create(user=self.user, student_name="Owner")

        self.other_user = User.objects.create_user(
            email="cert-other@test.com", password="pw", role="STUDENT")
        self.other_student = Student.objects.create(
            user=self.other_user, student_name="Other")

        self.skill = Skill.objects.create(skill_name="Python")

        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    @staticmethod
    def _release(response):
        stream = getattr(response, "file_to_stream", None)
        if stream is not None:
            stream.close()

    def _upload(self, **extra):
        payload = {
            "skills": json.dumps([{"skill_id": self.skill.id,
                                   "claimed_level": "INTERMEDIATE"}]),
            "source": "Coursera",
            # The upload-time consent the Certificate Verification Notice
            # collects. Tests that exercise its absence pass ack=False.
            "document_consent_ack": True,
        }
        payload.update(extra)
        return self.client.post(reverse("certificate-list"), payload, format="multipart")

    def test_upload_stores_file_outside_media_root(self):
        upload = SimpleUploadedFile("cert.pdf", b"%PDF-1.4 fake", content_type="application/pdf")
        with override_settings(PRIVATE_MEDIA_ROOT=self.private_root):
            response = self._upload(file=upload)

        self.assertEqual(response.status_code, 201, response.data)
        certificate = Certificate.objects.get()
        # Forward slash, not os.sep: a path stored on Windows has to resolve on
        # a Linux deployment, where a backslash is part of the filename rather
        # than a separator.
        self.assertTrue(certificate.file_path.startswith("certificates/"))
        self.assertNotIn("\\", certificate.file_path)
        self.assertEqual(certificate.original_name, "cert.pdf")
        self.assertEqual(certificate.verified_status, Certificate.VerifiedStatus.PENDING)
        self.assertTrue(os.path.exists(
            os.path.join(self.private_root, certificate.file_path)))

    def test_credential_url_is_accepted_without_a_file(self):
        response = self._upload(cert_url="https://coursera.org/verify/ABC123")

        self.assertEqual(response.status_code, 201, response.data)
        certificate = Certificate.objects.get()
        self.assertEqual(certificate.cert_url, "https://coursera.org/verify/ABC123")
        self.assertFalse(certificate.has_file)

    def test_submission_without_any_proof_is_rejected(self):
        response = self._upload()

        self.assertEqual(response.status_code, 400)
        self.assertFalse(Certificate.objects.exists())

    def test_unsupported_file_type_is_rejected(self):
        upload = SimpleUploadedFile("cert.exe", b"MZ", content_type="application/octet-stream")
        with override_settings(PRIVATE_MEDIA_ROOT=self.private_root):
            response = self._upload(file=upload)

        self.assertEqual(response.status_code, 400)
        self.assertFalse(Certificate.objects.exists())

    def test_file_view_refuses_another_students_certificate(self):
        upload = SimpleUploadedFile("cert.pdf", b"%PDF-1.4 fake", content_type="application/pdf")
        with override_settings(PRIVATE_MEDIA_ROOT=self.private_root):
            self._upload(file=upload)
            certificate = Certificate.objects.get()

            self.client.force_authenticate(user=self.other_user)
            response = self.client.get(
                reverse("certificate-file", args=[certificate.id]))

        self.assertEqual(response.status_code, 403)

    def test_owner_can_open_their_own_certificate(self):
        upload = SimpleUploadedFile("cert.pdf", b"%PDF-1.4 fake", content_type="application/pdf")
        with override_settings(PRIVATE_MEDIA_ROOT=self.private_root):
            self._upload(file=upload)
            certificate = Certificate.objects.get()
            response = self.client.get(
                reverse("certificate-file", args=[certificate.id]))
            self.addCleanup(self._release, response)

        self.assertEqual(response.status_code, 200)

    def test_link_only_certificate_has_no_file_to_serve(self):
        self._upload(cert_url="https://coursera.org/verify/ABC123")
        certificate = Certificate.objects.get()

        response = self.client.get(reverse("certificate-file", args=[certificate.id]))

        self.assertEqual(response.status_code, 404)


class CertificateEndorsementTests(TestCase):
    """Endorsing is what grants the skill — the loop must actually close."""

    def setUp(self):
        self.student_user = User.objects.create_user(
            email="endorse-student@test.com", password="pw", role="STUDENT")
        self.student = Student.objects.create(
            user=self.student_user, student_name="Student")

        self.admin_user = User.objects.create_user(
            email="endorse-admin@test.com", password="pw", role="ADMIN", is_staff=True)
        AdminProfile.objects.create(user=self.admin_user)

        self.skill = Skill.objects.create(skill_name="Kubernetes")
        self.certificate = Certificate.objects.create(
            student=self.student,
            cert_url="https://coursera.org/verify/ABC")
        CertificateSkillEvidence.objects.create(
            certificate=self.certificate, skill=self.skill,
            claimed_level="INTERMEDIATE")

        self.client = APIClient()
        self.client.force_authenticate(user=self.admin_user)

    def _endorse(self, verdict, level="INTERMEDIATE", **extra):
        payload = {"verified_status": verdict}
        if verdict == "REJECTED":
            payload["rejection_reason"] = "UNREADABLE_DOCUMENT"
        else:
            # The decision is per skill as well as per document, so an
            # approval names what it approves and at what level.
            payload["skills"] = [
                {"skill_id": self.skill.id, "approved_level": level}]
        payload.update(extra)
        return self.client.patch(
            reverse("certificate-endorse", args=[self.certificate.id]),
            payload, format="json")

    def test_approval_grants_the_skill(self):
        self.assertFalse(StudentSkill.objects.filter(student=self.student).exists())

        response = self._endorse("APPROVED")

        self.assertEqual(response.status_code, 200, response.data)
        row = StudentSkill.objects.get(student=self.student, skill=self.skill)
        self.assertEqual(row.skill_level, "INTERMEDIATE")

    def test_rejection_grants_nothing(self):
        response = self._endorse("REJECTED")

        self.assertEqual(response.status_code, 200, response.data)
        self.assertFalse(StudentSkill.objects.filter(student=self.student).exists())

    def test_approving_twice_is_idempotent(self):
        self._endorse("APPROVED")
        self._endorse("APPROVED")

        self.assertEqual(
            StudentSkill.objects.filter(student=self.student, skill=self.skill).count(), 1)

    def test_a_lower_certificate_never_downgrades_higher_evidence(self):
        """The highest *live* evidence wins, whatever order it arrives in.

        Written with a real approved certificate behind the ADVANCED rather
        than a hand-made StudentSkill row: a level with no evidence under it
        is precisely what the recalculation exists to clear away, so asserting
        that one survives would be asserting the bug.
        """
        earlier = Certificate.objects.create(
            student=self.student, cert_url="https://coursera.org/verify/ADV",
            verified_status=Certificate.VerifiedStatus.APPROVED)
        CertificateSkillEvidence.objects.create(
            certificate=earlier, skill=self.skill,
            claimed_level="ADVANCED", approved_level="ADVANCED",
            review_status=CertificateSkillEvidence.ReviewStatus.APPROVED)
        recalculate_student_skills(self.student, skills=[self.skill])

        self._endorse("APPROVED", level="BEGINNER")

        row = StudentSkill.objects.get(student=self.student, skill=self.skill)
        self.assertEqual(row.skill_level, "ADVANCED")


# ---------------------------------------------------------------------------
# Privacy: consent, access control, audit, retention
# ---------------------------------------------------------------------------


def _pdf(name="cert.pdf"):
    return SimpleUploadedFile(name, b"%PDF-1.4 fake body", content_type="application/pdf")


class PrivacyTestBase(TestCase):
    """One student with a certificate, plus an admin, a second student and a company."""

    def setUp(self):
        self.private_root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.private_root, ignore_errors=True)

        self.user = User.objects.create_user(
            email="priv-owner@test.com", password="pw", role="STUDENT")
        self.student = Student.objects.create(
            user=self.user, student_name="Owner", matric_number="S100001")

        self.other_user = User.objects.create_user(
            email="priv-other@test.com", password="pw", role="STUDENT")
        self.other_student = Student.objects.create(
            user=self.other_user, student_name="Other")

        self.admin_user = User.objects.create_user(
            email="priv-admin@test.com", password="pw", role="ADMIN", is_staff=True)
        AdminProfile.objects.create(user=self.admin_user, admin_name="Admin")

        self.company_user = User.objects.create_user(
            email="priv-company@test.com", password="pw", role="COMPANY")
        Company.objects.create(user=self.company_user, company_name="Acme")

        self.skill = Skill.objects.create(skill_name="Docker")

        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    @staticmethod
    def _release(response):
        stream = getattr(response, "file_to_stream", None)
        if stream is not None:
            stream.close()

    def _upload(self, **extra):
        payload = {
            "skills": json.dumps([{"skill_id": self.skill.id,
                                   "claimed_level": "INTERMEDIATE"}]),
            "source": "Coursera",
            "document_consent_ack": True,
        }
        payload.update(extra)
        with override_settings(PRIVATE_MEDIA_ROOT=self.private_root):
            return self.client.post(
                reverse("certificate-list"), payload, format="multipart")

    def _make_certificate(self, **extra):
        """Upload one certificate and return it.

        Returns the newest rather than the only one: a decision is final now,
        so a test needing both an approval and a rejection has to make two.
        """
        self._upload(file=_pdf(), **extra)
        # By id, not uploaded_time: auto_now_add can give two rows created in
        # the same instant the same timestamp, and "latest" would then be a
        # coin flip.
        return Certificate.objects.latest("id")


class CertificateUploadConsentTests(PrivacyTestBase):
    """A stored document must never exist without the consent that allowed it."""

    def test_upload_without_acknowledgement_is_refused(self):
        response = self._upload(file=_pdf(), document_consent_ack=False)

        self.assertEqual(response.status_code, 400)
        self.assertIn("document_consent_ack", response.data)
        self.assertFalse(Certificate.objects.exists())

    def test_upload_missing_the_acknowledgement_field_is_refused(self):
        payload = {"skills": json.dumps([{"skill_id": self.skill.id}]),
                   "cert_url": "https://x.test/1"}
        with override_settings(PRIVATE_MEDIA_ROOT=self.private_root):
            response = self.client.post(
                reverse("certificate-list"), payload, format="multipart")

        self.assertEqual(response.status_code, 400)
        self.assertFalse(Certificate.objects.exists())

    def test_upload_records_a_consent_linked_to_the_document(self):
        certificate = self._make_certificate()

        consent = certificate.upload_consent
        self.assertIsNotNone(consent)
        self.assertTrue(consent.accepted)
        self.assertIsNotNone(consent.accepted_at)
        self.assertEqual(consent.user, self.user)
        self.assertEqual(consent.source, UserConsent.Source.CERTIFICATE_UPLOAD)
        self.assertEqual(
            consent.consent_type,
            UserConsent.ConsentType.DOCUMENT_VERIFICATION_CONSENT)

    def test_the_acknowledgement_arrives_as_a_form_string(self):
        # FormData stringifies everything, so the browser sends the literal
        # 'true' rather than a JSON boolean.
        payload = {
            "skills": json.dumps([{"skill_id": self.skill.id}]),
            "source": "Coursera",
            "document_consent_ack": "true",
            "file": _pdf(),
        }
        with override_settings(PRIVATE_MEDIA_ROOT=self.private_root):
            response = self.client.post(
                reverse("certificate-list"), payload, format="multipart")

        self.assertEqual(response.status_code, 201, response.data)

    def test_a_refused_upload_records_no_consent(self):
        self._upload(file=_pdf(), document_consent_ack=False)

        self.assertFalse(UserConsent.objects.exists())


class CertificateAccessControlTests(PrivacyTestBase):
    """Private documents reach their owner and an authorised admin. Nobody else."""

    def test_student_cannot_open_another_students_document(self):
        certificate = self._make_certificate()

        self.client.force_authenticate(user=self.other_user)
        with override_settings(PRIVATE_MEDIA_ROOT=self.private_root):
            response = self.client.get(
                reverse("certificate-file", args=[certificate.id]))

        self.assertEqual(response.status_code, 403)

    def test_student_cannot_read_another_students_certificate_record(self):
        certificate = self._make_certificate()

        self.client.force_authenticate(user=self.other_user)
        response = self.client.get(reverse("certificate-detail", args=[certificate.id]))

        self.assertEqual(response.status_code, 403)

    def test_anonymous_visitor_cannot_open_a_document(self):
        certificate = self._make_certificate()

        self.client.force_authenticate(user=None)
        with override_settings(PRIVATE_MEDIA_ROOT=self.private_root):
            response = self.client.get(
                reverse("certificate-file", args=[certificate.id]))

        self.assertEqual(response.status_code, 401)

    def test_company_cannot_list_certificates(self):
        self._make_certificate()

        self.client.force_authenticate(user=self.company_user)
        response = self.client.get(reverse("certificate-list"))

        self.assertEqual(response.status_code, 403)

    def test_company_cannot_upload_a_certificate(self):
        self.client.force_authenticate(user=self.company_user)
        response = self._upload(file=_pdf())

        self.assertEqual(response.status_code, 403)
        self.assertFalse(Certificate.objects.exists())

    def test_company_cannot_open_a_document(self):
        certificate = self._make_certificate()

        self.client.force_authenticate(user=self.company_user)
        with override_settings(PRIVATE_MEDIA_ROOT=self.private_root):
            response = self.client.get(
                reverse("certificate-file", args=[certificate.id]))

        self.assertEqual(response.status_code, 403)

    def test_company_cannot_reach_the_verification_endpoint(self):
        certificate = self._make_certificate()

        self.client.force_authenticate(user=self.company_user)
        response = self.client.patch(
            reverse("certificate-endorse", args=[certificate.id]),
            {"verified_status": "APPROVED"}, format="json")

        self.assertEqual(response.status_code, 403)

    def test_student_cannot_verify_their_own_certificate(self):
        certificate = self._make_certificate()

        response = self.client.patch(
            reverse("certificate-endorse", args=[certificate.id]),
            {"verified_status": "APPROVED"}, format="json")

        self.assertEqual(response.status_code, 403)

    def test_admin_can_open_a_students_document(self):
        certificate = self._make_certificate()

        self.client.force_authenticate(user=self.admin_user)
        with override_settings(PRIVATE_MEDIA_ROOT=self.private_root):
            response = self.client.get(
                reverse("certificate-file", args=[certificate.id]))
            self.addCleanup(self._release, response)

        self.assertEqual(response.status_code, 200)

    def test_internal_notes_never_reach_the_student(self):
        certificate = self._make_certificate()
        certificate.verification_notes = "Looks altered, escalate"
        certificate.save(update_fields=["verification_notes"])

        response = self.client.get(reverse("certificate-detail", args=[certificate.id]))

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("verification_notes", response.data)
        self.assertNotIn("Looks altered", str(response.data))

    def test_a_certificate_predating_upload_consent_still_serializes(self):
        # Every certificate already in the database has upload_consent = NULL.
        # If traversing it raised, the whole admin queue would break on the
        # first legacy row.
        legacy = Certificate.objects.create(
            student=self.student, cert_url="https://example.test/legacy")
        CertificateSkillEvidence.objects.create(
            certificate=legacy, skill=self.skill, claimed_level="INTERMEDIATE")
        self.assertIsNone(legacy.upload_consent)

        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get(reverse("certificate-detail", args=[legacy.id]))

        self.assertEqual(response.status_code, 200, response.data)
        self.assertIsNone(response.data["consent_recorded_at"])

    def test_admin_sees_the_verification_context_the_student_does_not(self):
        certificate = self._make_certificate()

        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get(reverse("certificate-detail", args=[certificate.id]))

        self.assertEqual(response.status_code, 200)
        self.assertIn("verification_notes", response.data)
        self.assertEqual(response.data["matric_number"], "S100001")

    def test_document_response_is_not_cacheable_or_indexable(self):
        certificate = self._make_certificate()

        with override_settings(PRIVATE_MEDIA_ROOT=self.private_root):
            response = self.client.get(
                reverse("certificate-file", args=[certificate.id]))
            self.addCleanup(self._release, response)

        self.assertIn("no-store", response["Cache-Control"])
        self.assertIn("noindex", response["X-Robots-Tag"])

    def test_document_is_served_under_its_generated_name_not_the_uploaded_one(self):
        # A student may name their own file after their IC. Echoing that name
        # back in a header would put the number into the admin's download
        # folder and into any proxy log along the way.
        self._upload(file=_pdf("040910101234_SPM.pdf"))
        certificate = Certificate.objects.get()

        with override_settings(PRIVATE_MEDIA_ROOT=self.private_root):
            response = self.client.get(
                reverse("certificate-file", args=[certificate.id]))
            self.addCleanup(self._release, response)

        self.assertNotIn("040910101234", response["Content-Disposition"])
        self.assertIn("cert_", response["Content-Disposition"])
        # Still shown back to the student in the UI.
        self.assertEqual(certificate.original_name, "040910101234_SPM.pdf")

    def test_stored_filename_never_contains_the_uploaded_name(self):
        self._upload(file=_pdf("040910101234_SPM.pdf"))
        certificate = Certificate.objects.get()

        self.assertNotIn("040910101234", certificate.file_path)


class CertificateVerificationTests(PrivacyTestBase):
    """The decision, who made it, and when, are all recorded."""

    def setUp(self):
        super().setUp()
        self.certificate = self._make_certificate()
        self.client.force_authenticate(user=self.admin_user)

    def _decide(self, payload):
        # An approval names the skills it approves; the endpoint refuses one
        # that approves nothing, because a certificate verified but granting
        # nothing is a rejection written in the wrong field.
        if payload.get("verified_status") == "APPROVED" and "skills" not in payload:
            payload = dict(payload, skills=[
                {"skill_id": self.skill.id, "approved_level": "INTERMEDIATE"}])
        return self.client.patch(
            reverse("certificate-endorse", args=[self.certificate.id]),
            payload, format="json")

    def test_approval_stamps_the_reviewer_and_the_time(self):
        response = self._decide({"verified_status": "APPROVED"})

        self.assertEqual(response.status_code, 200, response.data)
        self.certificate.refresh_from_db()
        self.assertEqual(self.certificate.admin, self.admin_user.admin_profile)
        self.assertIsNotNone(self.certificate.verified_at)

    def test_rejection_requires_a_reason(self):
        response = self._decide({"verified_status": "REJECTED"})

        self.assertEqual(response.status_code, 400)
        self.assertIn("rejection_reason", response.data)
        self.certificate.refresh_from_db()
        self.assertEqual(
            self.certificate.verified_status, Certificate.VerifiedStatus.PENDING)

    def test_an_approval_cannot_carry_a_rejection_reason(self):
        response = self._decide({
            "verified_status": "APPROVED", "rejection_reason": "NAME_MISMATCH"})

        self.assertEqual(response.status_code, 400)

    def test_rejection_gives_the_student_a_readable_explanation(self):
        self._decide({
            "verified_status": "REJECTED", "rejection_reason": "NAME_MISMATCH"})

        self.client.force_authenticate(user=self.user)
        response = self.client.get(reverse("certificate-detail", args=[self.certificate.id]))

        self.assertIn("does not match your registered information",
                      response.data["rejection_message"])

    def test_notes_are_stored_but_stay_internal(self):
        self._decide({
            "verified_status": "REJECTED",
            "rejection_reason": "SUSPECTED_INVALID_DOCUMENT",
            "verification_notes": "Font mismatch on the seal",
        })

        self.certificate.refresh_from_db()
        self.assertEqual(self.certificate.verification_notes, "Font mismatch on the seal")

        self.client.force_authenticate(user=self.user)
        response = self.client.get(reverse("certificate-detail", args=[self.certificate.id]))
        self.assertNotIn("Font mismatch", str(response.data))

    def test_a_verification_decision_cannot_be_forged_by_the_client(self):
        # verified_at and the reviewing admin are stamped server-side; values
        # sent by the client are ignored.
        self._decide({
            "verified_status": "APPROVED",
            "verified_at": "2000-01-01T00:00:00Z",
            "admin": None,
        })

        self.certificate.refresh_from_db()
        self.assertEqual(self.certificate.verified_at.year, timezone.now().year)
        self.assertEqual(self.certificate.admin, self.admin_user.admin_profile)

    def test_an_arbitrary_status_is_refused(self):
        response = self._decide({"verified_status": "PENDING"})

        self.assertEqual(response.status_code, 400)

    def test_a_patch_that_states_no_decision_is_refused(self):
        # Regression: a PATCH carrying only notes used to return 200, stamp
        # verified_at on a still-PENDING certificate, and write a
        # CERTIFICATE_REJECTED audit row for a rejection that never happened.
        response = self.client.patch(
            reverse("certificate-endorse", args=[self.certificate.id]),
            {"verification_notes": "just jotting a note"}, format="json")

        self.assertEqual(response.status_code, 400)
        self.assertIn("verified_status", response.data)

        self.certificate.refresh_from_db()
        self.assertEqual(
            self.certificate.verified_status, Certificate.VerifiedStatus.PENDING)
        self.assertIsNone(self.certificate.verified_at)

    def test_a_refused_decision_writes_no_audit_row(self):
        PrivacyAuditLog.objects.all().delete()

        self.client.patch(
            reverse("certificate-endorse", args=[self.certificate.id]),
            {"verification_notes": "note only"}, format="json")

        self.assertFalse(
            PrivacyAuditLog.objects.filter(action__startswith="CERTIFICATE_").exists())

    def test_the_exact_approval_payload_the_admin_ui_sends_is_accepted(self):
        # The decision form always includes both fields, blank when unused. If
        # a blank rejection_reason were refused, every approval made through
        # the UI would fail while the tests still passed.
        response = self.client.patch(
            reverse("certificate-endorse", args=[self.certificate.id]),
            {"verified_status": "APPROVED", "rejection_reason": "",
             "verification_notes": "",
             "skills": [{"skill_id": self.skill.id,
                         "approved_level": "INTERMEDIATE"}]},
            format="json")

        self.assertEqual(response.status_code, 200, response.data)
        self.certificate.refresh_from_db()
        self.assertEqual(
            self.certificate.verified_status, Certificate.VerifiedStatus.APPROVED)

    def test_a_decided_submission_cannot_be_re_decided(self):
        """Replaces an earlier test that checked re-review cleared the old
        rejection reason. Re-review is now refused outright: approving after a
        rejection is fine, but *rejecting* after an approval left the granted
        skill standing, and one endpoint cannot allow one direction only
        without a revocation policy to lean on."""
        self._decide({
            "verified_status": "REJECTED", "rejection_reason": "UNREADABLE_DOCUMENT"})

        response = self._decide({"verified_status": "APPROVED"})

        self.assertEqual(response.status_code, 400)
        self.certificate.refresh_from_db()
        self.assertEqual(
            self.certificate.verified_status, Certificate.VerifiedStatus.REJECTED)


class CertificateDeletionTests(PrivacyTestBase):
    """A student may withdraw a submission, but only before it is decided."""

    def test_owner_can_delete_a_pending_submission(self):
        certificate = self._make_certificate()
        stored = os.path.join(self.private_root, certificate.file_path)
        self.assertTrue(os.path.exists(stored))

        with override_settings(PRIVATE_MEDIA_ROOT=self.private_root):
            response = self.client.delete(
                reverse("certificate-detail", args=[certificate.id]))

        self.assertEqual(response.status_code, 204)
        self.assertFalse(Certificate.objects.exists())
        self.assertFalse(os.path.exists(stored))

    def test_a_decided_submission_cannot_be_deleted(self):
        certificate = self._make_certificate()
        certificate.verified_status = Certificate.VerifiedStatus.APPROVED
        certificate.save(update_fields=["verified_status"])

        with override_settings(PRIVATE_MEDIA_ROOT=self.private_root):
            response = self.client.delete(
                reverse("certificate-detail", args=[certificate.id]))

        self.assertEqual(response.status_code, 400)
        self.assertTrue(Certificate.objects.exists())

    def test_a_student_cannot_delete_another_students_submission(self):
        certificate = self._make_certificate()

        self.client.force_authenticate(user=self.other_user)
        response = self.client.delete(
            reverse("certificate-detail", args=[certificate.id]))

        self.assertEqual(response.status_code, 403)
        self.assertTrue(Certificate.objects.exists())


class PrivacyAuditLogTests(PrivacyTestBase):
    """Sensitive operations leave a trace, and the trace carries no document data."""

    def test_upload_is_recorded(self):
        certificate = self._make_certificate()

        entry = PrivacyAuditLog.objects.get(
            action=PrivacyAuditLog.Action.CERTIFICATE_UPLOADED)
        self.assertEqual(entry.resource_id, certificate.id)
        self.assertEqual(entry.actor_user, self.user)
        self.assertEqual(entry.target_user, self.user)

    def test_admin_opening_a_document_is_recorded(self):
        certificate = self._make_certificate()

        self.client.force_authenticate(user=self.admin_user)
        with override_settings(PRIVATE_MEDIA_ROOT=self.private_root):
            response = self.client.get(
                reverse("certificate-file", args=[certificate.id]))
            self.addCleanup(self._release, response)

        entry = PrivacyAuditLog.objects.get(
            action=PrivacyAuditLog.Action.CERTIFICATE_VIEWED_BY_ADMIN)
        self.assertEqual(entry.actor_user, self.admin_user)
        self.assertEqual(entry.target_user, self.user)

    def test_a_student_opening_their_own_document_is_not_an_access_event(self):
        certificate = self._make_certificate()

        with override_settings(PRIVATE_MEDIA_ROOT=self.private_root):
            response = self.client.get(
                reverse("certificate-file", args=[certificate.id]))
            self.addCleanup(self._release, response)

        self.assertFalse(PrivacyAuditLog.objects.filter(
            action=PrivacyAuditLog.Action.CERTIFICATE_VIEWED_BY_ADMIN).exists())

    def test_approval_and_rejection_are_recorded(self):
        # Two submissions, because a decision is final: the same certificate
        # cannot be approved and then rejected any more.
        approved = self._make_certificate()
        rejected = self._make_certificate()
        self.client.force_authenticate(user=self.admin_user)

        self.client.patch(
            reverse("certificate-endorse", args=[approved.id]),
            {"verified_status": "APPROVED",
             "skills": [{"skill_id": self.skill.id,
                         "approved_level": "INTERMEDIATE"}]},
            format="json")
        self.assertTrue(PrivacyAuditLog.objects.filter(
            action=PrivacyAuditLog.Action.CERTIFICATE_VERIFIED,
            resource_id=approved.id).exists())

        self.client.patch(
            reverse("certificate-endorse", args=[rejected.id]),
            {"verified_status": "REJECTED", "rejection_reason": "NAME_MISMATCH"},
            format="json")
        self.assertTrue(PrivacyAuditLog.objects.filter(
            action=PrivacyAuditLog.Action.CERTIFICATE_REJECTED,
            resource_id=rejected.id).exists())

    def test_deletion_is_recorded(self):
        certificate = self._make_certificate()
        certificate_id = certificate.id

        with override_settings(PRIVATE_MEDIA_ROOT=self.private_root):
            self.client.delete(reverse("certificate-detail", args=[certificate_id]))

        self.assertTrue(PrivacyAuditLog.objects.filter(
            action=PrivacyAuditLog.Action.CERTIFICATE_DELETED,
            resource_id=certificate_id).exists())

    def test_the_log_has_no_field_that_could_hold_document_contents(self):
        # Structural, not behavioural: the guarantee that an IC number never
        # lands in the audit log rests on there being nowhere to put one.
        text_fields = {
            field.name for field in PrivacyAuditLog._meta.get_fields()
            if field.get_internal_type() in ("TextField", "CharField")
        }
        self.assertEqual(text_fields, {"action", "resource_type"})

    def test_an_audit_failure_does_not_break_the_operation(self):
        certificate = self._make_certificate()
        self.client.force_authenticate(user=self.admin_user)

        with mock.patch.object(
            PrivacyAuditLog.objects, "create", side_effect=RuntimeError("log is down")
        ):
            response = self.client.patch(
                reverse("certificate-endorse", args=[certificate.id]),
                {"verified_status": "APPROVED",
                 "skills": [{"skill_id": self.skill.id,
                             "approved_level": "INTERMEDIATE"}]},
                format="json")

        self.assertEqual(response.status_code, 200, response.data)
        certificate.refresh_from_db()
        self.assertEqual(
            certificate.verified_status, Certificate.VerifiedStatus.APPROVED)


class FileTypeValidationTests(PrivacyTestBase):
    """What a file claims to be and what it is are two different things."""

    def test_png_bytes_named_pdf_are_refused(self):
        disguised = SimpleUploadedFile(
            "cert.pdf", b"\x89PNG\r\n\x1a\n rest", content_type="application/pdf")

        response = self._upload(file=disguised)

        self.assertEqual(response.status_code, 400)
        self.assertFalse(Certificate.objects.exists())

    def test_an_executable_renamed_pdf_is_refused(self):
        disguised = SimpleUploadedFile(
            "cert.pdf", b"MZ\x90\x00\x03", content_type="application/pdf")

        response = self._upload(file=disguised)

        self.assertEqual(response.status_code, 400)
        self.assertFalse(Certificate.objects.exists())

    def test_an_empty_file_is_refused(self):
        response = self._upload(file=SimpleUploadedFile("cert.pdf", b""))

        self.assertEqual(response.status_code, 400)

    def test_the_detected_type_is_stored(self):
        certificate = self._make_certificate()

        self.assertEqual(certificate.mime_type, "application/pdf")

    def test_a_genuine_png_is_accepted_under_either_jpeg_free_extension(self):
        png = SimpleUploadedFile(
            "cert.png", b"\x89PNG\r\n\x1a\n body", content_type="image/png")

        response = self._upload(file=png)

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(Certificate.objects.get().mime_type, "image/png")

    def test_validator_reports_a_message_safe_to_show_a_student(self):
        with self.assertRaises(InvalidUpload) as caught:
            validate_document(SimpleUploadedFile("notes.txt", b"hello"))

        self.assertIn("PDF", str(caught.exception))

    def test_sniffing_leaves_the_file_readable(self):
        # The upload has to survive validation intact, or the bytes written to
        # storage would be truncated.
        certificate = self._make_certificate()
        stored = os.path.join(self.private_root, certificate.file_path)

        with open(stored, "rb") as handle:
            self.assertEqual(handle.read(), b"%PDF-1.4 fake body")


class RetentionTests(PrivacyTestBase):
    """Documents are kept while the account is active, and no longer."""

    def test_deleting_a_certificate_removes_the_stored_file(self):
        certificate = self._make_certificate()
        stored = os.path.join(self.private_root, certificate.file_path)

        with override_settings(PRIVATE_MEDIA_ROOT=self.private_root):
            certificate.delete()

        self.assertFalse(os.path.exists(stored))

    def test_deleting_the_account_removes_its_documents(self):
        certificate = self._make_certificate()
        stored = os.path.join(self.private_root, certificate.file_path)

        transcript = TranscriptUpload.objects.create(
            student=self.student, file_path="transcripts/t.pdf",
            original_name="t.pdf")
        transcript_dir = os.path.join(self.private_root, "transcripts")
        os.makedirs(transcript_dir, exist_ok=True)
        transcript_path = os.path.join(transcript_dir, "t.pdf")
        with open(transcript_path, "wb") as handle:
            handle.write(b"%PDF-1.4 transcript")

        with override_settings(PRIVATE_MEDIA_ROOT=self.private_root):
            self.user.delete()

        self.assertFalse(os.path.exists(stored))
        self.assertFalse(os.path.exists(transcript_path))

    def test_a_failed_save_leaves_no_orphaned_document_on_disk(self):
        # If the row is rolled back but the bytes survive, the file is
        # unreachable by the retention receiver -- an identity-bearing
        # document that nothing would ever delete.
        with override_settings(PRIVATE_MEDIA_ROOT=self.private_root):
            with mock.patch.object(
                UserConsent.objects, "create", side_effect=RuntimeError("db down")
            ):
                with self.assertRaises(RuntimeError):
                    self.client.post(
                        reverse("certificate-list"),
                        {
                            "skills": json.dumps([{"skill_id": self.skill.id}]),
                            "source": "Coursera",
                            "document_consent_ack": True,
                            "file": _pdf(),
                        },
                        format="multipart",
                    )

        self.assertFalse(Certificate.objects.exists())
        stored = os.path.join(self.private_root, "certificates")
        leftovers = os.listdir(stored) if os.path.isdir(stored) else []
        self.assertEqual(leftovers, [], "an orphaned document was left on disk")

    def test_stored_paths_are_portable_across_operating_systems(self):
        # os.path.join writes a backslash on Windows. A row stored that way
        # would not resolve on a Linux deployment -- the backslash becomes part
        # of the filename -- so every document uploaded here would 404 there.
        certificate = self._make_certificate()

        self.assertNotIn("\\", certificate.file_path)
        self.assertTrue(certificate.file_path.startswith("certificates/"))

    def test_a_path_already_stored_with_backslashes_still_resolves(self):
        # Rows written before the fix must keep working.
        certificate = self._make_certificate()
        windows_style = certificate.file_path.replace("/", "\\")
        certificate.file_path = windows_style
        certificate.save(update_fields=["file_path"])

        with override_settings(PRIVATE_MEDIA_ROOT=self.private_root):
            response = self.client.get(
                reverse("certificate-file", args=[certificate.id]))
            self.addCleanup(self._release, response)

        self.assertEqual(response.status_code, 200)

    def test_a_stored_path_cannot_escape_the_private_root(self):
        from resources import private_storage

        with override_settings(PRIVATE_MEDIA_ROOT=self.private_root):
            for hostile in ("../../../etc/passwd", r"..\..\windows\system.ini"):
                self.assertIsNone(private_storage.resolve(hostile))

    def test_a_missing_file_does_not_break_deletion(self):
        certificate = self._make_certificate()
        os.remove(os.path.join(self.private_root, certificate.file_path))

        with override_settings(PRIVATE_MEDIA_ROOT=self.private_root):
            certificate.delete()

        self.assertFalse(Certificate.objects.exists())


# ============================================================
# Transcript recognition and verification
#
# Parsing is not verification. These tests exist mostly to prove the negative:
# a document that reads cleanly still grants nothing until a person confirms
# the issuer.
# ============================================================

UM_HEADER = (
    "UNIVERSITI MALAYA\n"
    "STUDENT ACADEMIC PERFORMANCE RECORD\n"
    "Name: TEST STUDENT\n"
    "Matric No: 17204532\n"
    "Examination Result for Semester 1, Session 2023/2024\n"
)
UM_ROWS = (
    "1. WIA1002 DATA STRUCTURE 5 A 20.00\n"
    "2. WIA2003 SOFTWARE ENGINEERING 4 B 12.00\n"
    "3. WIA3001 DATABASE SYSTEMS 3 A- 11.10\n"
)


def um_transcript_text(matric="17204532", name="TEST STUDENT"):
    return (
        f"UNIVERSITI MALAYA\n"
        f"STUDENT ACADEMIC PERFORMANCE RECORD\n"
        f"Name: {name}\n"
        f"Matric No: {matric}\n"
        f"Examination Result for Semester 1, Session 2023/2024\n"
        + UM_ROWS
    )


class TranscriptClassifierTests(TestCase):
    """Recognition must not be fooled by cosmetic signals."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            email="classify@university.test", password="Strong1!",
            role=User.Role.STUDENT)
        cls.student = Student.objects.create(
            user=cls.user, student_name="Test Student",
            matric_number="17204532")

    def _classify(self, text):
        subjects, _ = parse_transcript_text(text)
        return classify_transcript(text, self.student, subjects), subjects

    def test_genuine_um_transcript_is_recognised(self):
        result, subjects = self._classify(um_transcript_text())

        self.assertEqual(result.document_type, "LIKELY_TRANSCRIPT")
        self.assertEqual(result.institution, "Universiti Malaya")
        self.assertTrue(result.identity_matched)
        self.assertGreaterEqual(result.score, 80)
        self.assertGreaterEqual(len(subjects), 2)

    def test_random_pdf_text_is_rejected(self):
        result, _ = self._classify(
            "Dear Sir, please find attached our quarterly invoice. "
            "Payment terms are 30 days.")

        self.assertEqual(result.document_type, "NOT_TRANSCRIPT")
        self.assertEqual(result.score, 0)

    def test_a_certificate_is_not_treated_as_a_transcript(self):
        result, _ = self._classify(
            "CERTIFICATE OF COMPLETION\\n"
            "This is to certify that TEST STUDENT has completed\\n"
            "the Python for Everybody course.")

        self.assertNotEqual(result.document_type, "LIKELY_TRANSCRIPT")

    def test_transcript_wording_without_an_institution_cannot_pass(self):
        """A forger can type 'Academic Transcript'; they cannot fake being a
        recognised issuer with a supported format."""
        text = um_transcript_text().replace("UNIVERSITI MALAYA", "SOME COLLEGE")

        result, _ = self._classify(text)

        self.assertNotEqual(result.document_type, "LIKELY_TRANSCRIPT")
        self.assertEqual(result.institution, "")

    def test_a_wrong_matric_number_fails_identity(self):
        result, _ = self._classify(um_transcript_text(matric="99999999"))

        self.assertFalse(result.identity_matched)
        self.assertNotEqual(result.document_type, "LIKELY_TRANSCRIPT")

    def test_identity_is_unknown_when_the_student_has_no_matric_number(self):
        """Not-checked must not be reported as checked-and-passed."""
        self.student.matric_number = ""
        self.student.save(update_fields=["matric_number"])

        result, _ = self._classify(um_transcript_text())

        self.assertIsNone(result.identity_matched)
        self.assertNotEqual(result.document_type, "LIKELY_TRANSCRIPT")

    def test_too_few_module_rows_cannot_pass(self):
        text = (
            "UNIVERSITI MALAYA\\nSTUDENT ACADEMIC PERFORMANCE RECORD\\n"
            "Matric No: 17204532\\n"
            "Examination Result for Semester 1, Session 2023/2024\\n"
            "1. WIA1002 DATA STRUCTURE 5 A 20.00\\n"
        )

        result, _ = self._classify(text)

        self.assertNotEqual(result.document_type, "LIKELY_TRANSCRIPT")

    def test_broken_grade_arithmetic_lowers_confidence(self):
        honest, _ = self._classify(um_transcript_text())
        tampered_text = um_transcript_text().replace("5 A 20.00", "5 A 99.00")

        tampered, _ = self._classify(tampered_text)

        self.assertLess(tampered.score, honest.score)

    def test_empty_text_fails_safely(self):
        result, _ = self._classify("")

        self.assertEqual(result.document_type, "NOT_TRANSCRIPT")
        self.assertIsNotNone(result.reasons)

    def test_reasons_explain_the_score(self):
        result, _ = self._classify(um_transcript_text())

        self.assertTrue(any("Matric number matches" in r for r in result.reasons))
        self.assertTrue(any("Universiti Malaya" in r for r in result.reasons))


class TranscriptUploadFlowTests(TestCase):
    """Uploading reads, applies and discards. The PDF is never kept.

    No administrator step: the automatic gates -- it parses, it classifies as
    a transcript, its matric number matches -- are the whole check, and the
    document is deleted before the response is written.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            email="upload@university.test", password="Strong1!",
            role=User.Role.STUDENT)
        self.student = Student.objects.create(
            user=self.user, student_name="Test Student", matric_number="17204532")
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        # A temporary root, removed with the test. Without it every upload
        # here wrote a real PDF into backend/private_media and left it there.
        self.private_root = tempfile.mkdtemp(prefix="mq-transcripts-")
        self.addCleanup(shutil.rmtree, self.private_root, ignore_errors=True)

    def _upload(self, text):
        """Post a PDF whose extracted text is patched to ``text``."""
        pdf = SimpleUploadedFile(
            "transcript.pdf", b"%PDF-1.4\n" + b"0" * 512,
            content_type="application/pdf")
        with patch("resources.views.extract_text_from_pdf", return_value=text), \
                override_settings(PRIVATE_MEDIA_ROOT=self.private_root):
            return self.client.post(
                "/api/resources/skill-validation/transcripts/",
                {"file": pdf, "document_consent_ack": True},
                format="multipart")

    def stored_files(self):
        folder = os.path.join(self.private_root, "transcripts")
        return os.listdir(folder) if os.path.isdir(folder) else []

    # -- the document does not survive the request -------------------------

    def test_the_pdf_is_deleted_once_it_has_been_read(self):
        response = self._upload(um_transcript_text())

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(self.stored_files(), [])
        self.assertEqual(TranscriptUpload.objects.get().file_path, "")

    def test_an_unreadable_pdf_leaves_nothing_behind(self):
        """Every exit path discards it, not only the happy one."""
        pdf = SimpleUploadedFile("t.pdf", b"%PDF-1.4\n" + b"0" * 512,
                                 content_type="application/pdf")
        with patch("resources.views.extract_text_from_pdf",
                   side_effect=RuntimeError("broken")),                 override_settings(PRIVATE_MEDIA_ROOT=self.private_root):
            response = self.client.post(
                "/api/resources/skill-validation/transcripts/",
                {"file": pdf, "document_consent_ack": True}, format="multipart")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.stored_files(), [])
        self.assertFalse(TranscriptUpload.objects.exists())

    def test_a_refused_document_is_not_kept_at_all(self):
        """No file, and no row either: a holiday booking is not a submission
        the student has to deal with, it is a mistake to tell them about."""
        response = self._upload("Trip.com booking confirmation, 7 day tour")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.stored_files(), [])
        self.assertFalse(TranscriptUpload.objects.exists())
        self.assertIn("not recognised", response.data["detail"])

    def test_a_refusal_blames_the_document_not_the_student(self):
        """A holiday booking carries no matric number, which the classifier
        reads as an identity failure. Leading with that would accuse the
        student of using someone else's results when they picked the wrong
        file."""
        response = self._upload("Trip.com booking confirmation, 7 day tour")

        self.assertNotIn("identity", response.data["detail"].lower())
        self.assertNotIn("does not match", response.data["detail"].lower())

    def test_a_scan_with_no_text_layer_is_not_kept(self):
        response = self._upload("   ")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.stored_files(), [])
        self.assertFalse(TranscriptUpload.objects.exists())

    def test_the_consent_survives_a_refusal(self):
        """Consent is append-only evidence. The student did agree, and the
        document was processed under that agreement -- deleting the record of
        a permission genuinely exercised would be tidying up history."""
        self._upload("Trip.com booking confirmation, 7 day tour")

        self.assertTrue(UserConsent.objects.filter(
            user=self.user,
            source=UserConsent.Source.TRANSCRIPT_UPLOAD).exists())

    # -- what is kept ------------------------------------------------------

    def test_the_subjects_and_grades_are_kept(self):
        self._upload(um_transcript_text())

        transcript = TranscriptUpload.objects.get()
        self.assertGreater(len(transcript.parsed_subjects), 0)
        self.assertTrue(all("code" in row and "grade" in row
                            for row in transcript.parsed_subjects))

    def test_skills_are_applied_immediately(self):
        skill = Skill.objects.create(skill_name="Data Structures")
        SubjectSkillMapping.objects.create(
            subject_code="WIA1002", skill=skill, is_active=True)

        response = self._upload(um_transcript_text())

        self.assertEqual(response.status_code, 201, response.data)
        self.assertTrue(StudentSkill.objects.filter(
            student=self.student, skill=skill).exists())
        self.assertGreater(response.data["skills_added"], 0)

    def test_the_transcript_is_auto_verified_by_classification(self):
        self._upload(um_transcript_text())

        transcript = TranscriptUpload.objects.get()
        self.assertEqual(transcript.verification_status,
                         TranscriptUpload.VerificationStatus.AUTO_VERIFIED)
        self.assertEqual(transcript.verification_method,
                         TranscriptUpload.VerificationMethod.CLASSIFICATION)
        self.assertIsNotNone(transcript.skills_applied_at)

    def test_evidence_records_which_transcript_granted_what(self):
        """The document is gone, so the evidence row is the only account of
        where a skill came from."""
        skill = Skill.objects.create(skill_name="Data Structures")
        SubjectSkillMapping.objects.create(
            subject_code="WIA1002", skill=skill, is_active=True)

        self._upload(um_transcript_text())

        evidence = TranscriptSkillEvidence.objects.get(skill=skill)
        self.assertEqual(evidence.transcript, TranscriptUpload.objects.get())
        # The fixture grades WIA1002 an A, which maps to ADVANCED.
        self.assertEqual(evidence.skill_level, "ADVANCED")

    def test_a_refused_document_grants_nothing(self):
        skill = Skill.objects.create(skill_name="Data Structures")
        SubjectSkillMapping.objects.create(
            subject_code="WIA1002", skill=skill, is_active=True)

        self._upload("Trip.com booking confirmation, 7 day tour")

        self.assertFalse(StudentSkill.objects.exists())
        self.assertFalse(TranscriptSkillEvidence.objects.exists())

    def test_the_classification_basis_is_kept_though_the_document_is_not(self):
        self._upload(um_transcript_text())

        transcript = TranscriptUpload.objects.get()
        self.assertTrue(transcript.classification_reasons)
        self.assertGreater(transcript.classification_score, 0)

    def test_the_reply_says_the_pdf_was_deleted(self):
        response = self._upload(um_transcript_text())

        self.assertIn("deleted", response.data["detail"].lower())

    def test_an_identity_mismatch_is_refused_and_grants_nothing(self):
        skill = Skill.objects.create(skill_name="Data Structures")
        SubjectSkillMapping.objects.create(
            subject_code="WIA1002", skill=skill, is_active=True)
        self.student.matric_number = "99999999"
        self.student.save(update_fields=["matric_number"])

        response = self._upload(um_transcript_text())

        self.assertEqual(response.status_code, 400)
        self.assertFalse(StudentSkill.objects.exists())
        self.assertEqual(self.stored_files(), [])
        self.assertFalse(TranscriptUpload.objects.exists())
        # This one *is* a transcript, just not theirs -- so identity is the
        # right thing to say.
        self.assertIn("does not match", response.data["detail"])


class TranscriptReviewIsRetiredTests(TestCase):
    """There is no administrator queue and no file endpoint.

    Both are gone because neither can exist: by the time an upload finishes,
    the document does not.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            email="retired@uni.test", password="Strong1!",
            role=User.Role.ADMIN, is_staff=True)
        AdminProfile.objects.create(user=self.user, admin_name="A")
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_the_review_routes_are_gone(self):
        for url in ("/api/resources/admin/transcripts/pending/",
                    "/api/resources/admin/transcripts/1/",
                    "/api/resources/admin/transcripts/1/review/",
                    "/api/resources/skill-validation/transcripts/1/file/"):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 404)


class TranscriptIdentityDistinctionTests(TestCase):
    """Absent identity and wrong identity are different findings."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            email="identity@university.test", password="Strong1!",
            role=User.Role.STUDENT)
        cls.student = Student.objects.create(
            user=cls.user, student_name="Test Student", matric_number="17204532")
        cls.admin_user = User.objects.create_user(
            email="identity@admin.test", password="Strong1!", role=User.Role.ADMIN, is_staff=True)
        cls.admin = AdminProfile.objects.create(
            user=cls.admin_user, admin_name="Reviewer")

    def _classify(self, text):
        subjects, _ = parse_transcript_text(text)
        return classify_transcript(text, self.student, subjects), subjects

    def test_a_transcript_with_no_matric_in_the_text_is_uncertain_not_refused(self):
        """UM's text layer can drop the matric number entirely. That is
        'could not check', and refusing it rejects genuine transcripts."""
        text = um_transcript_text().replace("Matric No: 17204532\n", "")

        result, subjects = self._classify(text)

        self.assertIsNone(result.identity_matched)
        self.assertEqual(result.document_type, "UNCERTAIN")
        self.assertGreaterEqual(len(subjects), 2)

    def test_a_transcript_carrying_someone_elses_matric_is_refused(self):
        result, _ = self._classify(um_transcript_text(matric="99999999"))

        self.assertFalse(result.identity_matched)
        self.assertEqual(result.document_type, "NOT_TRANSCRIPT")


class PublicUploadSafetyTests(TestCase):
    """The two public upload endpoints write into unauthenticated media.

    That makes the accepted file type the whole of the security boundary: an
    .html or .svg served from the application's own origin can run script
    against anyone who opens it.
    """

    @classmethod
    def setUpTestData(cls):
        cls.company_user = User.objects.create_user(
            email="upload@business.test", password="Strong1!", role=User.Role.COMPANY)
        Company.objects.create(user=cls.company_user, company_name="Uploader Ltd")
        cls.admin_user = User.objects.create_user(
            email="upload@admin.test", password="Strong1!", role=User.Role.ADMIN, is_staff=True)
        AdminProfile.objects.create(user=cls.admin_user, admin_name="Uploader")

    def setUp(self):
        self.client = APIClient()

    ENDPOINTS = (
        ("company_user", "/api/resources/training/upload/"),
        ("admin_user", "/api/dashboard/announcements/upload/"),
    )

    def _post(self, actor, url, upload):
        self.client.force_authenticate(getattr(self, actor))
        return self.client.post(url, {"file": upload}, format="multipart")

    def test_html_is_refused(self):
        for actor, url in self.ENDPOINTS:
            payload = SimpleUploadedFile(
                "poster.html", b"<script>alert(document.cookie)</script>",
                content_type="text/html")
            response = self._post(actor, url, payload)
            self.assertEqual(response.status_code, 400, url)

    def test_svg_is_refused(self):
        """An SVG is a script container that browsers render inline."""
        for actor, url in self.ENDPOINTS:
            payload = SimpleUploadedFile(
                "poster.svg", b"<svg xmlns='http://www.w3.org/2000/svg'>"
                              b"<script>alert(1)</script></svg>",
                content_type="image/svg+xml")
            response = self._post(actor, url, payload)
            self.assertEqual(response.status_code, 400, url)

    def test_an_executable_renamed_to_pdf_is_refused_on_its_bytes(self):
        for actor, url in self.ENDPOINTS:
            payload = SimpleUploadedFile(
                "poster.pdf", b"MZ\x90\x00 this is a windows executable",
                content_type="application/pdf")
            response = self._post(actor, url, payload)
            self.assertEqual(response.status_code, 400, url)

    def test_an_oversized_upload_is_refused(self):
        for actor, url in self.ENDPOINTS:
            payload = SimpleUploadedFile(
                "poster.pdf", b"%PDF-1.4\n" + b"0" * (11 * 1024 * 1024),
                content_type="application/pdf")
            response = self._post(actor, url, payload)
            self.assertEqual(response.status_code, 400, url)

    def test_a_real_pdf_is_accepted_and_stored_under_a_generated_name(self):
        for actor, url in self.ENDPOINTS:
            payload = SimpleUploadedFile(
                "My Poster.pdf", b"%PDF-1.4\n" + b"0" * 512,
                content_type="application/pdf")
            response = self._post(actor, url, payload)

            self.assertEqual(response.status_code, 201, response.data)
            stored = response.data["url"]
            self.assertTrue(stored.endswith(".pdf"), stored)
            self.assertNotIn("My Poster", stored,
                             "the client filename must not reach the stored path")

    def test_an_unauthenticated_visitor_cannot_upload(self):
        for _, url in self.ENDPOINTS:
            self.client.force_authenticate(None)
            payload = SimpleUploadedFile(
                "poster.pdf", b"%PDF-1.4\n" + b"0" * 512,
                content_type="application/pdf")
            response = self.client.post(url, {"file": payload}, format="multipart")
            self.assertIn(response.status_code, (401, 403), url)


class EndorsementIsFinalTests(TestCase):
    """A decision cannot be reversed while revocation is undefined."""

    @classmethod
    def setUpTestData(cls):
        cls.student_user = User.objects.create_user(
            email="final@university.test", password="Strong1!", role=User.Role.STUDENT)
        cls.student = Student.objects.create(
            user=cls.student_user, student_name="Final")
        cls.admin_user = User.objects.create_user(
            email="final@admin.test", password="Strong1!", role=User.Role.ADMIN, is_staff=True)
        AdminProfile.objects.create(user=cls.admin_user, admin_name="Decider")
        cls.skill = Skill.objects.create(skill_name="Final Skill")

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.admin_user)
        self.certificate = Certificate.objects.create(
            student=self.student, cert_url="https://example.test/c")
        CertificateSkillEvidence.objects.create(
            certificate=self.certificate, skill=self.skill,
            claimed_level="INTERMEDIATE")

    def _decide(self, payload):
        if payload.get("verified_status") == "APPROVED" and "skills" not in payload:
            payload = dict(payload, skills=[
                {"skill_id": self.skill.id, "approved_level": "INTERMEDIATE"}])
        return self.client.patch(
            f"/api/resources/certificates/{self.certificate.pk}/endorse/",
            payload, format="json")

    def test_a_pending_submission_can_be_approved(self):
        response = self._decide({"verified_status": "APPROVED"})

        self.assertEqual(response.status_code, 200, response.data)

    def test_an_approved_submission_cannot_then_be_rejected(self):
        """Rejecting did not take the granted skill back, so the certificate
        read REJECTED while the skill it produced stayed on the profile."""
        self._decide({"verified_status": "APPROVED"})

        response = self._decide({
            "verified_status": "REJECTED", "rejection_reason": "NAME_MISMATCH"})

        self.assertEqual(response.status_code, 400)
        self.assertIn("verified_status", response.data)
        self.certificate.refresh_from_db()
        self.assertEqual(self.certificate.verified_status, "APPROVED")

    def test_the_granted_skill_survives_the_refused_reversal(self):
        self._decide({"verified_status": "APPROVED"})
        self._decide({
            "verified_status": "REJECTED", "rejection_reason": "NAME_MISMATCH"})

        self.assertTrue(StudentSkill.objects.filter(
            student=self.student, skill=self.skill).exists())

    def test_a_rejected_submission_cannot_be_approved_later(self):
        self._decide({
            "verified_status": "REJECTED", "rejection_reason": "UNREADABLE_DOCUMENT"})

        response = self._decide({"verified_status": "APPROVED"})

        self.assertEqual(response.status_code, 400)
        self.assertFalse(StudentSkill.objects.filter(
            student=self.student, skill=self.skill).exists())


# ---------------------------------------------------------------------------
# Multi-skill certificate evidence, and the recalculation that keeps
# StudentSkill equal to what the evidence actually supports
# ---------------------------------------------------------------------------


class MultiSkillCertificateUploadTests(PrivacyTestBase):
    """One document, several claims, stored once."""

    def _upload_claiming(self, claims, **extra):
        payload = {
            "skills": json.dumps(claims),
            "source": "Example Academy",
            "certificate_name": "Data Analytics Programme",
            "document_consent_ack": True,
            "file": _pdf(),
        }
        payload.update(extra)
        with override_settings(PRIVATE_MEDIA_ROOT=self.private_root):
            return self.client.post(
                reverse("certificate-list"), payload, format="multipart")

    def setUp(self):
        super().setUp()
        self.sql = Skill.objects.create(skill_name="SQL")
        self.viz = Skill.objects.create(skill_name="Data Visualisation")
        self.client.force_authenticate(user=self.user)

    def test_one_certificate_can_claim_several_skills(self):
        response = self._upload_claiming([
            {"skill_id": self.skill.id, "claimed_level": "INTERMEDIATE"},
            {"skill_id": self.sql.id, "claimed_level": "INTERMEDIATE"},
            {"skill_id": self.viz.id, "claimed_level": "BEGINNER"},
        ])

        self.assertEqual(response.status_code, 201, response.data)
        certificate = Certificate.objects.latest("id")
        self.assertEqual(certificate.skill_evidence.count(), 3)
        # One document on disk, not three.
        self.assertEqual(Certificate.objects.count(), 1)

    def test_the_claimed_levels_are_recorded_per_skill(self):
        self._upload_claiming([
            {"skill_id": self.skill.id, "claimed_level": "ADVANCED"},
            {"skill_id": self.sql.id, "claimed_level": "BEGINNER"},
        ])

        levels = dict(Certificate.objects.latest("id").skill_evidence
                      .values_list("skill__skill_name", "claimed_level"))
        self.assertEqual(levels[self.skill.skill_name], "ADVANCED")
        self.assertEqual(levels["SQL"], "BEGINNER")

    def test_a_duplicate_skill_in_one_upload_is_refused(self):
        response = self._upload_claiming([
            {"skill_id": self.skill.id, "claimed_level": "BEGINNER"},
            {"skill_id": self.skill.id, "claimed_level": "ADVANCED"},
        ])

        self.assertEqual(response.status_code, 400)
        self.assertIn("skills", response.data)
        self.assertFalse(Certificate.objects.exists())

    def test_an_upload_claiming_no_skill_is_refused(self):
        response = self._upload_claiming([])

        self.assertEqual(response.status_code, 400)
        self.assertFalse(Certificate.objects.exists())

    def test_an_unknown_skill_id_is_refused(self):
        response = self._upload_claiming([{"skill_id": 999999}])

        self.assertEqual(response.status_code, 400)
        self.assertFalse(Certificate.objects.exists())

    def test_an_invalid_level_is_refused(self):
        response = self._upload_claiming(
            [{"skill_id": self.skill.id, "claimed_level": "EXPERT"}])

        self.assertEqual(response.status_code, 400)
        self.assertFalse(Certificate.objects.exists())

    def test_more_than_ten_skills_is_refused(self):
        extras = [Skill.objects.create(skill_name=f"Skill {i}") for i in range(12)]

        response = self._upload_claiming(
            [{"skill_id": skill.id} for skill in extras])

        self.assertEqual(response.status_code, 400)
        self.assertFalse(Certificate.objects.exists())

    def test_a_pending_certificate_grants_nothing(self):
        self._upload_claiming([
            {"skill_id": self.skill.id, "claimed_level": "ADVANCED"},
            {"skill_id": self.sql.id, "claimed_level": "ADVANCED"},
        ])

        self.assertFalse(StudentSkill.objects.filter(student=self.student).exists())


class CertificateSkillReviewTests(PrivacyTestBase):
    """An administrator decides each claim, not only the document."""

    def setUp(self):
        super().setUp()
        self.sql = Skill.objects.create(skill_name="SQL")
        self.viz = Skill.objects.create(skill_name="Data Visualisation")
        self.certificate = Certificate.objects.create(
            student=self.student, certificate_name="Data Analytics Programme",
            cert_url="https://example.test/cert")
        for skill, level in ((self.skill, "ADVANCED"),
                             (self.sql, "INTERMEDIATE"),
                             (self.viz, "BEGINNER")):
            CertificateSkillEvidence.objects.create(
                certificate=self.certificate, skill=skill, claimed_level=level)
        self.client.force_authenticate(user=self.admin_user)

    def _decide(self, payload):
        return self.client.patch(
            reverse("certificate-endorse", args=[self.certificate.id]),
            payload, format="json")

    def levels(self):
        return dict(StudentSkill.objects
                    .filter(student=self.student)
                    .values_list("skill__skill_name", "skill_level"))

    def test_approving_every_claim_grants_every_skill(self):
        response = self._decide({"verified_status": "APPROVED", "skills": [
            {"skill_id": self.skill.id, "approved_level": "ADVANCED"},
            {"skill_id": self.sql.id, "approved_level": "INTERMEDIATE"},
            {"skill_id": self.viz.id, "approved_level": "BEGINNER"},
        ]})

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(self.levels(), {
            self.skill.skill_name: "ADVANCED",
            "SQL": "INTERMEDIATE",
            "Data Visualisation": "BEGINNER",
        })

    def test_an_administrator_can_approve_a_subset(self):
        """The common case: a broad programme over-claims."""
        self._decide({"verified_status": "APPROVED", "skills": [
            {"skill_id": self.skill.id, "approved_level": "ADVANCED"},
        ]})

        self.assertEqual(self.levels(), {self.skill.skill_name: "ADVANCED"})
        statuses = dict(self.certificate.skill_evidence
                        .values_list("skill__skill_name", "review_status"))
        self.assertEqual(statuses["SQL"], "REJECTED")
        self.assertEqual(statuses["Data Visualisation"], "REJECTED")

    def test_an_exaggerated_claim_can_be_lowered(self):
        self._decide({"verified_status": "APPROVED", "skills": [
            {"skill_id": self.skill.id, "approved_level": "BEGINNER",
             "review_note": "The syllabus covers the basics only."},
        ]})

        self.assertEqual(self.levels(), {self.skill.skill_name: "BEGINNER"})
        evidence = self.certificate.skill_evidence.get(skill=self.skill)
        # The claim survives the correction: overwriting it would destroy the
        # evidence that it was ever corrected.
        self.assertEqual(evidence.claimed_level, "ADVANCED")
        self.assertEqual(evidence.approved_level, "BEGINNER")

    def test_an_approved_certificate_can_carry_rejected_claims(self):
        self._decide({"verified_status": "APPROVED", "skills": [
            {"skill_id": self.sql.id, "approved_level": "INTERMEDIATE"},
        ]})
        self.certificate.refresh_from_db()

        self.assertEqual(self.certificate.verified_status, "APPROVED")
        self.assertEqual(
            self.certificate.skill_evidence.filter(review_status="REJECTED").count(), 2)

    def test_rejecting_the_document_rejects_every_claim(self):
        self._decide({"verified_status": "REJECTED",
                      "rejection_reason": "UNREADABLE_DOCUMENT"})

        self.assertEqual(self.levels(), {})
        self.assertEqual(
            self.certificate.skill_evidence.exclude(review_status="REJECTED").count(), 0)

    def test_approving_nothing_is_refused(self):
        response = self._decide({"verified_status": "APPROVED", "skills": []})

        self.assertEqual(response.status_code, 400)
        self.assertIn("skills", response.data)

    def test_a_skill_the_document_never_claimed_cannot_be_granted(self):
        other = Skill.objects.create(skill_name="Kubernetes")

        response = self._decide({"verified_status": "APPROVED", "skills": [
            {"skill_id": other.id, "approved_level": "ADVANCED"},
        ]})

        self.assertEqual(response.status_code, 400)
        self.assertFalse(StudentSkill.objects.filter(skill=other).exists())

    def test_the_student_sees_every_approved_skill_on_one_certificate(self):
        self._decide({"verified_status": "APPROVED", "skills": [
            {"skill_id": self.skill.id, "approved_level": "INTERMEDIATE"},
            {"skill_id": self.sql.id, "approved_level": "INTERMEDIATE"},
        ]})
        self.client.force_authenticate(user=self.user)

        rows = self.client.get(reverse("certificate-list")).data
        row = next(r for r in rows if r["id"] == self.certificate.id)

        self.assertEqual(len(row["skill_evidence"]), 3)
        granted = {e["skill"]: e["granted_level"] for e in row["skill_evidence"]}
        self.assertEqual(granted[self.skill.skill_name], "INTERMEDIATE")
        self.assertEqual(granted["SQL"], "INTERMEDIATE")
        # Refused claims come back with nothing granted rather than vanishing:
        # the student should see what was decided about each one.
        self.assertIsNone(granted["Data Visualisation"])


class HighestLiveEvidenceTests(TestCase):
    """StudentSkill always equals the highest level live evidence supports."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="evidence@uni.test", password="pw", role="STUDENT")
        self.student = Student.objects.create(user=self.user, student_name="S")
        self.python = Skill.objects.create(skill_name="Python")

    def certificate(self, level, status="APPROVED", review="APPROVED"):
        certificate = Certificate.objects.create(
            student=self.student, cert_url=f"https://example.test/{level}{status}",
            verified_status=status)
        CertificateSkillEvidence.objects.create(
            certificate=certificate, skill=self.python,
            claimed_level=level,
            approved_level=level if review == "APPROVED" else "",
            review_status=review)
        return certificate

    def level(self):
        row = StudentSkill.objects.filter(
            student=self.student, skill=self.python).first()
        return row.skill_level if row else None

    def test_two_certificates_keep_the_highest_level(self):
        self.certificate("BEGINNER")
        self.certificate("ADVANCED")

        recalculate_student_skills(self.student, skills=[self.python])

        self.assertEqual(self.level(), "ADVANCED")

    def test_a_later_lower_certificate_does_not_downgrade(self):
        self.certificate("ADVANCED")
        recalculate_student_skills(self.student, skills=[self.python])

        self.certificate("BEGINNER")
        recalculate_student_skills(self.student, skills=[self.python])

        self.assertEqual(self.level(), "ADVANCED")

    def test_removing_the_highest_evidence_drops_to_the_next(self):
        """The bug this service exists to fix: the level used to outlive its
        evidence, leaving a student showing Advanced backed by nothing."""
        advanced = self.certificate("ADVANCED")
        self.certificate("BEGINNER")
        recalculate_student_skills(self.student, skills=[self.python])
        self.assertEqual(self.level(), "ADVANCED")

        advanced.delete()
        recalculate_student_skills(self.student, skills=[self.python])

        self.assertEqual(self.level(), "BEGINNER")

    def test_removing_all_evidence_removes_the_skill(self):
        certificate = self.certificate("INTERMEDIATE")
        recalculate_student_skills(self.student, skills=[self.python])
        self.assertEqual(self.level(), "INTERMEDIATE")

        certificate.delete()
        recalculate_student_skills(self.student, skills=[self.python])

        self.assertIsNone(self.level())

    def test_pending_evidence_counts_for_nothing(self):
        self.certificate("ADVANCED", status="PENDING", review="PENDING")

        recalculate_student_skills(self.student, skills=[self.python])

        self.assertIsNone(self.level())

    def test_a_rejected_claim_on_an_approved_document_counts_for_nothing(self):
        self.certificate("ADVANCED", status="APPROVED", review="REJECTED")

        recalculate_student_skills(self.student, skills=[self.python])

        self.assertIsNone(self.level())

    def test_a_withdrawn_consent_takes_its_evidence_with_it(self):
        certificate = self.certificate("ADVANCED")
        consent = UserConsent.objects.create(
            user=self.user,
            consent_type=UserConsent.ConsentType.DOCUMENT_VERIFICATION_CONSENT,
            notice_version="1.1", accepted=True, accepted_at=timezone.now(),
            source=UserConsent.Source.CERTIFICATE_UPLOAD)
        certificate.upload_consent = consent
        certificate.save(update_fields=["upload_consent"])
        recalculate_student_skills(self.student, skills=[self.python])
        self.assertEqual(self.level(), "ADVANCED")

        consent.withdrawn_at = timezone.now()
        consent.save(update_fields=["withdrawn_at"])
        recalculate_student_skills(self.student, skills=[self.python])

        self.assertIsNone(self.level())

    def test_a_skill_with_no_recorded_provenance_is_left_alone(self):
        """Transcripts uploaded before evidence tracking granted skills with
        nothing recorded about where they came from. Deleting those would be
        guessing, so a whole-profile pass leaves them in place and the
        management command reports them."""
        StudentSkill.objects.create(
            student=self.student, skill=self.python, skill_level="ADVANCED")

        recalculate_student_skills(self.student)

        self.assertEqual(self.level(), "ADVANCED")

    def test_recalculate_one_skill_returns_the_row(self):
        self.certificate("INTERMEDIATE")

        row = recalculate_student_skill(self.student, self.python)

        self.assertIsNotNone(row)
        self.assertEqual(row.skill_level, "INTERMEDIATE")


class EvidenceBackfillTests(TransactionTestCase):
    """Every pre-existing certificate keeps its claim.

    Run through the migration executor rather than against the live models:
    ``Certificate.skill`` is gone from the current schema, so the only place
    the backfill can be exercised is the historical state it was written for.
    Reimplementing its logic in the test would leave the copy free to drift
    from what actually runs.
    """

    BEFORE = ("resources", "0011_alter_certificate_skill_certificateskillevidence")
    AFTER = ("resources", "0012_backfill_certificate_skill_evidence")

    def migrate_to(self, target):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate([target])
        executor.loader.build_graph()
        return executor.loader.project_state([target]).apps

    def tearDown(self):
        # Leave the database at the latest state for whatever runs next.
        call_command("migrate", "resources", verbosity=0)

    def seed(self, apps, statuses):
        User = apps.get_model("accounts", "User")
        Student = apps.get_model("accounts", "Student")
        Skill = apps.get_model("scrape_jobs", "Skill")
        Certificate = apps.get_model("resources", "Certificate")

        user = User.objects.create(email="backfill@uni.test", role="STUDENT",
                                   password="x")
        student = Student.objects.create(user=user, student_name="S")
        skill = Skill.objects.create(skill_name="Python")
        for index, status in enumerate(statuses):
            Certificate.objects.create(
                student=student, skill=skill,
                cert_url=f"https://example.test/{index}",
                verified_status=status,
                verified_at=timezone.now() if status != "PENDING" else None)
        return Certificate

    def test_an_approved_certificate_becomes_approved_evidence(self):
        apps = self.migrate_to(self.BEFORE)
        self.seed(apps, ["APPROVED"])

        after = self.migrate_to(self.AFTER)
        evidence = after.get_model("resources", "CertificateSkillEvidence").objects.get()

        self.assertEqual(evidence.review_status, "APPROVED")
        self.assertEqual(evidence.approved_level, "INTERMEDIATE")
        self.assertEqual(evidence.claimed_level, "INTERMEDIATE")

    def test_a_pending_certificate_grants_nothing(self):
        apps = self.migrate_to(self.BEFORE)
        self.seed(apps, ["PENDING"])

        after = self.migrate_to(self.AFTER)
        evidence = after.get_model("resources", "CertificateSkillEvidence").objects.get()

        self.assertEqual(evidence.review_status, "PENDING")
        self.assertEqual(evidence.approved_level, "")

    def test_a_rejected_certificate_becomes_rejected_evidence(self):
        apps = self.migrate_to(self.BEFORE)
        self.seed(apps, ["REJECTED"])

        after = self.migrate_to(self.AFTER)
        evidence = after.get_model("resources", "CertificateSkillEvidence").objects.get()

        self.assertEqual(evidence.review_status, "REJECTED")
        self.assertEqual(evidence.approved_level, "")

    def test_the_migrated_counts_match(self):
        apps = self.migrate_to(self.BEFORE)
        Certificate = self.seed(apps, ["APPROVED", "PENDING", "REJECTED"])
        before = Certificate.objects.count()

        after = self.migrate_to(self.AFTER)

        self.assertEqual(
            after.get_model("resources", "CertificateSkillEvidence").objects.count(),
            before)





class CourseCatalogueScrapeTests(TestCase):
    """The two passes that replaced title-filtered scraping.

    The old path kept a course only when a Skill name appeared in its title,
    which is why 59 rows survived a ~145-link ceiling. These cover the two
    properties that changed: nothing is discarded at fetch time, and skills are
    decided separately and re-runnably.

    The second argument to the parser is now the search phrase that surfaced
    the page rather than a Coursera category -- the category walk was removed
    when the site turned out not to paginate -- but what it records is the same
    kind of thing: where a course was found, kept apart from what it teaches.
    """

    LISTING = """
      <ul>
        <li><a href="/learn/python-basics"><h3>Python for Everybody</h3>
            <p>Skills you'll gain: Python, Programming</p></a></li>
        <li><a href="/professional-certificates/google-data-analytics">
            <h3>Google Data Analytics Professional Certificate</h3>
            <p>Skills you'll gain: SQL, Tableau</p></a></li>
        <li><a href="/learn/basket-weaving"><h3>Introduction to Basket Weaving</h3>
            <p>Skills you'll gain: Patience</p></a></li>
        <li><a href="/about">About us</a></li>
      </ul>
    """

    def setUp(self):
        for name in ("Python", "SQL", "Tableau"):
            Skill.objects.create(skill_name=name, skill_category="Technical")

    def test_parse_keeps_every_course_and_ignores_non_courses(self):
        from resources.scraper import _parse_coursera_cards

        by_url = {}
        found = _parse_coursera_cards(self.LISTING, "Data Science", by_url)

        self.assertEqual(found, 3)
        # The basket-weaving course names no skill and is kept anyway -- that is
        # the whole change. /about is not a course and is not.
        self.assertEqual(
            sorted(url.rsplit("/", 1)[-1] for url in by_url),
            ["basket-weaving", "google-data-analytics", "python-basics"],
        )
        certificate = by_url["https://www.coursera.org/professional-certificates/google-data-analytics"]
        self.assertEqual(certificate["type"], "Professional Certificate")
        self.assertIn("Tableau", certificate["card_text"])

    def test_a_course_seen_twice_is_one_row_carrying_both_origins(self):
        from resources.scraper import _parse_coursera_cards

        by_url = {}
        _parse_coursera_cards(self.LISTING, "Data Science", by_url)
        added = _parse_coursera_cards(self.LISTING, "Computer Science", by_url)

        self.assertEqual(added, 0)
        self.assertEqual(len(by_url), 3)
        self.assertEqual(
            by_url["https://www.coursera.org/learn/python-basics"]["discovered_via"],
            ["Data Science", "Computer Science"],
        )

    def test_mapping_writes_one_resource_per_matched_skill(self):
        from resources.scraper import _parse_coursera_cards
        from resources.services import map_catalogue_to_skills, save_course_catalogue

        by_url = {}
        _parse_coursera_cards(self.LISTING, "Data Science", by_url)
        created, _ = save_course_catalogue(list(by_url.values()))
        self.assertEqual(created, 3)

        mapped, _, unmapped = map_catalogue_to_skills(platform_name="Coursera")

        # The certificate matches two skills off its card text, not its title --
        # the case the old title-only filter threw away entirely.
        certificate_skills = set(
            LearningResource.objects
            .filter(url__contains="google-data-analytics")
            .values_list("skill__skill_name", flat=True)
        )
        self.assertEqual(certificate_skills, {"SQL", "Tableau"})
        self.assertEqual(mapped, 3)
        # Kept, not deleted: a later re-map can pick it up once the Skill table
        # knows the word.
        self.assertEqual(unmapped, 1)
        self.assertTrue(
            CourseCatalogue.objects.filter(url__contains="basket-weaving").exists()
        )

    def test_mapping_is_rerunnable_and_picks_up_new_skills(self):
        from resources.scraper import _parse_coursera_cards
        from resources.services import map_catalogue_to_skills, save_course_catalogue

        by_url = {}
        _parse_coursera_cards(self.LISTING, "Data Science", by_url)
        save_course_catalogue(list(by_url.values()))
        map_catalogue_to_skills(platform_name="Coursera")

        # No re-scrape: the catalogue is the input, which is why the passes are
        # separate at all.
        Skill.objects.create(skill_name="Patience", skill_category="Soft Skill")
        created, updated, unmapped = map_catalogue_to_skills(platform_name="Coursera")

        self.assertEqual(created, 1)
        self.assertEqual(unmapped, 0)
        self.assertTrue(updated)
        self.assertTrue(
            LearningResource.objects
            .filter(url__contains="basket-weaving", skill__skill_name="Patience")
            .exists()
        )


class SkillSelectionControlTests(TestCase):
    """What the picker hides, the serializer must also refuse.

    The picker endpoint filtered retired and unreviewed skills out of what it
    offered, but the serializers behind it took any primary key at all. The
    rule therefore held only for callers who used the form, and a hand-made
    request could attach certificate evidence to a skill the catalogue does
    not stand behind -- including one an employer had just typed into a job
    form and that was sitting in quarantine.
    """

    def setUp(self):
        self.good = Skill.objects.create(skill_name="Python")
        self.retired = Skill.objects.create(
            skill_name="Silverlight",
            catalogue_status=Skill.CatalogueStatus.DEPRECATED)
        self.quarantined = Skill.objects.create(
            skill_name="Pyhton", is_active=False,
            catalogue_status=Skill.CatalogueStatus.REVIEW_REQUIRED)
        self.inactive = Skill.objects.create(skill_name="Flash",
                                             is_active=False)

    def test_selectable_offers_only_skills_the_catalogue_stands_behind(self):
        # Scoped to this test's own rows: the test database carries whatever
        # the migrations seeded, and asserting over the whole table would make
        # this fail for a reason that is not the rule under test.
        mine = [self.good, self.retired, self.quarantined, self.inactive]
        selectable = set(
            Skill.objects.selectable()
            .filter(id__in=[skill.id for skill in mine])
            .values_list("skill_name", flat=True))

        self.assertEqual(selectable, {"Python"})

    def test_a_claimed_skill_must_be_selectable(self):
        from .serializers import ClaimedSkillSerializer

        ok = ClaimedSkillSerializer(data={"skill_id": self.good.id})
        self.assertTrue(ok.is_valid(), ok.errors)

        for skill in (self.retired, self.quarantined, self.inactive):
            with self.subTest(skill=skill.skill_name):
                serializer = ClaimedSkillSerializer(data={"skill_id": skill.id})
                self.assertFalse(serializer.is_valid())
                self.assertIn("skill_id", serializer.errors)

    def test_an_approved_skill_must_be_selectable(self):
        """The admin side needs the same rule.

        An administrator approving evidence against a quarantined skill would
        promote it by use, which is the review step happening backwards.
        """
        from .serializers import ApprovedSkillSerializer

        serializer = ApprovedSkillSerializer(data={
            "skill_id": self.quarantined.id, "approved_level": "INTERMEDIATE"})

        self.assertFalse(serializer.is_valid())
        self.assertIn("skill_id", serializer.errors)


class SkillQuarantineOnWriteTests(TestCase):
    """A free-text skill name never enters the vocabulary already trusted.

    A name typed into a course or training-programme form used to land as a
    fully active, ACTIVE_INTERNAL skill -- indistinguishable from a curated
    one -- so a company's typo or vague phrase joined the global vocabulary
    and the extractor matched it against every scraped advert from then on.
    """

    def test_a_new_name_is_quarantined_not_published(self):
        from .serializers import resolve_or_quarantine_skill

        skill = resolve_or_quarantine_skill("Superb Communicaton")

        self.assertFalse(skill.is_active)
        self.assertEqual(skill.catalogue_status,
                         Skill.CatalogueStatus.REVIEW_REQUIRED)
        # And so it cannot be picked, which is the point of quarantining it.
        self.assertNotIn(skill.id,
                         Skill.objects.selectable().values_list("id", flat=True))

    def test_an_existing_skill_is_reused_and_not_downgraded(self):
        """Matching an existing name must not touch its status.

        Otherwise typing a curated skill's name into a course form would
        quarantine the curated skill.
        """
        from .serializers import resolve_or_quarantine_skill

        existing = Skill.objects.create(skill_name="Django")

        resolved = resolve_or_quarantine_skill("django")

        self.assertEqual(resolved.id, existing.id)
        resolved.refresh_from_db()
        self.assertTrue(resolved.is_active)
        self.assertEqual(resolved.catalogue_status,
                         Skill.CatalogueStatus.ACTIVE_INTERNAL)

    def test_a_blank_name_creates_nothing(self):
        from .serializers import resolve_or_quarantine_skill

        before = Skill.objects.count()

        self.assertIsNone(resolve_or_quarantine_skill("   "))
        self.assertIsNone(resolve_or_quarantine_skill(None))
        self.assertEqual(Skill.objects.count(), before)


class SearchPhraseNormalisationTests(TestCase):
    """The search phrase and the canonical skill are different strings.

    "RCA" is the catalogue's name for the skill; typing it into a course search
    returns chemistry. "Root Cause Analysis" returns the courses. Conflating
    the two is why searching by skill would otherwise under-perform on exactly
    the abbreviations Malaysian adverts use most.
    """

    def test_an_abbreviation_searches_by_its_reviewed_expansion(self):
        from .search_terms import search_phrase

        self.assertEqual(
            search_phrase("UAT", ["User Acceptance Testing"]),
            "User Acceptance Testing")
        self.assertEqual(
            search_phrase("RCA", ["Root Cause Analysis"]),
            "Root Cause Analysis")

    def test_a_spelled_out_name_is_left_alone(self):
        """Only abbreviations are expanded.

        "Microsoft SQL Server" already reads as a phrase; rewriting it could
        only make the search worse.
        """
        from .search_terms import search_phrase

        self.assertEqual(
            search_phrase("Microsoft SQL Server", ["MSSQL", "SQL Server"]),
            "Microsoft SQL Server")

    def test_another_abbreviation_is_not_mistaken_for_an_expansion(self):
        """MSSQL does not spell MS SQL out; it is a second abbreviation."""
        from .search_terms import search_phrase

        self.assertEqual(search_phrase("UAT", ["UATx", "UA"]), "UAT")

    def test_an_override_beats_the_alias_table(self):
        """SAP's longest alias is a product, not an expansion.

        "SAP Business One" would narrow a vendor-wide search to one SMB
        product, so the override refuses the expansion.
        """
        from .search_terms import search_phrase

        self.assertEqual(
            search_phrase("SAP", ["SAP B1", "SAP Business One", "SAP ERP"]),
            "SAP")

    def test_contextual_aliases_are_never_used_as_phrases(self):
        from .search_terms import phrases_for_skills

        skill = Skill.objects.create(skill_name="XYZ")
        SkillAlias.objects.create(skill=skill, alias_name="Extended Yield Zone",
                                  requires_context=True)

        self.assertEqual(phrases_for_skills([skill]), [("XYZ", "XYZ")])


class CourseIdentityTests(TestCase):
    """One course is one row, however its URL arrived."""

    def test_tracking_parameters_and_slashes_collapse_to_one_identity(self):
        from .scraper import canonical_course_url

        variants = [
            "/learn/abap-fundamentals",
            "/learn/abap-fundamentals/",
            "https://www.coursera.org/learn/abap-fundamentals?msockid=abc",
            "https://www.coursera.org/learn/abap-fundamentals#syllabus",
        ]
        canonical = {canonical_course_url(v) for v in variants}

        self.assertEqual(
            canonical, {"https://www.coursera.org/learn/abap-fundamentals"})

    def test_one_course_found_by_two_searches_is_one_row_carrying_both(self):
        from .scraper import _parse_coursera_cards

        html = ('<li><a href="/learn/x"><h3>SAP ABAP Fundamentals</h3>'
                '<p>Skills you will gain: ABAP</p></a></li>')
        by_url = {}
        _parse_coursera_cards(html, "SAP ABAP", by_url)
        added = _parse_coursera_cards(html, "SAP", by_url)

        self.assertEqual(added, 0)
        self.assertEqual(len(by_url), 1)
        self.assertEqual(
            list(by_url.values())[0]["discovered_via"], ["SAP ABAP", "SAP"])


class MappingUsesContentNotTheQueryTests(TestCase):
    """A course is filed by what it teaches, never by what found it."""

    def test_the_search_phrase_is_not_evidence(self):
        """The whole point of separating retrieval from mapping.

        A "Root Cause Analysis" search surfaces Six Sigma courses; filing them
        under RCA because the search found them would record the search, not
        the course.
        """
        from .services import map_catalogue_to_skills, save_course_catalogue

        Skill.objects.create(skill_name="Kubernetes")
        save_course_catalogue([{
            "url": "https://www.coursera.org/learn/unrelated",
            "title": "Introduction to Watercolour Painting",
            "platform": "Coursera", "type": "Course",
            "discovered_via": ["Kubernetes"],
            "card_text": "Skills you will gain: Brushwork, Colour Theory",
        }])

        map_catalogue_to_skills(platform_name="Coursera")

        self.assertFalse(
            LearningResource.objects.filter(skill__skill_name="Kubernetes")
            .exists())
        # Kept, not deleted: a later re-map can pick it up if the catalogue grows.
        self.assertTrue(
            CourseCatalogue.objects.filter(url__endswith="unrelated").exists())

    def test_content_evidence_does_map(self):
        from .services import map_catalogue_to_skills, save_course_catalogue

        Skill.objects.create(skill_name="ABAP")
        save_course_catalogue([{
            "url": "https://www.coursera.org/learn/abap",
            "title": "Learn SAP ABAP Fundamentals",
            "platform": "Coursera", "type": "Course",
            "discovered_via": ["SAP ABAP"],
            "card_text": "Skills you will gain: ABAP, SAP",
        }])

        map_catalogue_to_skills(platform_name="Coursera")

        self.assertTrue(
            LearningResource.objects.filter(skill__skill_name="ABAP").exists())


class ResourceSeedReproducibilityTests(TestCase):
    """A fresh database must rebuild what students are shown.

    The scraper cannot be the production bootstrap: Coursera re-ranks results
    and changes markup, so two deployments scraping on different days would
    recommend different courses from identical code -- quite apart from needing
    Chrome and outbound network access to deploy.
    """

    def test_seed_files_rebuild_the_catalogue_exactly(self):
        from django.core.management import call_command
        from io import StringIO
        from .seeds import (DATA_DIR, database_snapshot, file_snapshot,
                            snapshot_digest)

        CourseCatalogue.objects.all().delete()
        LearningResource.objects.all().delete()

        # The documented bootstrap order, and the reason it is an order: a
        # resource names its skill by string, so a database without the skill
        # catalogue silently drops every resource whose skill it cannot find.
        # Importing resources alone rebuilt 146 of 2,165 rows and looked like a
        # seeding bug rather than a missing prerequisite.
        call_command("import_skills", verbosity=0)
        call_command("import_resources", stdout=StringIO())

        self.assertEqual(snapshot_digest(database_snapshot()),
                         snapshot_digest(file_snapshot(DATA_DIR)))

    def test_import_is_idempotent(self):
        from django.core.management import call_command
        from io import StringIO
        from .seeds import database_snapshot, snapshot_digest

        CourseCatalogue.objects.all().delete()
        LearningResource.objects.all().delete()
        call_command("import_skills", verbosity=0)
        call_command("import_resources", stdout=StringIO())
        once = snapshot_digest(database_snapshot())

        call_command("import_resources", stdout=StringIO())

        self.assertEqual(snapshot_digest(database_snapshot()), once)
