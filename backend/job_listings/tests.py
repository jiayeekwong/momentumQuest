import os
import tempfile
import time
from datetime import timedelta
from unittest.mock import patch

from django.core import signing

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import (
    AdminProfile, Company, Student, StudentSkill, User, UserConsent,
)
from . import cv_receipt
from resources.models import Certificate, CertificateSkillEvidence
from scrape_jobs.models import Skill

from .matching import match_score, proficiency_value, student_skill_levels

from .expiry import (
    SOURCE_LISTING_LIFESPAN_DAYS,
    expire_stale_listings,
    expiry_report,
    stale_scraped_listings,
)
from .models import JobApplication, JobListing, JobSkill, SavedJob


class ListingExpiryTests(TestCase):
    """Scraped listings must stop being offered once the advert has lapsed."""

    def setUp(self):
        self.today = timezone.localdate()
        self.old = self.today - timedelta(days=SOURCE_LISTING_LIFESPAN_DAYS + 10)
        self.recent = self.today - timedelta(days=3)

    def _scraped(self, url, posted_date=None, status=JobListing.Status.ACTIVE):
        return JobListing.objects.create(
            job_title='Software Engineer',
            source_type=JobListing.SourceType.SCRAPED,
            source_url=url,
            posted_date=posted_date,
            status=status,
        )

    def test_lapsed_listing_is_closed(self):
        listing = self._scraped('https://example.test/old', posted_date=self.old)

        self.assertEqual(expire_stale_listings(), 1)
        listing.refresh_from_db()
        self.assertEqual(listing.status, JobListing.Status.CLOSED)

    def test_recent_listing_is_left_alone(self):
        listing = self._scraped('https://example.test/new', posted_date=self.recent)

        expire_stale_listings()
        listing.refresh_from_db()
        self.assertEqual(listing.status, JobListing.Status.ACTIVE)

    def test_boundary_listing_is_kept(self):
        """Exactly at the window edge is still advertised."""
        listing = self._scraped(
            'https://example.test/edge',
            posted_date=self.today - timedelta(days=SOURCE_LISTING_LIFESPAN_DAYS))

        expire_stale_listings()
        listing.refresh_from_db()
        self.assertEqual(listing.status, JobListing.Status.ACTIVE)

    def test_missing_posted_date_falls_back_to_first_seen(self):
        """42% of real listings have no posted_date; they still must expire."""
        listing = self._scraped('https://example.test/nodate', posted_date=None)
        # posted_time is auto_now_add, so age it directly.
        JobListing.objects.filter(pk=listing.pk).update(
            posted_time=timezone.now() - timedelta(days=SOURCE_LISTING_LIFESPAN_DAYS + 5))

        self.assertEqual(expire_stale_listings(), 1)
        listing.refresh_from_db()
        self.assertEqual(listing.status, JobListing.Status.CLOSED)

    def test_company_listings_are_never_touched(self):
        """Employers control their own listings; age must not close them."""
        listing = JobListing.objects.create(
            job_title='Graduate Developer',
            source_type=JobListing.SourceType.COMPANY,
            posted_date=self.old,
        )

        expire_stale_listings()
        listing.refresh_from_db()
        self.assertEqual(listing.status, JobListing.Status.ACTIVE)

    def test_expiry_is_idempotent(self):
        self._scraped('https://example.test/old', posted_date=self.old)

        self.assertEqual(expire_stale_listings(), 1)
        self.assertEqual(expire_stale_listings(), 0)

    def test_listings_are_closed_not_deleted(self):
        """Demand analytics are built from history and must keep the rows."""
        self._scraped('https://example.test/old', posted_date=self.old)

        expire_stale_listings()

        self.assertEqual(JobListing.objects.count(), 1)

    def test_report_counts_without_changing_anything(self):
        self._scraped('https://example.test/old', posted_date=self.old)
        self._scraped('https://example.test/new', posted_date=self.recent)

        report = expiry_report()

        self.assertEqual(report['total_scraped'], 2)
        self.assertEqual(report['stale_active'], 1)
        self.assertEqual(report['active'], 2, 'reporting must not mutate')
        self.assertEqual(stale_scraped_listings().count(), 1)


class ScrapedJobListingVisibilityTests(TestCase):
    """The student-facing list must not offer dead links."""

    def setUp(self):
        today = timezone.localdate()
        self.live = JobListing.objects.create(
            job_title='Live Role', source_type=JobListing.SourceType.SCRAPED,
            source_url='https://example.test/live',
            posted_date=today - timedelta(days=2))
        self.expired = JobListing.objects.create(
            job_title='Expired Role', source_type=JobListing.SourceType.SCRAPED,
            source_url='https://example.test/expired',
            posted_date=today - timedelta(days=90),
            status=JobListing.Status.CLOSED)

    def test_expired_listings_are_hidden_by_default(self):
        response = self.client.get('/api/scrape-jobs/scraped/')

        titles = [row['job_title'] for row in response.json()]
        self.assertIn('Live Role', titles)
        self.assertNotIn('Expired Role', titles)

    def test_expired_listings_can_be_requested_explicitly(self):
        response = self.client.get('/api/scrape-jobs/scraped/?include_expired=true')

        titles = [row['job_title'] for row in response.json()]
        self.assertIn('Expired Role', titles)


class StudentApplicationListTests(TestCase):
    """A student must be able to see their own applications — and only theirs."""

    @classmethod
    def setUpTestData(cls):
        cls.student_user = User.objects.create_user(
            email='applicant@university.test', password='Strong1!',
            role=User.Role.STUDENT)
        cls.student = Student.objects.create(
            user=cls.student_user, student_name='Applying Student')

        cls.other_user = User.objects.create_user(
            email='other-applicant@university.test', password='Strong1!',
            role=User.Role.STUDENT)
        cls.other_student = Student.objects.create(
            user=cls.other_user, student_name='Other Student')

        cls.company_user = User.objects.create_user(
            email='hiring@business.test', password='Strong1!',
            role=User.Role.COMPANY)
        cls.company = Company.objects.create(
            user=cls.company_user, company_name='Hiring Company')

        cls.job = JobListing.objects.create(
            job_title='Junior Data Analyst', company=cls.company,
            work_mode='Hybrid', status=JobListing.Status.ACTIVE)
        cls.application = JobApplication.objects.create(
            student=cls.student, job=cls.job,
            cv_url='https://example.test/cv.pdf',
            status=JobApplication.Status.SHORTLISTED,
            needs_work_permit=False, phone='0123456789')

        cls.other_job = JobListing.objects.create(
            job_title='Backend Engineer', company=cls.company,
            status=JobListing.Status.ACTIVE)
        JobApplication.objects.create(
            student=cls.other_student, job=cls.other_job,
            cv_url='https://example.test/other.pdf')

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.student_user)

    def test_student_sees_own_application_with_status(self):
        response = self.client.get('/api/job-listings/applications/')

        self.assertEqual(response.status_code, 200)
        rows = response.json()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['job_title'], 'Junior Data Analyst')
        self.assertEqual(rows[0]['company_name'], 'Hiring Company')
        self.assertEqual(rows[0]['status'], 'SHORTLISTED')
        self.assertEqual(rows[0]['status_display'], 'Shortlisted')
        self.assertEqual(rows[0]['work_mode'], 'Hybrid')

    def test_another_students_application_is_never_returned(self):
        rows = self.client.get('/api/job-listings/applications/').json()

        self.assertNotIn('Backend Engineer', [row['job_title'] for row in rows])

    def test_screening_fields_are_not_exposed_to_the_applicant(self):
        # match_score and student_skills belong to the employer's view.
        row = self.client.get('/api/job-listings/applications/').json()[0]

        self.assertNotIn('match_score', row)
        self.assertNotIn('student_skills', row)

    def test_company_cannot_read_the_student_endpoint(self):
        self.client.force_authenticate(self.company_user)

        response = self.client.get('/api/job-listings/applications/')

        self.assertEqual(response.status_code, 403)

    def test_student_with_no_applications_gets_an_empty_list(self):
        self.client.force_authenticate(self.other_user)
        JobApplication.objects.filter(student=self.other_student).delete()

        response = self.client.get('/api/job-listings/applications/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])


class MatchScoreFormulaTests(TestCase):
    """The documented formula, clause by clause.

    Job Matching % = (total matched skill score / total required skill score) x 100
    Beginner = 1, Intermediate = 2, Advanced = 3.
    """

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            email='match@university.test', password='Strong1!',
            role=User.Role.STUDENT)
        cls.student = Student.objects.create(user=cls.user, student_name='Matcher')
        cls.python = Skill.objects.create(skill_name='Python')
        cls.sql = Skill.objects.create(skill_name='SQL')

    def _job(self, requirements):
        job = JobListing.objects.create(job_title='Analyst')
        for skill, level in requirements:
            JobSkill.objects.create(job=job, skill=skill, required_level=level)
        return job

    def _hold(self, skill, level):
        StudentSkill.objects.update_or_create(
            student=self.student, skill=skill, defaults={'skill_level': level})

    def _score(self, job):
        return match_score(job, student_skill_levels(self.student))

    def test_proficiency_values_match_the_specification(self):
        self.assertEqual(proficiency_value('BEGINNER'), 1)
        self.assertEqual(proficiency_value('INTERMEDIATE'), 2)
        self.assertEqual(proficiency_value('ADVANCED'), 3)

    def test_level_above_requirement_scores_full_not_extra(self):
        # Advanced student, intermediate requirement: 2/2 = 100, not 3/2.
        job = self._job([(self.python, 'INTERMEDIATE')])
        self._hold(self.python, 'ADVANCED')

        self.assertEqual(self._score(job), 100)

    def test_level_equal_to_requirement_scores_full(self):
        job = self._job([(self.python, 'INTERMEDIATE')])
        self._hold(self.python, 'INTERMEDIATE')

        self.assertEqual(self._score(job), 100)

    def test_level_below_requirement_scores_the_students_own_level(self):
        # Beginner (1) against an Advanced (3) requirement: 1/3 = 33%.
        job = self._job([(self.python, 'ADVANCED')])
        self._hold(self.python, 'BEGINNER')

        self.assertEqual(self._score(job), 33)

    def test_missing_skill_scores_zero(self):
        job = self._job([(self.python, 'ADVANCED')])

        self.assertEqual(self._score(job), 0)

    def test_scores_are_weighted_by_required_level_not_skill_count(self):
        # Required total = 3 (Python ADVANCED) + 1 (SQL BEGINNER) = 4.
        # Student holds SQL at INTERMEDIATE -> min(2, 1) = 1. Python -> 0.
        job = self._job([(self.python, 'ADVANCED'), (self.sql, 'BEGINNER')])
        self._hold(self.sql, 'INTERMEDIATE')

        self.assertEqual(self._score(job), 25)

    def test_full_match_across_several_skills(self):
        job = self._job([(self.python, 'INTERMEDIATE'), (self.sql, 'BEGINNER')])
        self._hold(self.python, 'ADVANCED')
        self._hold(self.sql, 'BEGINNER')

        self.assertEqual(self._score(job), 100)

    def test_advert_with_no_skills_has_no_score(self):
        # None, not 0: "we cannot tell" must not read as "you match nothing".
        self.assertIsNone(self._score(self._job([])))

    def test_student_with_no_skills_scores_zero_not_null(self):
        job = self._job([(self.python, 'INTERMEDIATE')])

        self.assertEqual(match_score(job, {}), 0)

    def test_scraped_listings_default_to_intermediate(self):
        job = JobListing.objects.create(
            job_title='Scraped Role',
            source_type=JobListing.SourceType.SCRAPED,
            source_url='https://example.test/level-default')
        relation = JobSkill.objects.create(job=job, skill=self.python)

        self.assertEqual(relation.required_level, 'INTERMEDIATE')


class MatchScoreIsTheSameOnBothSidesTests(TestCase):
    """A student and the employer must see one number, not two."""

    @classmethod
    def setUpTestData(cls):
        cls.student_user = User.objects.create_user(
            email='both-sides@university.test', password='Strong1!',
            role=User.Role.STUDENT)
        cls.student = Student.objects.create(
            user=cls.student_user, student_name='Both Sides')
        cls.company_user = User.objects.create_user(
            email='both-sides@business.test', password='Strong1!',
            role=User.Role.COMPANY)
        cls.company = Company.objects.create(
            user=cls.company_user, company_name='Both Sides Ltd')

        python = Skill.objects.create(skill_name='Python')
        sql = Skill.objects.create(skill_name='SQL')
        cls.job = JobListing.objects.create(
            job_title='Data Analyst', company=cls.company,
            status=JobListing.Status.ACTIVE)
        JobSkill.objects.create(job=cls.job, skill=python, required_level='ADVANCED')
        JobSkill.objects.create(job=cls.job, skill=sql, required_level='BEGINNER')
        StudentSkill.objects.create(
            student=cls.student, skill=python, skill_level='INTERMEDIATE')
        cls.application = JobApplication.objects.create(
            student=cls.student, job=cls.job, cv_url='https://example.test/cv.pdf')

    def test_both_endpoints_report_the_same_score(self):
        client = APIClient()

        client.force_authenticate(self.student_user)
        student_view = client.get('/api/job-listings/public/').json()
        student_score = next(
            row['match_score'] for row in student_view if row['id'] == self.job.id)

        client.force_authenticate(self.company_user)
        company_view = client.get('/api/job-listings/company/applications/').json()
        company_score = company_view[0]['match_score']

        # Required total = 3 + 1 = 4. Matched = min(2,3) + 0 = 2. 2/4 = 50%.
        self.assertEqual(student_score, 50)
        self.assertEqual(company_score, 50)

    def test_anonymous_visitor_gets_no_score_rather_than_zero(self):
        row = next(
            row for row in APIClient().get('/api/job-listings/public/').json()
            if row['id'] == self.job.id)

        self.assertIsNone(row['match_score'])

    def test_scraped_feed_scores_against_the_logged_in_student(self):
        scraped = JobListing.objects.create(
            job_title='Scraped Analyst',
            source_type=JobListing.SourceType.SCRAPED,
            source_url='https://example.test/scored')
        JobSkill.objects.create(
            job=scraped, skill=Skill.objects.get(skill_name='Python'),
            required_level='INTERMEDIATE')

        client = APIClient()
        client.force_authenticate(self.student_user)
        row = next(
            row for row in client.get('/api/scrape-jobs/scraped/').json()
            if row['id'] == scraped.id)

        self.assertEqual(row['match_score'], 100)

    def test_scraped_feed_states_the_level_each_skill_is_wanted_at(self):
        """The student page renders a per-skill verdict beside the score.

        Without the required level it could only compare skill names, so a
        student holding every skill at Beginner saw a green tick on each one
        next to a 33% match. The two must be computed from the same numbers.
        """
        scraped = JobListing.objects.create(
            job_title='Scraped Senior Analyst',
            source_type=JobListing.SourceType.SCRAPED,
            source_url='https://example.test/levels')
        JobSkill.objects.create(
            job=scraped, skill=Skill.objects.get(skill_name='Python'),
            required_level='ADVANCED')

        client = APIClient()
        client.force_authenticate(self.student_user)
        row = next(
            row for row in client.get('/api/scrape-jobs/scraped/').json()
            if row['id'] == scraped.id)

        self.assertEqual(
            row['required_skill_levels'],
            [{'skill': 'Python', 'required_level': 'ADVANCED'}],
        )
        # The student holds Python at INTERMEDIATE: min(2, 3) / 3 = 67%.
        # A name-only tick would have called this skill fully met.
        self.assertEqual(row['match_score'], 67)


class RequiredSkillLevelWriteTests(TestCase):
    """Companies can state the level they need; the old shape still works."""

    @classmethod
    def setUpTestData(cls):
        cls.company_user = User.objects.create_user(
            email='levels@business.test', password='Strong1!',
            role=User.Role.COMPANY)
        cls.company = Company.objects.create(
            user=cls.company_user, company_name='Levels Ltd')

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.company_user)

    def _post(self, required_skills):
        return self.client.post('/api/job-listings/jobs/', {
            'job_title': 'Backend Engineer',
            'required_skills': required_skills,
        }, format='json')

    def test_plain_string_still_accepted_and_defaults_to_intermediate(self):
        response = self._post(['Python'])

        self.assertEqual(response.status_code, 201)
        relation = JobSkill.objects.get(job_id=response.json()['id'])
        self.assertEqual(relation.required_level, 'INTERMEDIATE')

    def test_level_can_be_stated_per_skill(self):
        response = self._post([{'name': 'Python', 'level': 'ADVANCED'}])

        self.assertEqual(response.status_code, 201)
        relation = JobSkill.objects.get(job_id=response.json()['id'])
        self.assertEqual(relation.required_level, 'ADVANCED')

    def test_unknown_level_is_rejected(self):
        response = self._post([{'name': 'Python', 'level': 'GURU'}])

        self.assertEqual(response.status_code, 400)

    def test_editing_with_names_only_preserves_existing_levels(self):
        created = self._post([{'name': 'Python', 'level': 'ADVANCED'}]).json()

        # An older client (and the edit form until now) sends names only.
        response = self.client.patch(
            f"/api/job-listings/jobs/{created['id']}/",
            {'required_skills': ['Python']}, format='json')

        self.assertEqual(response.status_code, 200)
        relation = JobSkill.objects.get(job_id=created['id'])
        self.assertEqual(relation.required_level, 'ADVANCED',
                         'a stated level must survive an edit that omits it')

    def test_an_explicit_level_still_overrides_the_previous_one(self):
        created = self._post([{'name': 'Python', 'level': 'ADVANCED'}]).json()

        self.client.patch(
            f"/api/job-listings/jobs/{created['id']}/",
            {'required_skills': [{'name': 'Python', 'level': 'BEGINNER'}]},
            format='json')

        relation = JobSkill.objects.get(job_id=created['id'])
        self.assertEqual(relation.required_level, 'BEGINNER')


class CompanyVisibilityTests(TestCase):
    """What an employer learns about an applicant, and what stays private.

    An employer gets the verification *result* -- "this skill was checked by an
    administrator" -- and never the evidence behind it. The certificate, the
    document, and any identification number printed on it are not reachable
    from anything a company account can call.
    """

    @classmethod
    def setUpTestData(cls):
        cls.student_user = User.objects.create_user(
            email='visible-student@test.com', password='pw', role='STUDENT')
        cls.student = Student.objects.create(
            user=cls.student_user, student_name='Applicant',
            matric_number='S900001')

        cls.company_user = User.objects.create_user(
            email='visible-company@test.com', password='pw', role='COMPANY')
        cls.company = Company.objects.create(
            user=cls.company_user, company_name='Hiring Co')

        cls.admin_user = User.objects.create_user(
            email='visible-admin@test.com', password='pw', role='ADMIN', is_staff=True)
        AdminProfile.objects.create(user=cls.admin_user, admin_name='Admin')

        cls.verified_skill = Skill.objects.create(skill_name='Python')
        cls.claimed_skill = Skill.objects.create(skill_name='Figma')

        StudentSkill.objects.create(
            student=cls.student, skill=cls.verified_skill, skill_level='ADVANCED')
        StudentSkill.objects.create(
            student=cls.student, skill=cls.claimed_skill, skill_level='BEGINNER')

        # Only the first skill has an approved certificate behind it. The file
        # path stands in for a document holding the student's IC.
        approved = Certificate.objects.create(
            student=cls.student,
            file_path='certificates/cert_deadbeef.pdf',
            original_name='040910101234_cert.pdf',
            verified_status=Certificate.VerifiedStatus.APPROVED)
        CertificateSkillEvidence.objects.create(
            certificate=approved, skill=cls.verified_skill,
            claimed_level='INTERMEDIATE', approved_level='INTERMEDIATE',
            review_status=CertificateSkillEvidence.ReviewStatus.APPROVED)
        pending = Certificate.objects.create(
            student=cls.student,
            cert_url='https://example.test/pending',
            verified_status=Certificate.VerifiedStatus.PENDING)
        CertificateSkillEvidence.objects.create(
            certificate=pending, skill=cls.claimed_skill,
            claimed_level='INTERMEDIATE')

        cls.job = JobListing.objects.create(
            company=cls.company, job_title='Backend Engineer',
            description='Build services', status='OPEN')
        JobApplication.objects.create(
            student=cls.student, job=cls.job,
            cv_url='https://example.test/cv.pdf')

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.company_user)

    def _application_row(self):
        response = self.client.get('/api/job-listings/company/applications/')
        self.assertEqual(response.status_code, 200, response.content)
        rows = response.json()
        self.assertEqual(len(rows), 1)
        return rows[0]

    def test_an_endorsed_skill_is_reported_as_verified(self):
        skills = {s['skill_name']: s for s in self._application_row()['student_skills']}

        self.assertTrue(skills['Python']['verified'])
        self.assertEqual(skills['Python']['skill_level'], 'ADVANCED')

    def test_a_skill_without_an_approved_certificate_is_not_verified(self):
        skills = {s['skill_name']: s for s in self._application_row()['student_skills']}

        self.assertFalse(skills['Figma']['verified'])

    def test_the_application_payload_carries_no_document_or_identity_data(self):
        payload = str(self._application_row())

        # The stored document, the name the student gave it, and the digits in
        # that name must all be absent.
        self.assertNotIn('certificates/', payload)
        self.assertNotIn('040910101234', payload)
        self.assertNotIn('cert_deadbeef', payload)
        self.assertNotIn('S900001', payload)

    def test_the_payload_exposes_no_certificate_fields_at_all(self):
        row = self._application_row()

        for leaked in ('certificate', 'certificates', 'file_path', 'original_name',
                       'matric_number', 'verification_notes'):
            self.assertNotIn(leaked, row)


class CVParseAndDeleteTests(TestCase):
    """A CV is read once and never stored."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            email='cv@university.test', password='Strong1!', role=User.Role.STUDENT)
        cls.student = Student.objects.create(user=cls.user, student_name='CV Student')
        cls.python = Skill.objects.create(skill_name='Python')

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def _post(self, text='Skills\nPython\n', **extra):
        pdf = SimpleUploadedFile('cv.pdf', b'%PDF-1.4\n' + b'0' * 512,
                                 content_type='application/pdf')
        payload = {'file': pdf, 'cv_processing_ack': True}
        payload.update(extra)
        with patch('job_listings.cv_parser.extract_text_from_pdf', return_value=text):
            return self.client.post('/api/job-listings/cv/parse/',
                                    payload, format='multipart')

    @staticmethod
    def _temp_cvs():
        return {n for n in os.listdir(tempfile.gettempdir()) if n.startswith('cv-')}

    def test_parsing_returns_skills_without_storing_the_file(self):
        before = self._temp_cvs()

        response = self._post('Technical Skills\nPython\nExperience\nIntern at Acme\n')

        self.assertEqual(response.status_code, 200)
        self.assertIn('Python', [s['skill_name'] for s in response.data['skills']])
        self.assertEqual(self._temp_cvs() - before, set(),
                         'the temporary CV must be deleted')

    def test_the_temporary_file_is_deleted_even_when_parsing_raises(self):
        before = self._temp_cvs()
        pdf = SimpleUploadedFile('cv.pdf', b'%PDF-1.4\n' + b'0' * 512,
                                 content_type='application/pdf')

        with patch('job_listings.cv_parser.extract_text_from_pdf',
                   side_effect=RuntimeError('boom')):
            response = self.client.post(
                '/api/job-listings/cv/parse/',
                {'file': pdf, 'cv_processing_ack': True}, format='multipart')

        self.assertEqual(response.status_code, 400)
        self.assertEqual(self._temp_cvs() - before, set())

    def test_a_renamed_non_pdf_is_refused_on_its_bytes(self):
        fake = SimpleUploadedFile('cv.pdf', b'MZ\x90\x00 not a pdf at all',
                                  content_type='application/pdf')

        response = self.client.post(
            '/api/job-listings/cv/parse/',
            {'file': fake, 'cv_processing_ack': True}, format='multipart')

        self.assertEqual(response.status_code, 400)

    def test_an_oversized_cv_is_refused(self):
        big = SimpleUploadedFile(
            'cv.pdf', b'%PDF-1.4\n' + b'0' * (11 * 1024 * 1024),
            content_type='application/pdf')

        response = self.client.post(
            '/api/job-listings/cv/parse/',
            {'file': big, 'cv_processing_ack': True}, format='multipart')

        self.assertEqual(response.status_code, 400)

    def test_a_scanned_cv_is_explained(self):
        response = self._post('')

        self.assertEqual(response.status_code, 400)
        self.assertIn('scan', response.data['detail'].lower())

    def test_a_company_cannot_parse_a_cv(self):
        company_user = User.objects.create_user(
            email='cv@business.test', password='Strong1!', role=User.Role.COMPANY)
        Company.objects.create(user=company_user, company_name='Snooper')
        self.client.force_authenticate(company_user)

        response = self._post()

        self.assertEqual(response.status_code, 403)


class ApplicationSnapshotTests(TestCase):
    """An application records what was submitted, not the profile as it is now."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            email='snap@university.test', password='Strong1!', role=User.Role.STUDENT)
        cls.student = Student.objects.create(user=cls.user, student_name='Snap')
        cls.company_user = User.objects.create_user(
            email='snap@business.test', password='Strong1!', role=User.Role.COMPANY)
        cls.company = Company.objects.create(
            user=cls.company_user, company_name='Snap Ltd')

        cls.python = Skill.objects.create(skill_name='Python')
        cls.sql = Skill.objects.create(skill_name='SQL')
        cls.job = JobListing.objects.create(
            job_title='Backend Engineer', company=cls.company,
            status=JobListing.Status.ACTIVE)
        JobSkill.objects.create(job=cls.job, skill=cls.python,
                                required_level='INTERMEDIATE')
        StudentSkill.objects.create(
            student=cls.student, skill=cls.python, skill_level='INTERMEDIATE')

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def _receipt(self, user=None):
        """A receipt for a consented parse, as the parse endpoint would issue."""
        user = user or self.user
        consent = UserConsent.objects.create(
            user=user,
            consent_type=UserConsent.ConsentType.CV_PROCESSING_CONSENT,
            notice_version='1.0', accepted=True,
            accepted_at=timezone.now(),
            source=UserConsent.Source.CV_PARSE)
        return cv_receipt.issue(user.id, consent.id)

    def _apply(self, skills=None, **overrides):
        payload = {
            'job': self.job.id,
            'needs_work_permit': False,
            'cv_parse_receipt': self._receipt(),
            'applicant_snapshot': {
                'skills': skills if skills is not None else [{'skill_id': self.python.id}],
                'education': ['BSc Computer Science, Universiti Malaya'],
                'experience': ['Intern, Acme'],
            },
        }
        payload.update(overrides)
        return self.client.post('/api/job-listings/applications/', payload, format='json')

    def test_applying_stores_the_confirmed_snapshot(self):
        response = self._apply()

        self.assertEqual(response.status_code, 201)
        snapshot = JobApplication.objects.get(student=self.student).applicant_snapshot
        self.assertEqual([s['skill_name'] for s in snapshot['skills']], ['Python'])
        self.assertEqual(snapshot['skills'][0]['skill_level'], 'INTERMEDIATE')
        self.assertIn('BSc Computer Science, Universiti Malaya', snapshot['education'])
        self.assertIn('captured_at', snapshot)

    def test_the_snapshot_does_not_change_when_the_profile_does(self):
        self._apply()
        application = JobApplication.objects.get(student=self.student)
        before = application.applicant_snapshot

        StudentSkill.objects.create(
            student=self.student, skill=self.sql, skill_level='ADVANCED')
        StudentSkill.objects.filter(
            student=self.student, skill=self.python).update(skill_level='ADVANCED')

        application.refresh_from_db()
        self.assertEqual(application.applicant_snapshot, before)

    def test_the_match_score_is_frozen_with_the_snapshot(self):
        self._apply()
        client = APIClient()
        client.force_authenticate(self.company_user)
        before = client.get(
            '/api/job-listings/company/applications/').json()[0]['match_score']

        StudentSkill.objects.filter(
            student=self.student, skill=self.python).update(skill_level='ADVANCED')

        after = client.get(
            '/api/job-listings/company/applications/').json()[0]['match_score']
        self.assertEqual(before, after,
                         'editing a profile must not re-score a sent application')

    def test_a_claimed_level_from_the_client_is_ignored(self):
        """The CV says which skills; the profile says how good at them. A
        client asserting ADVANCED must not be able to score itself up."""
        self._apply(skills=[{'skill_id': self.python.id, 'skill_level': 'ADVANCED'}])

        snapshot = JobApplication.objects.get(student=self.student).applicant_snapshot
        self.assertEqual(snapshot['skills'][0]['skill_level'], 'INTERMEDIATE')

    def test_an_unknown_skill_id_is_discarded(self):
        self._apply(skills=[{'skill_id': 999999}])

        application = JobApplication.objects.filter(student=self.student).first()
        if application is not None:
            self.assertEqual(application.applicant_snapshot['skills'], [])

    def test_applying_with_nothing_confirmed_is_refused(self):
        response = self.client.post('/api/job-listings/applications/', {
            'job': self.job.id, 'needs_work_permit': False,
        }, format='json')

        self.assertEqual(response.status_code, 400)
        self.assertFalse(JobApplication.objects.filter(student=self.student).exists())


class CVProcessingConsentTests(TestCase):
    """A CV is read only after the student agrees to it being read."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            email='cvconsent@university.test', password='Strong1!',
            role=User.Role.STUDENT)
        cls.student = Student.objects.create(user=cls.user, student_name='Consenter')
        Skill.objects.create(skill_name='Python')

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def _pdf(self):
        return SimpleUploadedFile('cv.pdf', b'%PDF-1.4\n' + b'0' * 512,
                                  content_type='application/pdf')

    def _post(self, **payload):
        body = {'file': self._pdf()}
        body.update(payload)
        with patch('job_listings.cv_parser.extract_text_from_pdf',
                   return_value='Skills\nPython\n'):
            return self.client.post('/api/job-listings/cv/parse/', body,
                                    format='multipart')

    def test_parsing_without_the_acknowledgement_is_refused(self):
        response = self._post()

        self.assertEqual(response.status_code, 400)
        self.assertIn('cv_processing_ack', response.data)
        self.assertFalse(UserConsent.objects.filter(
            consent_type='CV_PROCESSING_CONSENT').exists())

    def test_a_false_acknowledgement_is_refused(self):
        response = self._post(cv_processing_ack=False)

        self.assertEqual(response.status_code, 400)

    def test_the_string_false_cannot_pass_the_gate(self):
        """A form-encoded unchecked box sends "false"; bool("false") is True."""
        response = self._post(cv_processing_ack='false')

        self.assertEqual(response.status_code, 400)

    def test_parsing_records_a_cv_processing_consent(self):
        response = self._post(cv_processing_ack=True)

        self.assertEqual(response.status_code, 200)
        consent = UserConsent.objects.get(consent_type='CV_PROCESSING_CONSENT')
        self.assertEqual(consent.source, 'CV_PARSE')
        self.assertTrue(consent.accepted)
        self.assertIsNotNone(consent.accepted_at)
        self.assertTrue(consent.notice_version)

    def test_a_successful_parse_returns_a_receipt(self):
        response = self._post(cv_processing_ack=True)

        self.assertIn('cv_parse_receipt', response.data)
        payload = cv_receipt.verify(response.data['cv_parse_receipt'], self.user.id)
        self.assertEqual(payload['user_id'], self.user.id)

    def test_the_consent_is_recorded_even_when_reading_the_file_fails(self):
        """The CV was processed either way; that is what the record accounts for."""
        with patch('job_listings.cv_parser.extract_text_from_pdf',
                   side_effect=RuntimeError('boom')):
            response = self.client.post(
                '/api/job-listings/cv/parse/',
                {'file': self._pdf(), 'cv_processing_ack': True},
                format='multipart')

        self.assertEqual(response.status_code, 400)
        self.assertTrue(UserConsent.objects.filter(
            consent_type='CV_PROCESSING_CONSENT').exists())


class CVParseReceiptTests(TestCase):
    """The receipt proves consented processing, to one student, for a while."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            email='receipt@university.test', password='Strong1!',
            role=User.Role.STUDENT)
        cls.other = User.objects.create_user(
            email='receipt-other@university.test', password='Strong1!',
            role=User.Role.STUDENT)

    def test_a_valid_receipt_round_trips(self):
        token = cv_receipt.issue(self.user.id, 42)

        payload = cv_receipt.verify(token, self.user.id)

        self.assertEqual(payload['consent_id'], 42)

    def test_another_students_receipt_is_refused(self):
        token = cv_receipt.issue(self.user.id, 42)

        with self.assertRaises(cv_receipt.InvalidReceipt):
            cv_receipt.verify(token, self.other.id)

    def test_a_tampered_receipt_is_refused(self):
        token = cv_receipt.issue(self.user.id, 42)

        with self.assertRaises(cv_receipt.InvalidReceipt):
            cv_receipt.verify(token[:-4] + 'AAAA', self.user.id)

    def test_a_missing_receipt_is_refused(self):
        with self.assertRaises(cv_receipt.InvalidReceipt):
            cv_receipt.verify('', self.user.id)

    def test_an_expired_receipt_is_refused(self):
        token = cv_receipt.issue(self.user.id, 42)

        with patch('django.core.signing.loads',
                   side_effect=signing.SignatureExpired('too old')):
            with self.assertRaises(cv_receipt.InvalidReceipt):
                cv_receipt.verify(token, self.user.id)


class ApplicationDisclosureTests(TestCase):
    """Submitting records the disclosure, without a second checkbox."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            email='disclose@university.test', password='Strong1!',
            role=User.Role.STUDENT)
        cls.student = Student.objects.create(user=cls.user, student_name='Discloser')
        cls.company_user = User.objects.create_user(
            email='disclose@business.test', password='Strong1!',
            role=User.Role.COMPANY)
        cls.company = Company.objects.create(
            user=cls.company_user, company_name='Receiving Ltd')
        cls.python = Skill.objects.create(skill_name='Python')
        cls.job = JobListing.objects.create(
            job_title='Backend Engineer', company=cls.company,
            status=JobListing.Status.ACTIVE)
        StudentSkill.objects.create(
            student=cls.student, skill=cls.python, skill_level='INTERMEDIATE')

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def _receipt(self):
        consent = UserConsent.objects.create(
            user=self.user,
            consent_type=UserConsent.ConsentType.CV_PROCESSING_CONSENT,
            notice_version='1.0', accepted=True, accepted_at=timezone.now(),
            source=UserConsent.Source.CV_PARSE)
        return cv_receipt.issue(self.user.id, consent.id)

    def _payload(self, **overrides):
        payload = {
            'job': self.job.id,
            'needs_work_permit': False,
            'cv_parse_receipt': self._receipt(),
            'applicant_snapshot': {
                'skills': [self.python.id],
                'education': ['BSc Computer Science'],
                'experience': [],
            },
        }
        payload.update(overrides)
        return payload

    def _apply(self, **overrides):
        return self.client.post('/api/job-listings/applications/',
                                self._payload(**overrides), format='json')

    def test_submitting_records_the_disclosure_acknowledgement(self):
        response = self._apply()

        self.assertEqual(response.status_code, 201, response.data)
        consent = UserConsent.objects.get(
            consent_type='APPLICATION_DISCLOSURE_ACKNOWLEDGEMENT')
        self.assertEqual(consent.source, 'JOB_APPLICATION')
        self.assertTrue(consent.accepted)
        self.assertIsNotNone(consent.accepted_at)
        self.assertTrue(consent.notice_version)

    def test_no_disclosure_checkbox_is_required(self):
        """The payload carries no acknowledgement flag and still succeeds."""
        payload = self._payload()
        self.assertNotIn('application_disclosure_ack', payload)

        self.assertEqual(self._apply().status_code, 201)

    def test_the_application_links_both_consents(self):
        self._apply()

        application = JobApplication.objects.get(student=self.student)
        self.assertIsNotNone(application.disclosure_consent)
        self.assertIsNotNone(application.cv_processing_consent)
        self.assertEqual(application.cv_processing_consent.consent_type,
                         'CV_PROCESSING_CONSENT')

    def test_the_receiving_company_is_identifiable_from_the_record(self):
        """The sentence names no company; the audit trail must still reach one."""
        self._apply()

        consent = UserConsent.objects.get(
            consent_type='APPLICATION_DISCLOSURE_ACKNOWLEDGEMENT')
        application = consent.disclosure_applications.get()
        self.assertEqual(application.job.company, self.company)

    def test_the_application_and_the_disclosure_roll_back_together(self):
        with patch('job_listings.views.JobApplication.objects.create',
                   side_effect=RuntimeError('boom')):
            with self.assertRaises(RuntimeError):
                self._apply()

        self.assertFalse(JobApplication.objects.exists())
        self.assertFalse(UserConsent.objects.filter(
            consent_type='APPLICATION_DISCLOSURE_ACKNOWLEDGEMENT').exists())

    def test_a_receipt_from_another_student_is_refused(self):
        stranger = User.objects.create_user(
            email='stranger@university.test', password='Strong1!',
            role=User.Role.STUDENT)
        foreign = cv_receipt.issue(stranger.id, 1)

        response = self._apply(cv_parse_receipt=foreign)

        self.assertEqual(response.status_code, 400)
        self.assertIn('cv_parse_receipt', response.data)
        self.assertFalse(JobApplication.objects.exists())

    def test_a_missing_receipt_is_refused(self):
        payload = self._payload()
        del payload['cv_parse_receipt']

        response = self.client.post('/api/job-listings/applications/',
                                    payload, format='json')

        self.assertEqual(response.status_code, 400)


class ApplicationPayloadValidationTests(TestCase):
    """Malformed input is a 400 naming the field, never a 500."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            email='payload@university.test', password='Strong1!',
            role=User.Role.STUDENT)
        cls.student = Student.objects.create(user=cls.user, student_name='Payload')
        cls.company_user = User.objects.create_user(
            email='payload@business.test', password='Strong1!',
            role=User.Role.COMPANY)
        cls.company = Company.objects.create(
            user=cls.company_user, company_name='Payload Ltd')
        cls.python = Skill.objects.create(skill_name='Python')
        cls.job = JobListing.objects.create(
            job_title='Backend Engineer', company=cls.company,
            status=JobListing.Status.ACTIVE)
        StudentSkill.objects.create(
            student=cls.student, skill=cls.python, skill_level='ADVANCED')

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def _receipt(self):
        consent = UserConsent.objects.create(
            user=self.user,
            consent_type=UserConsent.ConsentType.CV_PROCESSING_CONSENT,
            notice_version='1.0', accepted=True, accepted_at=timezone.now(),
            source=UserConsent.Source.CV_PARSE)
        return cv_receipt.issue(self.user.id, consent.id)

    def _apply(self, **overrides):
        payload = {
            'job': self.job.id,
            'needs_work_permit': False,
            'cv_parse_receipt': self._receipt(),
            'applicant_snapshot': {'skills': [self.python.id],
                                   'education': ['BSc'], 'experience': []},
        }
        payload.update(overrides)
        return self.client.post('/api/job-listings/applications/',
                                payload, format='json')

    def test_a_non_object_snapshot_is_a_field_error(self):
        for bad in (['not', 'an', 'object'], 'a string', 42):
            response = self._apply(applicant_snapshot=bad)
            self.assertEqual(response.status_code, 400, bad)
            self.assertIn('applicant_snapshot', response.data)

    def test_a_null_snapshot_is_a_field_error(self):
        response = self._apply(applicant_snapshot=None)

        self.assertEqual(response.status_code, 400)

    def test_a_non_integer_skill_id_is_refused(self):
        response = self._apply(applicant_snapshot={
            'skills': ['; DROP TABLE'], 'education': [], 'experience': []})

        self.assertEqual(response.status_code, 400)

    def test_an_unknown_skill_id_is_refused_not_dropped(self):
        """Dropping it would show the employer fewer skills than the student sent."""
        response = self._apply(applicant_snapshot={
            'skills': [self.python.id, 999999], 'education': [], 'experience': []})

        self.assertEqual(response.status_code, 400)
        self.assertFalse(JobApplication.objects.exists())

    def test_too_many_entries_are_refused(self):
        response = self._apply(applicant_snapshot={
            'skills': [], 'education': [f'Entry {i}' for i in range(41)],
            'experience': []})

        self.assertEqual(response.status_code, 400)

    def test_an_overlong_entry_is_refused(self):
        response = self._apply(applicant_snapshot={
            'skills': [], 'education': ['x' * 201], 'experience': []})

        self.assertEqual(response.status_code, 400)

    def test_the_string_false_does_not_become_true_for_work_permit(self):
        """bool("false") is True. A student who said no must not be recorded
        as needing a permit."""
        response = self._apply(needs_work_permit='false')

        self.assertEqual(response.status_code, 201, response.data)
        application = JobApplication.objects.get()
        self.assertFalse(application.needs_work_permit)

    def test_an_absent_work_permit_answer_is_refused(self):
        payload = {
            'job': self.job.id,
            'cv_parse_receipt': self._receipt(),
            'applicant_snapshot': {'skills': [self.python.id],
                                   'education': [], 'experience': []},
        }

        response = self.client.post('/api/job-listings/applications/',
                                    payload, format='json')

        self.assertEqual(response.status_code, 400)
        self.assertIn('needs_work_permit', response.data)

    def test_a_malformed_date_is_refused(self):
        response = self._apply(available_from='the 3rd of never')

        self.assertEqual(response.status_code, 400)
        self.assertIn('available_from', response.data)

    def test_an_overlong_cover_note_is_refused(self):
        response = self._apply(cover_note='x' * 5001)

        self.assertEqual(response.status_code, 400)

    def test_an_overlong_phone_is_refused(self):
        response = self._apply(phone='0' * 31)

        self.assertEqual(response.status_code, 400)

    def test_a_scraped_listing_cannot_be_applied_to(self):
        scraped = JobListing.objects.create(
            job_title='Scraped Role',
            source_type=JobListing.SourceType.SCRAPED,
            source_url='https://example.test/x',
            status=JobListing.Status.ACTIVE)

        response = self._apply(job=scraped.id)

        self.assertEqual(response.status_code, 400)
        self.assertIn('job', response.data)

    def test_a_closed_advert_is_refused(self):
        self.job.closing_date = timezone.localdate() - timedelta(days=1)
        self.job.save()

        response = self._apply()

        self.assertEqual(response.status_code, 400)


class SubmittedSnapshotIsFrozenTests(TestCase):
    """The employer sees the application as submitted, and nothing else."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            email='frozen@university.test', password='Strong1!',
            role=User.Role.STUDENT)
        cls.student = Student.objects.create(user=cls.user, student_name='Frozen')
        cls.company_user = User.objects.create_user(
            email='frozen@business.test', password='Strong1!',
            role=User.Role.COMPANY)
        cls.company = Company.objects.create(
            user=cls.company_user, company_name='Frozen Ltd')
        cls.python = Skill.objects.create(skill_name='Python')
        cls.sql = Skill.objects.create(skill_name='SQL')
        cls.job = JobListing.objects.create(
            job_title='Backend Engineer', company=cls.company,
            status=JobListing.Status.ACTIVE)
        StudentSkill.objects.create(
            student=cls.student, skill=cls.python, skill_level='INTERMEDIATE')

    def _apply(self, skills):
        client = APIClient()
        client.force_authenticate(self.user)
        consent = UserConsent.objects.create(
            user=self.user,
            consent_type=UserConsent.ConsentType.CV_PROCESSING_CONSENT,
            notice_version='1.0', accepted=True, accepted_at=timezone.now(),
            source=UserConsent.Source.CV_PARSE)
        return client.post('/api/job-listings/applications/', {
            'job': self.job.id,
            'needs_work_permit': False,
            'cv_parse_receipt': cv_receipt.issue(self.user.id, consent.id),
            'applicant_snapshot': {
                'skills': skills,
                'education': ['BSc Computer Science'],
                'experience': [],
            },
        }, format='json')

    def _employer_view(self):
        client = APIClient()
        client.force_authenticate(self.company_user)
        rows = client.get('/api/job-listings/company/applications/').json()
        self.assertEqual(len(rows), 1)
        return rows[0]

    def _approve(self, skill):
        """An approved certificate evidencing one skill."""
        certificate = Certificate.objects.create(
            student=self.student,
            verified_status=Certificate.VerifiedStatus.APPROVED)
        CertificateSkillEvidence.objects.create(
            certificate=certificate, skill=skill,
            claimed_level='INTERMEDIATE', approved_level='INTERMEDIATE',
            review_status=CertificateSkillEvidence.ReviewStatus.APPROVED)
        return certificate

    def test_verified_status_is_captured_at_submission(self):
        self._approve(self.python)

        self._apply([self.python.id])

        snapshot = JobApplication.objects.get().applicant_snapshot
        self.assertTrue(snapshot['skills'][0]['verified'])
        self.assertEqual(snapshot['skills'][0]['skill_level'], 'INTERMEDIATE')
        self.assertEqual(snapshot['skills'][0]['skill_id'], self.python.id)

    def test_a_certificate_approved_later_does_not_alter_a_sent_application(self):
        self._apply([self.python.id])

        self._approve(self.python)

        skills = self._employer_view()['student_skills']
        self.assertEqual(len(skills), 1)
        self.assertFalse(skills[0]['verified'],
                         'a later approval must not rewrite a sent application')

    def test_a_skill_added_later_is_not_shown_to_the_employer(self):
        self._apply([self.python.id])

        StudentSkill.objects.create(
            student=self.student, skill=self.sql, skill_level='ADVANCED')

        skills = self._employer_view()['student_skills']
        self.assertEqual([s['skill_name'] for s in skills], ['Python'])

    def test_an_empty_submitted_skill_list_stays_empty(self):
        """No fallback to the live profile: the student chose to send none."""
        response = self._apply([])
        self.assertEqual(response.status_code, 201, response.data)

        skills = self._employer_view()['student_skills']
        self.assertEqual(skills, [])

    def test_an_empty_snapshot_scores_no_match_from_the_live_profile(self):
        """The match score must come from the snapshot too, not just the list.

        Scoring an empty submission against the live profile would report a
        match built from information the student chose not to send.
        """
        JobSkill.objects.create(job=self.job, skill=self.python,
                                required_level='INTERMEDIATE')

        self._apply([])

        row = self._employer_view()
        self.assertEqual(row['match_score'], 0)

    def test_a_receipt_naming_a_missing_consent_is_refused(self):
        """A signature proves we issued it, not that the row still exists."""
        forged_but_signed = cv_receipt.issue(self.user.id, 999999)

        client = APIClient()
        client.force_authenticate(self.user)
        response = client.post('/api/job-listings/applications/', {
            'job': self.job.id,
            'needs_work_permit': False,
            'cv_parse_receipt': forged_but_signed,
            'applicant_snapshot': {'skills': [self.python.id],
                                   'education': [], 'experience': []},
        }, format='json')

        self.assertEqual(response.status_code, 400)
        self.assertIn('cv_parse_receipt', response.data)
        self.assertFalse(JobApplication.objects.exists())

    def test_a_legacy_application_still_reports_the_live_profile(self):
        """Rows predating snapshots have no other answer available."""
        JobApplication.objects.create(
            student=self.student, job=self.job, applicant_snapshot={})

        skills = self._employer_view()['student_skills']
        self.assertEqual([s['skill_name'] for s in skills], ['Python'])


class LongCvConfirmationTests(TestCase):
    """More than five entries: the screen used to show 5 and submit all."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            email='longcv@university.test', password='Strong1!',
            role=User.Role.STUDENT)
        cls.student = Student.objects.create(user=cls.user, student_name='Long CV')
        cls.company_user = User.objects.create_user(
            email='longcv@business.test', password='Strong1!',
            role=User.Role.COMPANY)
        cls.company = Company.objects.create(
            user=cls.company_user, company_name='Long Ltd')
        cls.python = Skill.objects.create(skill_name='Python')
        cls.job = JobListing.objects.create(
            job_title='Backend Engineer', company=cls.company,
            status=JobListing.Status.ACTIVE)
        StudentSkill.objects.create(
            student=cls.student, skill=cls.python, skill_level='INTERMEDIATE')

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def _receipt(self):
        consent = UserConsent.objects.create(
            user=self.user,
            consent_type=UserConsent.ConsentType.CV_PROCESSING_CONSENT,
            notice_version='1.1', accepted=True, accepted_at=timezone.now(),
            source=UserConsent.Source.CV_PARSE)
        return cv_receipt.issue(self.user.id, consent.id)

    def _apply(self, education, experience):
        return self.client.post('/api/job-listings/applications/', {
            'job': self.job.id,
            'needs_work_permit': False,
            'cv_parse_receipt': self._receipt(),
            'applicant_snapshot': {
                'skills': [self.python.id],
                'education': education,
                'experience': experience,
            },
        }, format='json')

    def test_more_than_five_entries_are_all_stored(self):
        education = [f'Degree {i}' for i in range(8)]
        experience = [f'Role {i}' for i in range(7)]

        response = self._apply(education, experience)

        self.assertEqual(response.status_code, 201, response.data)
        snapshot = JobApplication.objects.get().applicant_snapshot
        self.assertEqual(snapshot['education'], education)
        self.assertEqual(snapshot['experience'], experience)

    def test_the_employer_sees_every_stored_entry(self):
        education = [f'Degree {i}' for i in range(8)]
        self._apply(education, [])

        client = APIClient()
        client.force_authenticate(self.company_user)
        row = client.get('/api/job-listings/company/applications/').json()[0]

        self.assertEqual(len(row['applicant_snapshot']['education']), 8)

    def test_only_the_confirmed_entries_are_stored(self):
        """What the student removed must not reach the employer.

        The server stores what it is sent; this asserts it does not add back
        anything, so a client that submits the trimmed list is enough.
        """
        response = self._apply(['Kept one', 'Kept two'], [])

        snapshot = JobApplication.objects.get().applicant_snapshot
        self.assertEqual(snapshot['education'], ['Kept one', 'Kept two'])
        self.assertEqual(snapshot['experience'], [])

    def test_the_forty_entry_ceiling_still_holds(self):
        response = self._apply([f'Degree {i}' for i in range(41)], [])

        self.assertEqual(response.status_code, 400)


class TranscriptVerifiedSkillsReachEmployersTests(TestCase):
    """A skill approved through transcript review is verified evidence."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            email='transcript-emp@university.test', password='Strong1!',
            role=User.Role.STUDENT)
        cls.student = Student.objects.create(
            user=cls.user, student_name='Transcript Student',
            matric_number='S222222')
        cls.company_user = User.objects.create_user(
            email='transcript-emp@business.test', password='Strong1!',
            role=User.Role.COMPANY)
        cls.company = Company.objects.create(
            user=cls.company_user, company_name='Transcript Ltd')
        cls.python = Skill.objects.create(skill_name='Python')
        cls.job = JobListing.objects.create(
            job_title='Backend Engineer', company=cls.company,
            status=JobListing.Status.ACTIVE)
        StudentSkill.objects.create(
            student=cls.student, skill=cls.python, skill_level='INTERMEDIATE')

    def _verified_transcript(self):
        from resources.models import TranscriptSkillEvidence, TranscriptUpload

        transcript = TranscriptUpload.objects.create(
            student=self.student,
            status=TranscriptUpload.Status.PARSED,
            document_type_status=TranscriptUpload.DocumentTypeStatus.LIKELY_TRANSCRIPT,
            verification_status=TranscriptUpload.VerificationStatus.MANUALLY_VERIFIED,
        )
        TranscriptSkillEvidence.objects.create(
            transcript=transcript, skill=self.python, skill_level='INTERMEDIATE')
        return transcript

    def _apply(self):
        client = APIClient()
        client.force_authenticate(self.user)
        consent = UserConsent.objects.create(
            user=self.user,
            consent_type=UserConsent.ConsentType.CV_PROCESSING_CONSENT,
            notice_version='1.1', accepted=True, accepted_at=timezone.now(),
            source=UserConsent.Source.CV_PARSE)
        return client.post('/api/job-listings/applications/', {
            'job': self.job.id,
            'needs_work_permit': False,
            'cv_parse_receipt': cv_receipt.issue(self.user.id, consent.id),
            'applicant_snapshot': {'skills': [self.python.id],
                                   'education': ['BSc'], 'experience': []},
        }, format='json')

    def _employer_skills(self):
        client = APIClient()
        client.force_authenticate(self.company_user)
        return client.get(
            '/api/job-listings/company/applications/').json()[0]['student_skills']

    def test_a_transcript_verified_skill_is_submitted_as_verified(self):
        self._verified_transcript()

        self._apply()

        snapshot = JobApplication.objects.get().applicant_snapshot
        self.assertTrue(snapshot['skills'][0]['verified'],
                        'transcript review is evidence too')

    def test_a_pending_transcript_does_not_make_a_skill_verified(self):
        from resources.models import TranscriptSkillEvidence, TranscriptUpload

        transcript = TranscriptUpload.objects.create(
            student=self.student,
            verification_status=TranscriptUpload.VerificationStatus.PENDING)
        TranscriptSkillEvidence.objects.create(
            transcript=transcript, skill=self.python, skill_level='INTERMEDIATE')

        self._apply()

        snapshot = JobApplication.objects.get().applicant_snapshot
        self.assertFalse(snapshot['skills'][0]['verified'])

    def test_the_legacy_fallback_also_counts_transcript_evidence(self):
        self._verified_transcript()
        JobApplication.objects.create(
            student=self.student, job=self.job, applicant_snapshot={})

        skills = self._employer_skills()

        self.assertEqual(len(skills), 1)
        self.assertTrue(skills[0]['verified'])


class WithdrawnConsentBlocksReceiptTests(TestCase):
    """A receipt cannot outlive the permission it represents."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            email='wr@university.test', password='Strong1!', role=User.Role.STUDENT)
        cls.student = Student.objects.create(user=cls.user, student_name='WR')
        cls.company_user = User.objects.create_user(
            email='wr@business.test', password='Strong1!', role=User.Role.COMPANY)
        cls.company = Company.objects.create(user=cls.company_user, company_name='WR Ltd')
        cls.python = Skill.objects.create(skill_name='Python')
        cls.job = JobListing.objects.create(
            job_title='Backend Engineer', company=cls.company,
            status=JobListing.Status.ACTIVE)
        StudentSkill.objects.create(
            student=cls.student, skill=cls.python, skill_level='INTERMEDIATE')

    def test_a_receipt_whose_consent_was_withdrawn_is_refused(self):
        consent = UserConsent.objects.create(
            user=self.user,
            consent_type=UserConsent.ConsentType.CV_PROCESSING_CONSENT,
            notice_version='1.1', accepted=True, accepted_at=timezone.now(),
            source=UserConsent.Source.CV_PARSE)
        token = cv_receipt.issue(self.user.id, consent.id)

        consent.withdrawn_at = timezone.now()
        consent.save()

        client = APIClient()
        client.force_authenticate(self.user)
        response = client.post('/api/job-listings/applications/', {
            'job': self.job.id,
            'needs_work_permit': False,
            'cv_parse_receipt': token,
            'applicant_snapshot': {'skills': [self.python.id],
                                   'education': ['BSc'], 'experience': []},
        }, format='json')

        self.assertEqual(response.status_code, 400)
        self.assertIn('cv_parse_receipt', response.data)
        self.assertFalse(JobApplication.objects.exists())


class TemporaryCvSweepTests(TestCase):
    """A hard kill bypasses finally; the sweeper is what covers that."""

    def _make_temp_cv(self, age_seconds):
        handle, path = tempfile.mkstemp(suffix='.pdf', prefix='cv-')
        os.close(handle)
        old = time.time() - age_seconds
        os.utime(path, (old, old))
        return path

    def test_an_abandoned_file_is_removed(self):
        from job_listings.cv_parser import SWEEP_AGE_SECONDS, sweep_orphaned_cv_files

        path = self._make_temp_cv(SWEEP_AGE_SECONDS + 60)

        sweep_orphaned_cv_files()

        self.assertFalse(os.path.exists(path))

    def test_a_file_from_a_request_in_flight_is_left_alone(self):
        from job_listings.cv_parser import sweep_orphaned_cv_files

        path = self._make_temp_cv(5)
        try:
            sweep_orphaned_cv_files()
            self.assertTrue(os.path.exists(path),
                            'a concurrent parse must not lose its file')
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def test_the_sweep_never_raises(self):
        from job_listings.cv_parser import sweep_orphaned_cv_files

        with patch('os.listdir', side_effect=OSError('nope')):
            self.assertEqual(sweep_orphaned_cv_files(), 0)


class SavedJobTests(TestCase):
    """The bookmark is a private shortlist, and it has to actually save.

    The button existed on the jobs page with no handler behind it, so pressing
    it did nothing at all.
    """

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            email='saver@university.test', password='Strong1!',
            role=User.Role.STUDENT)
        cls.student = Student.objects.create(user=cls.user, student_name='S')
        cls.other_user = User.objects.create_user(
            email='other@university.test', password='Strong1!',
            role=User.Role.STUDENT)
        cls.other = Student.objects.create(user=cls.other_user, student_name='O')

        cls.job = JobListing.objects.create(
            job_title='Backend Engineer',
            source_type=JobListing.SourceType.SCRAPED,
            source_url='https://example.test/saved-1')
        cls.lapsed = JobListing.objects.create(
            job_title='Lapsed Role',
            source_type=JobListing.SourceType.SCRAPED,
            status=JobListing.Status.CLOSED,
            source_url='https://example.test/saved-2')

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def url(self, job):
        return f'/api/scrape-jobs/scraped/{job.id}/save/'

    def test_saving_records_the_bookmark(self):
        response = self.client.post(self.url(self.job))

        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.data['is_saved'])
        self.assertTrue(SavedJob.objects.filter(
            student=self.student, job=self.job).exists())

    def test_saving_twice_is_the_same_as_saving_once(self):
        """A double-click must not 500 on the unique constraint."""
        self.client.post(self.url(self.job))
        response = self.client.post(self.url(self.job))

        self.assertEqual(response.status_code, 201)
        self.assertEqual(SavedJob.objects.filter(student=self.student).count(), 1)

    def test_unsaving_removes_it(self):
        self.client.post(self.url(self.job))

        response = self.client.delete(self.url(self.job))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data['is_saved'])
        self.assertFalse(SavedJob.objects.filter(student=self.student).exists())

    def test_unsaving_something_never_saved_is_not_an_error(self):
        response = self.client.delete(self.url(self.job))

        self.assertEqual(response.status_code, 200)

    def test_the_listing_reports_whether_it_is_saved(self):
        self.client.post(self.url(self.job))

        rows = self.client.get('/api/scrape-jobs/scraped/').json()
        by_id = {row['id']: row for row in
                 (rows['results'] if isinstance(rows, dict) else rows)}

        self.assertTrue(by_id[self.job.id]['is_saved'])

    def test_the_saved_filter_returns_only_bookmarks(self):
        self.client.post(self.url(self.job))

        rows = self.client.get('/api/scrape-jobs/scraped/?saved=true').json()
        results = rows['results'] if isinstance(rows, dict) else rows

        self.assertEqual([row['id'] for row in results], [self.job.id])

    def test_a_lapsed_saved_job_is_still_returned(self):
        """Dropping it would look like the bookmark had failed. It is kept and
        its status is reported, so the page can label it closed."""
        self.client.post(self.url(self.lapsed))

        rows = self.client.get(
            '/api/scrape-jobs/scraped/?saved=true&include_expired=true').json()
        results = rows['results'] if isinstance(rows, dict) else rows
        row = next(r for r in results if r['id'] == self.lapsed.id)

        self.assertEqual(row['status'], 'CLOSED')

    def test_one_students_shortlist_is_not_anothers(self):
        self.client.post(self.url(self.job))
        self.client.force_authenticate(self.other_user)

        rows = self.client.get('/api/scrape-jobs/scraped/?saved=true').json()
        results = rows['results'] if isinstance(rows, dict) else rows

        self.assertEqual(results, [])

    def test_an_anonymous_visitor_sees_nothing_saved(self):
        self.client.post(self.url(self.job))
        self.client.force_authenticate(None)

        rows = self.client.get('/api/scrape-jobs/scraped/').json()
        results = rows['results'] if isinstance(rows, dict) else rows

        self.assertTrue(all(row['is_saved'] is False for row in results))

    def test_a_company_cannot_save(self):
        company_user = User.objects.create_user(
            email='co@business.test', password='Strong1!',
            role=User.Role.COMPANY)
        Company.objects.create(user=company_user, company_name='Co')
        self.client.force_authenticate(company_user)

        self.assertEqual(self.client.post(self.url(self.job)).status_code, 403)

    def test_saving_is_never_disclosed_to_the_employer(self):
        """A shortlist commits the student to nothing, which is the whole
        difference between saving and applying."""
        self.client.post(self.url(self.job))

        self.assertFalse(JobApplication.objects.exists())


class SkillExtractionEndpointTests(TestCase):
    """Reading skills out of a draft description, for the post-a-job form.

    A suggestion the company then edits. The extractor knows a skill is
    wanted but never at what level, and the level is what candidates are
    scored against -- so this fills names only.
    """

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            email='extract@business.test', password='Strong1!',
            role=User.Role.COMPANY)
        Company.objects.create(user=cls.user, company_name='Co')
        for name in ('Python', 'Django', 'SAP', 'React'):
            Skill.objects.get_or_create(skill_name=name)

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    URL = '/api/job-listings/skills/extract/'

    def test_it_finds_the_skills_in_a_description(self):
        response = self.client.post(self.URL, {
            'text': 'We need a backend developer with experience in Python '
                    'and Django. React knowledge is a plus.',
        }, format='json')

        self.assertEqual(response.status_code, 200)
        names = {row['skill_name'] for row in response.data['skills']}
        self.assertEqual(names, {'Python', 'Django', 'React'})

    def test_it_returns_no_level(self):
        """The level is the company's judgement, not the extractor's."""
        response = self.client.post(self.URL, {
            'text': 'Looking for a developer proficient in Python and Django '
                    'to build our internal tools.',
        }, format='json')

        for row in response.data['skills']:
            self.assertNotIn('required_level', row)
            self.assertNotIn('level', row)

    def test_it_uses_the_same_rules_as_the_scraper(self):
        """"go live" is not the Go language here either."""
        Skill.objects.get_or_create(skill_name='Go')

        response = self.client.post(self.URL, {
            'text': 'Coordinate testing before changes go live and support '
                    'the business through each go-live weekend.',
        }, format='json')

        names = {row['skill_name'] for row in response.data['skills']}
        self.assertNotIn('Go', names)

    def test_a_short_description_is_refused_with_a_reason(self):
        response = self.client.post(self.URL, {'text': 'Python'},
                                    format='json')

        self.assertEqual(response.status_code, 400)
        self.assertIn('description', response.data['detail'])

    def test_only_a_company_may_call_it(self):
        student_user = User.objects.create_user(
            email='nosy@university.test', password='Strong1!',
            role=User.Role.STUDENT)
        Student.objects.create(user=student_user, student_name='S')
        self.client.force_authenticate(student_user)

        response = self.client.post(self.URL, {
            'text': 'A description long enough to pass the length check here.',
        }, format='json')

        self.assertEqual(response.status_code, 403)


class EnterpriseSkillVocabularyTests(TestCase):
    """The vocabulary has to contain what the Malaysian market advertises.

    It held 162 skills and not one of them matched SAP, ERP or Oracle, so an
    ERP / SAP Consultant skill gap could only report generic words -- it
    listed Debugging and Programming and nothing about SAP.
    """

    def test_the_enterprise_systems_are_in_the_vocabulary(self):
        from django.core.management import call_command
        from io import StringIO
        call_command('import_skills', stdout=StringIO())

        for name in ('SAP', 'ERP', 'Oracle', 'ABAP', 'SAP FICO',
                     'SAP S/4HANA', 'Microsoft Dynamics', 'CRM'):
            with self.subTest(name=name):
                self.assertTrue(Skill.objects.filter(skill_name=name).exists())

    def test_a_sap_advert_now_yields_sap_skills(self):
        from django.core.management import call_command
        from io import StringIO
        from scrape_jobs.skill_extractor import extract_skills_from_text
        call_command('import_skills', stdout=StringIO())

        names = {s.skill_name for s in extract_skills_from_text(
            'SAP FICO Consultant. Configure SAP S/4HANA finance modules, write '
            'ABAP reports, and support the ERP rollout across the group.')}

        self.assertIn('SAP', names)
        self.assertIn('ABAP', names)
        self.assertIn('ERP', names)

    def test_team_dynamics_is_not_microsoft_dynamics(self):
        """Bare "Dynamics" is deliberately not an alias."""
        from django.core.management import call_command
        from io import StringIO
        from scrape_jobs.skill_extractor import extract_skills_from_text
        call_command('import_skills', stdout=StringIO())

        names = {s.skill_name for s in extract_skills_from_text(
            'You will understand team dynamics and market dynamics in a fast '
            'moving software engineering environment.')}

        self.assertNotIn('Microsoft Dynamics', names)
