from datetime import datetime, timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import (
    AdminProfile, Company, SkillGap, Student, StudentSkill, StudentTargetRole,
    User,
)
from job_listings.models import JobApplication, JobListing, JobSkill
from resources.models import LearningResource
from resources.skill_recognition import apply_skills
from scrape_jobs.models import (
    JobCategory, JobTitle, MarketRole, Skill,
)

from .models import Announcement
from .skill_gap_snapshots import refresh_skill_gaps
from .views import MAX_RESOURCES_PER_SKILL, pick_resources_for_gap, shift_month


class StudentDashboardDemandTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.student_user = User.objects.create_user(
            email='dashboard-student@university.test',
            password='Strong1!',
            role=User.Role.STUDENT,
        )
        cls.student = Student.objects.create(
            user=cls.student_user,
            student_name='Dashboard Student',
        )
        cls.company_user = User.objects.create_user(
            email='dashboard-company@business.test',
            password='Strong1!',
            role=User.Role.COMPANY,
        )
        cls.company = Company.objects.create(
            user=cls.company_user,
            company_name='Analytics Company',
        )
        cls.category = JobCategory.objects.create(category_name='Software Engineer')
        cls.backend = MarketRole.objects.create(
            name='Backend Developer', broad_area='Software & Applications')
        cls.data_engineer = MarketRole.objects.create(
            name='Data Engineer', broad_area='Data & AI')

        current_month = timezone.localdate().replace(day=1)
        previous_month = shift_month(current_month, -1)
        cls.software_listing = JobListing.objects.create(
            job_title='Backend Engineer',
            market_role=cls.backend,
            classification_method='REVIEWED_TITLE_ALIAS',
            category=cls.category,
            source_type=JobListing.SourceType.SCRAPED,
            source_url='https://example.test/jobs/software',
            posted_date=previous_month,
        )
        JobListing.objects.create(
            job_title='Database Engineer',
            market_role=cls.data_engineer,
            classification_method='REVIEWED_TITLE_ALIAS',
            category=cls.category,
            source_type=JobListing.SourceType.SCRAPED,
            source_url='https://example.test/jobs/data',
            posted_date=current_month,
        )
        # Unclassified: no Market Role, so it counts towards the market total
        # but must never rank as an area of demand.
        JobListing.objects.create(
            job_title='Platform Specialist',
            category=cls.category,
            source_type=JobListing.SourceType.SCRAPED,
            source_url='https://example.test/jobs/unclassified',
            posted_date=current_month,
        )
        company_listing = JobListing.objects.create(
            company=cls.company,
            job_title='Graduate Developer',
            source_type=JobListing.SourceType.COMPANY,
        )
        JobApplication.objects.create(
            student=cls.student,
            job=company_listing,
            status=JobApplication.Status.SHORTLISTED,
        )

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.student_user)

    def test_first_login_receives_overall_market_overview(self):
        demand = self.client.get('/api/dashboard/student/').data['market_demand']

        self.assertEqual(demand['mode'], 'OVERVIEW')
        self.assertIsNone(demand['target_market_role'])
        self.assertIsNone(demand['target_broad_area'])
        self.assertEqual(demand['total_postings'], 3)
        self.assertIn(demand['top_broad_areas'][0]['name'],
                      {'Software & Applications', 'Data & AI'})

    def test_the_chart_can_be_scoped_to_a_market_role(self):
        response = self.client.get(
            '/api/dashboard/market-demand/?role=Backend%20Developer')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['mode'], 'TARGET')
        self.assertEqual(response.data['target_market_role'], 'Backend Developer')
        self.assertEqual(response.data['total_postings'], 1)

    def test_the_chart_can_be_scoped_to_a_broad_area(self):
        response = self.client.get(
            '/api/dashboard/market-demand/?broad_area=Data%20%26%20AI')

        self.assertEqual(response.data['target_broad_area'], 'Data & AI')
        self.assertEqual(response.data['total_postings'], 1)

    def test_browsing_a_role_does_not_change_the_saved_target(self):
        StudentTargetRole.objects.create(
            student=self.student, market_role=self.backend)

        response = self.client.get(
            '/api/dashboard/market-demand/?role=Data%20Engineer')

        self.assertEqual(response.data['target_market_role'], 'Data Engineer')
        self.assertEqual(self.student.target_roles.get().market_role,
                         self.backend)

    def test_market_demand_without_param_uses_the_saved_target(self):
        StudentTargetRole.objects.create(
            student=self.student, market_role=self.backend)

        response = self.client.get('/api/dashboard/market-demand/')

        self.assertEqual(response.data['target_market_role'], 'Backend Developer')

    def test_market_demand_ignores_an_invalid_role(self):
        response = self.client.get(
            '/api/dashboard/market-demand/?role=Underwater%20Basketry')

        self.assertEqual(response.data['mode'], 'OVERVIEW')
        self.assertIsNone(response.data['target_market_role'])

    def test_unclassified_adverts_are_never_ranked(self):
        """An unclassified advert is the absence of a classification, not an
        area of demand. It counts towards the market total and nothing else."""
        response = self.client.get('/api/dashboard/market-demand/')

        areas = [row['name'] for row in response.data['top_broad_areas']]
        roles = [row['name'] for row in response.data['top_market_roles']]
        self.assertNotIn('', areas)
        self.assertEqual(len(roles), 2)
        self.assertEqual(response.data['market_role_postings'], 2)

    def test_coverage_counts_classified_not_checked(self):
        response = self.client.get('/api/dashboard/market-demand/')
        quality = response.data['data_quality']

        self.assertEqual(quality['market_postings_in_period'], 3)
        self.assertEqual(quality['matched_postings_in_period'], 2)
        self.assertNotIn('verified', str(quality).lower())

    def test_a_role_beats_a_broad_area_when_both_are_given(self):
        """The role is the narrower answer, so it wins."""
        response = self.client.get(
            '/api/dashboard/market-demand/'
            '?broad_area=Data%20%26%20AI&role=Backend%20Developer')

        self.assertEqual(response.data['target_market_role'], 'Backend Developer')
        self.assertEqual(response.data['total_postings'], 1)

    def test_market_demand_rejects_non_student(self):
        self.client.force_authenticate(self.company_user)

        response = self.client.get('/api/dashboard/market-demand/')

        self.assertEqual(response.status_code, 403)


class SkillGapTests(TestCase):
    """The live skill-gap analysis that replaced the page's mock data."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            email='gap-student@university.test', password='Strong1!', role=User.Role.STUDENT)
        cls.student = Student.objects.create(user=cls.user, student_name='Gap Student')

        cls.role = MarketRole.objects.create(
            name='Software Engineer', broad_area='Software & Applications')
        cls.other_role = MarketRole.objects.create(
            name='Data Scientist', broad_area='Data & AI')

        cls.python = Skill.objects.create(skill_name='Python')
        cls.sql = Skill.objects.create(skill_name='SQL')
        cls.docker = Skill.objects.create(skill_name='Docker')

        # Student holds Python only.
        StudentSkill.objects.create(
            student=cls.student, skill=cls.python, skill_level='ADVANCED')

        # Six adverts on the target Market Role clears MIN_LISTINGS_FOR_TARGET.
        for index in range(6):
            listing = JobListing.objects.create(
                job_title=f'Developer {index}',
                market_role=cls.role,
                source_type=JobListing.SourceType.SCRAPED,
                source_url=f'https://example.test/target/{index}',
            )
            JobSkill.objects.create(job=listing, skill=cls.python)
            JobSkill.objects.create(job=listing, skill=cls.sql)
            if index < 1:
                JobSkill.objects.create(job=listing, skill=cls.docker)

        # One advert elsewhere, so the other role stays under the floor.
        other = JobListing.objects.create(
            job_title='Data Scientist',
            market_role=cls.other_role,
            source_type=JobListing.SourceType.SCRAPED,
            source_url='https://example.test/other/1',
        )
        JobSkill.objects.create(job=other, skill=cls.docker)

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_splits_matched_and_missing_skills(self):
        StudentTargetRole.objects.create(
            student=self.student, market_role=self.role)

        response = self.client.get('/api/dashboard/skill-gap/')

        self.assertEqual(response.status_code, 200)
        data = response.data
        self.assertEqual(data['mode'], 'TARGET')
        self.assertEqual([row['skill'] for row in data['matched_skills']], ['Python'])
        self.assertCountEqual([row['skill'] for row in data['missing_skills']], ['SQL', 'Docker'])

    def test_match_percentage_reflects_real_counts(self):
        StudentTargetRole.objects.create(
            student=self.student, market_role=self.role)

        data = self.client.get('/api/dashboard/skill-gap/').data

        # 1 held of 3 demanded skills.
        self.assertEqual(data['critical_skill_count'], 3)
        self.assertEqual(data['match_percentage'], 33)

    def test_demand_percentage_and_priority(self):
        StudentTargetRole.objects.create(
            student=self.student, market_role=self.role)

        data = self.client.get('/api/dashboard/skill-gap/').data
        by_skill = {row['skill']: row for row in data['missing_skills']}

        # SQL appears in all 6 target listings, Docker in 1 of 6.
        self.assertEqual(by_skill['SQL']['demand_percentage'], 100.0)
        self.assertEqual(by_skill['SQL']['priority_level'], 'HIGH')
        self.assertEqual(by_skill['Docker']['demand_percentage'], 16.7)
        self.assertEqual(by_skill['Docker']['priority_level'], 'MEDIUM')

    def test_a_single_advert_still_scopes_to_the_role(self):
        """One advert is answered from that one advert.

        A student who names a career gets what the market said about that
        career, however little it said. Widening them into a career area they
        did not ask about answers a different question -- so the count the
        figure rests on is reported instead, and the page shows it.
        """
        StudentTargetRole.objects.create(
            student=self.student, market_role=self.other_role)

        data = self.client.get('/api/dashboard/skill-gap/').data

        self.assertEqual(data['mode'], 'TARGET')
        self.assertEqual(data['scope'], 'ROLE')
        self.assertFalse(data['data_quality']['fell_back_to_market'])
        self.assertEqual(data['data_quality']['role_listing_count'], 1)
        self.assertEqual(data['total_listings'], 1)

    def test_a_role_with_no_adverts_at_all_still_widens(self):
        """Nothing to analyse is the one case left that has to fall back."""
        empty = MarketRole.objects.create(
            name='Prompt Engineer', broad_area='Data & AI')
        StudentTargetRole.objects.create(
            student=self.student, market_role=empty)

        data = self.client.get('/api/dashboard/skill-gap/').data

        self.assertEqual(data['data_quality']['role_listing_count'], 0)
        self.assertNotEqual(data['scope'], 'ROLE')

    def test_no_target_uses_whole_market(self):
        data = self.client.get('/api/dashboard/skill-gap/').data

        self.assertEqual(data['mode'], 'OVERVIEW')
        self.assertFalse(data['data_quality']['has_target'])
        self.assertIsNone(data['target_role'])
        self.assertIsNone(data['target_broad_area'])

    def test_a_role_param_overrides_the_saved_target(self):
        StudentTargetRole.objects.create(
            student=self.student, market_role=self.other_role)

        data = self.client.get(
            '/api/dashboard/skill-gap/?role=Software%20Engineer').data

        self.assertEqual(data['mode'], 'TARGET')
        self.assertEqual(data['target_role'], 'Software Engineer')
        self.assertEqual(data['scope'], 'ROLE')

    def test_student_skills_outside_critical_list_still_returned(self):
        extra = Skill.objects.create(skill_name='Photoshop')
        StudentSkill.objects.create(student=self.student, skill=extra, skill_level='BEGINNER')
        StudentTargetRole.objects.create(
            student=self.student, market_role=self.role)

        data = self.client.get('/api/dashboard/skill-gap/').data

        self.assertEqual([row['skill'] for row in data['other_skills']], ['Photoshop'])

    def test_soft_skills_are_ranked_separately_from_technical_gaps(self):
        """'Communication' sits in ~76% of adverts and must not be the top gap."""
        communication = Skill.objects.create(
            skill_name='Communication', skill_category='Soft Skill')
        for listing in JobListing.objects.filter(market_role=self.role):
            JobSkill.objects.create(job=listing, skill=communication)
        StudentTargetRole.objects.create(
            student=self.student, market_role=self.role)

        data = self.client.get('/api/dashboard/skill-gap/').data

        technical = [row['skill'] for row in data['missing_skills']]
        soft = [row['skill'] for row in data['soft_skills']]
        self.assertNotIn('Communication', technical,
                         'soft skills must not compete in the technical gap list')
        self.assertIn('Communication', soft)
        self.assertEqual(soft[0], 'Communication')

    def test_soft_skills_report_demand_and_whether_held(self):
        teamwork = Skill.objects.create(skill_name='Teamwork', skill_category='Soft Skill')
        for listing in JobListing.objects.filter(market_role=self.role)[:3]:
            JobSkill.objects.create(job=listing, skill=teamwork)
        StudentSkill.objects.create(
            student=self.student, skill=teamwork, skill_level='INTERMEDIATE')
        StudentTargetRole.objects.create(
            student=self.student, market_role=self.role)

        row = next(r for r in self.client.get('/api/dashboard/skill-gap/').data['soft_skills']
                   if r['skill'] == 'Teamwork')

        self.assertTrue(row['held'])
        self.assertEqual(row['skill_level'], 'INTERMEDIATE')
        self.assertEqual(row['demand_percentage'], 50.0)

    def test_match_percentage_ignores_soft_skills(self):
        """Holding Communication must not inflate the technical match score."""
        communication = Skill.objects.create(
            skill_name='Communication', skill_category='Soft Skill')
        for listing in JobListing.objects.filter(market_role=self.role):
            JobSkill.objects.create(job=listing, skill=communication)
        StudentSkill.objects.create(
            student=self.student, skill=communication, skill_level='ADVANCED')
        StudentTargetRole.objects.create(
            student=self.student, market_role=self.role)

        data = self.client.get('/api/dashboard/skill-gap/').data

        # Still 1 held (Python) of 3 technical demanded skills.
        self.assertEqual(data['critical_skill_count'], 3)
        self.assertEqual(data['match_percentage'], 33)

    def test_held_soft_skill_is_not_duplicated_into_other_skills(self):
        communication = Skill.objects.create(
            skill_name='Communication', skill_category='Soft Skill')
        for listing in JobListing.objects.filter(market_role=self.role):
            JobSkill.objects.create(job=listing, skill=communication)
        StudentSkill.objects.create(
            student=self.student, skill=communication, skill_level='ADVANCED')
        StudentTargetRole.objects.create(
            student=self.student, market_role=self.role)

        data = self.client.get('/api/dashboard/skill-gap/').data

        self.assertNotIn('Communication', [row['skill'] for row in data['other_skills']])

    def test_recommends_resources_for_missing_skills_only(self):
        LearningResource.objects.create(
            skill=self.sql, title='SQL Basics', platform='Coursera',
            url='https://example.test/sql', type='Course')
        LearningResource.objects.create(
            skill=self.python, title='Python Basics', platform='Coursera',
            url='https://example.test/python', type='Course')
        StudentTargetRole.objects.create(
            student=self.student, market_role=self.role)

        data = self.client.get('/api/dashboard/skill-gap/').data

        titles = [row['title'] for row in data['recommended_resources']]
        self.assertIn('SQL Basics', titles)
        self.assertNotIn('Python Basics', titles, 'already-held skills need no resource')

    def test_rejects_non_student(self):
        company_user = User.objects.create_user(
            email='gap-company@business.test', password='Strong1!', role=User.Role.COMPANY)
        self.client.force_authenticate(company_user)

        response = self.client.get('/api/dashboard/skill-gap/')

        self.assertEqual(response.status_code, 403)


class BroadAreaSkillGapTests(TestCase):
    """Skill gap scoped by Market Role, widening to Broad Area when thin.

    Broad Area widens a *measurement* only. It never decides which Market Role
    an advert belongs to -- that stays a direct advert-to-role decision.
    """

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            email='area-student@university.test', password='Strong1!',
            role=User.Role.STUDENT)
        cls.student = Student.objects.create(user=cls.user,
                                             student_name='Area Student')

        cls.software = MarketRole.objects.create(
            name='Software Engineer', broad_area='Software & Applications')
        cls.frontend = MarketRole.objects.create(
            name='Frontend Developer', broad_area='Software & Applications')
        cls.security = MarketRole.objects.create(
            name='Security Analyst', broad_area='Cybersecurity')

        cls.python = Skill.objects.create(skill_name='Python')
        cls.react = Skill.objects.create(skill_name='React')
        StudentSkill.objects.create(
            student=cls.student, skill=cls.python, skill_level='ADVANCED')

        for index in range(6):
            listing = JobListing.objects.create(
                job_title=f'Software Engineer {index}',
                market_role=cls.software,
                classification_method='EXACT_MARKET_ROLE',
                source_type=JobListing.SourceType.SCRAPED,
                source_url=f'https://example.test/sw/{index}')
            JobSkill.objects.create(job=listing, skill=cls.python)
            JobSkill.objects.create(job=listing, skill=cls.react)

        thin_listing = JobListing.objects.create(
            job_title='Security Analyst', market_role=cls.security,
            classification_method='EXACT_MARKET_ROLE',
            source_type=JobListing.SourceType.SCRAPED,
            source_url='https://example.test/sec/1')
        JobSkill.objects.create(job=thin_listing, skill=cls.react)

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_a_market_role_scopes_the_analysis(self):
        response = self.client.get(
            '/api/dashboard/skill-gap/?role=Software%20Engineer')

        self.assertEqual(response.status_code, 200)
        data = response.data
        self.assertEqual(data['scope'], 'ROLE')
        self.assertEqual(data['mode'], 'TARGET')
        self.assertEqual(data['target_role'], 'Software Engineer')
        self.assertEqual(data['total_listings'], 6)
        self.assertEqual([row['skill'] for row in data['matched_skills']], ['Python'])
        self.assertEqual([row['skill'] for row in data['missing_skills']], ['React'])

    def test_a_broad_area_scopes_the_analysis(self):
        response = self.client.get(
            '/api/dashboard/skill-gap/?broad_area=Software%20%26%20Applications')

        self.assertEqual(response.data['scope'], 'BROAD_AREA')
        self.assertEqual(response.data['total_listings'], 6)

    def test_a_thin_role_widens_to_its_broad_area(self):
        """Frontend Developer has no adverts of its own, so the analysis says
        so and answers at the wider scope rather than at a scope of zero."""
        StudentTargetRole.objects.create(student=self.student,
                                         market_role=self.frontend)

        data = self.client.get('/api/dashboard/skill-gap/').data

        self.assertEqual(data['scope'], 'BROAD_AREA')
        self.assertTrue(data['data_quality']['fell_back_to_broad_area'])
        self.assertEqual(data['data_quality']['role_listing_count'], 0)
        self.assertEqual(data['total_listings'], 6)

    def test_a_role_with_one_advert_is_answered_from_it(self):
        """Security Analyst has a single advert, and that is what it reports.

        The evidence floor used to widen this to the whole market, which told
        a student about careers they had not asked about.
        """
        StudentTargetRole.objects.create(student=self.student,
                                         market_role=self.security)

        data = self.client.get('/api/dashboard/skill-gap/').data

        self.assertEqual(data['scope'], 'ROLE')
        self.assertEqual(data['data_quality']['role_listing_count'], 1)
        self.assertFalse(data['data_quality']['fell_back_to_market'])

    def test_an_invalid_role_is_ignored(self):
        response = self.client.get('/api/dashboard/skill-gap/?role=not-a-role')

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.data['target_role'])

    def test_the_scope_selector_lists_every_role_with_an_advert(self):
        """Including the ones with only one. Frontend Developer has none, so
        it is the only one absent."""
        response = self.client.get('/api/dashboard/skill-gap/market-roles/')

        names = {role['name'] for area in response.data['results']
                 for role in area['roles']}
        self.assertEqual(names, {'Software Engineer', 'Security Analyst'})
        self.assertNotIn('Frontend Developer', names)

    def test_the_scope_selector_groups_by_broad_area(self):
        response = self.client.get('/api/dashboard/skill-gap/market-roles/')

        self.assertEqual({area['name'] for area in response.data['results']},
                         {'Software & Applications', 'Cybersecurity'})

    def test_the_scope_selector_reports_coverage_not_verification(self):
        JobListing.objects.create(
            job_title='Mystery Role',
            source_type=JobListing.SourceType.SCRAPED,
            source_url='https://example.test/mystery')

        coverage = self.client.get(
            '/api/dashboard/skill-gap/market-roles/').data['coverage']

        self.assertEqual(coverage['scraped_total'], 8)
        self.assertEqual(coverage['classified_total'], 7)
        self.assertEqual(coverage['classified_percentage'], 87.5)
        self.assertNotIn('verified', str(coverage).lower())

    def test_the_role_profile_reports_its_evidence(self):
        response = self.client.get(
            '/api/dashboard/market-role/?role=Software%20Engineer')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['role']['name'], 'Software Engineer')
        self.assertEqual(response.data['role']['broad_area'],
                         'Software & Applications')
        self.assertEqual(response.data['listing_count'], 6)
        self.assertTrue(response.data['analysable'])
        self.assertEqual(response.data['classification_methods'],
                         [{'classification_method': 'EXACT_MARKET_ROLE',
                           'listing_count': 6}])

    def test_the_role_profile_requires_a_valid_role(self):
        self.assertEqual(
            self.client.get('/api/dashboard/market-role/').status_code, 400)
        self.assertEqual(
            self.client.get('/api/dashboard/market-role/?role=nope').status_code,
            400)

    def test_the_role_profile_rejects_the_unauthenticated(self):
        self.client.force_authenticate(None)

        response = self.client.get(
            '/api/dashboard/market-role/?role=Software%20Engineer')

        self.assertEqual(response.status_code, 401)


class SkillGapSnapshotTests(TestCase):
    """SkillGap rows record progress; the live view stays authoritative."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="gap-student@test.com", password="pw", role="STUDENT")
        self.student = Student.objects.create(user=self.user, student_name="Gap")

        self.role = MarketRole.objects.create(
            name="Software Engineer", broad_area="Software & Applications")
        self.target = StudentTargetRole.objects.create(
            student=self.student, market_role=self.role)

        self.python = Skill.objects.create(skill_name="Python")
        self.docker = Skill.objects.create(skill_name="Docker")

        # Enough adverts that the analysis trusts the role rather than
        # falling back to its Broad Area or the whole market.
        for index in range(6):
            listing = JobListing.objects.create(
                job_title=f"Software Engineer {index}",
                source_type=JobListing.SourceType.SCRAPED,
                market_role=self.role,
                classification_method="EXACT_MARKET_ROLE",
            )
            JobSkill.objects.create(job=listing, skill=self.python)
            JobSkill.objects.create(job=listing, skill=self.docker)

    def test_missing_skills_are_recorded_as_open_gaps(self):
        opened, closed, reopened = refresh_skill_gaps(self.student)

        self.assertEqual((opened, closed, reopened), (2, 0, 0))
        self.assertEqual(
            set(SkillGap.objects.filter(student=self.student)
                .values_list("skill__skill_name", flat=True)),
            {"Python", "Docker"},
        )
        self.assertTrue(all(
            gap.status == SkillGap.Status.OPEN
            for gap in SkillGap.objects.all()))

    def test_refresh_is_idempotent(self):
        refresh_skill_gaps(self.student)
        opened, closed, reopened = refresh_skill_gaps(self.student)

        self.assertEqual((opened, closed, reopened), (0, 0, 0))
        self.assertEqual(SkillGap.objects.count(), 2)

    def test_acquiring_a_skill_closes_the_gap_without_deleting_it(self):
        refresh_skill_gaps(self.student)
        StudentSkill.objects.create(
            student=self.student, skill=self.python, skill_level="INTERMEDIATE")

        opened, closed, reopened = refresh_skill_gaps(self.student)

        self.assertEqual(closed, 1)
        gap = SkillGap.objects.get(student=self.student, skill=self.python)
        self.assertEqual(gap.status, SkillGap.Status.CLOSED)
        self.assertIsNotNone(gap.closed_time)

    def test_a_student_without_a_target_records_nothing(self):
        StudentTargetRole.objects.filter(student=self.student).delete()

        self.assertEqual(refresh_skill_gaps(self.student), (0, 0, 0))
        self.assertFalse(SkillGap.objects.exists())

    def test_each_target_is_recorded_against_its_own_role(self):
        """Every gap row must name the target it was measured for.

        Passing no scope would resolve the student's *first* target, writing
        one target's gaps onto another's rows.
        """
        frontend = MarketRole.objects.create(
            name="Frontend Developer", broad_area="Software & Applications")
        StudentTargetRole.objects.create(
            student=self.student, market_role=frontend)

        refresh_skill_gaps(self.student)

        recorded = set(
            SkillGap.objects.filter(student=self.student)
            .values_list("target__market_role__name", flat=True)
        )
        # Frontend Developer has no adverts, so it widens to its Broad Area --
        # the same six adverts, and therefore still records gaps.
        self.assertEqual(recorded, {"Software Engineer", "Frontend Developer"})

    def test_a_thin_role_widens_to_its_area_rather_than_recording_nothing(self):
        frontend = MarketRole.objects.create(
            name="Frontend Developer", broad_area="Software & Applications")
        StudentTargetRole.objects.filter(student=self.student).delete()
        StudentTargetRole.objects.create(
            student=self.student, market_role=frontend)

        opened, _, _ = refresh_skill_gaps(self.student)

        self.assertEqual(opened, 2,
                         "the Broad Area fallback still yields a real gap")


class SkillGapResourceRankingTests(TestCase):
    """Recommendations must follow the gap's priority, not the alphabet."""

    def _skill(self, name):
        return Skill.objects.create(skill_name=name, skill_category='Technical')

    def _listing(self, url, skills):
        listing = JobListing.objects.create(
            job_title='Data Analyst', source_type=JobListing.SourceType.SCRAPED,
            source_url=url)
        for skill in skills:
            JobSkill.objects.create(job=listing, skill=skill)
        return listing

    def setUp(self):
        self.user = User.objects.create_user(
            email='ranking-student@university.test', password='Strong1!',
            role=User.Role.STUDENT)
        self.student = Student.objects.create(user=self.user, student_name='Ranked')

        # `high` is asked for by every listing, `low` by one. Their resource
        # titles are chosen so alphabetical ordering would put `low` first.
        self.high = self._skill('SQL')
        self.low = self._skill('Zebra Framework')
        for index in range(6):
            skills = [self.high] + ([self.low] if index == 0 else [])
            self._listing(f'https://example.test/rank-{index}', skills)

        for index in range(6):
            LearningResource.objects.create(
                skill=self.low, title=f'AAA Zebra Course {index}',
                platform='Coursera', url=f'https://example.test/z{index}',
                type='Course')
        LearningResource.objects.create(
            skill=self.high, title='ZZZ SQL Course', platform='Coursera',
            url='https://example.test/sql', type='Course')

        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_highest_demand_gap_is_recommended_first(self):
        rows = self.client.get('/api/dashboard/skill-gap/').data['recommended_resources']

        self.assertEqual(rows[0]['skill'], 'SQL')

    def test_one_skill_cannot_claim_every_slot(self):
        rows = self.client.get('/api/dashboard/skill-gap/').data['recommended_resources']

        # Six Zebra resources exist and would previously have filled the list,
        # leaving the highest-priority gap with nothing.
        zebra = [row for row in rows if row['skill'] == 'Zebra Framework']
        self.assertLessEqual(len(zebra), MAX_RESOURCES_PER_SKILL)
        self.assertIn('SQL', [row['skill'] for row in rows])

    def test_priority_is_reported_with_each_resource(self):
        rows = self.client.get('/api/dashboard/skill-gap/').data['recommended_resources']

        sql_row = next(row for row in rows if row['skill'] == 'SQL')
        self.assertEqual(sql_row['skill_priority'], 'HIGH')
        self.assertGreater(sql_row['skill_demand_percentage'], 0)

    def test_no_missing_skills_means_no_recommendations(self):
        self.assertEqual(pick_resources_for_gap([]), [])


class SkillGapRefreshTriggerTests(TestCase):
    """Skill gaps are event-driven, not scheduled.

    Two triggers, and no timer: validating a skill refreshes that student, and
    a scrape that moved the market refreshes everyone.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            email='trigger@university.test', password='Strong1!',
            role=User.Role.STUDENT)
        self.student = Student.objects.create(user=self.user, student_name='Trigger')

        self.role = MarketRole.objects.create(
            name='Systems Analyst', broad_area='Business & Delivery')
        self.target = StudentTargetRole.objects.create(
            student=self.student, market_role=self.role)

        self.python = Skill.objects.create(
            skill_name='Python', skill_category='Technical')
        for index in range(6):
            listing = JobListing.objects.create(
                job_title='Systems Analyst',
                source_type=JobListing.SourceType.SCRAPED,
                source_url=f'https://example.test/trigger-{index}',
                market_role=self.role,
                classification_method='EXACT_MARKET_ROLE')
            JobSkill.objects.create(job=listing, skill=self.python)

    def test_validating_a_skill_closes_the_gap_immediately(self):
        # The gap exists first...
        refresh_skill_gaps(self.student)
        self.assertTrue(
            SkillGap.objects.filter(
                student=self.student, skill=self.python,
                status=SkillGap.Status.OPEN).exists())

        # ...and apply_skills closes it without any scheduled job running.
        apply_skills(self.student, {self.python: 'ADVANCED'})

        row = SkillGap.objects.get(student=self.student, skill=self.python)
        self.assertEqual(row.status, SkillGap.Status.CLOSED)
        self.assertIsNotNone(row.closed_time)

    def test_a_first_validation_records_the_remaining_gaps(self):
        sql = Skill.objects.create(skill_name='SQL', skill_category='Technical')
        JobSkill.objects.create(
            job=JobListing.objects.first(), skill=sql)

        # Meets the adverts' requirement, so Python is genuinely closed.
        apply_skills(self.student, {self.python: 'INTERMEDIATE'})

        open_skills = set(
            SkillGap.objects
            .filter(student=self.student, status=SkillGap.Status.OPEN)
            .values_list('skill__skill_name', flat=True))
        self.assertEqual(open_skills, {'SQL'})

    def test_holding_a_skill_below_the_required_level_keeps_the_gap_open(self):
        """Holding a skill is not the same as being ready for it.

        The adverts ask Intermediate Python. A student at Beginner used to be
        counted as a full match and told the gap was closed, which is exactly
        the flattery this change removes.
        """
        apply_skills(self.student, {self.python: 'BEGINNER'})

        row = SkillGap.objects.get(student=self.student, skill=self.python)
        self.assertEqual(row.status, SkillGap.Status.OPEN)

    def test_applying_nothing_new_does_not_touch_the_gaps(self):
        # The gap has to be opened while the skill is still missing; closing
        # it is what leaves a row behind to compare against.
        refresh_skill_gaps(self.student)
        apply_skills(self.student, {self.python: 'ADVANCED'})
        before = SkillGap.objects.get(student=self.student, skill=self.python).updated_time

        # Re-applying the same level is a no-op upstream, so nothing refreshes.
        added, upgraded = apply_skills(self.student, {self.python: 'ADVANCED'})

        self.assertEqual((added, upgraded), (0, 0))
        after = SkillGap.objects.get(student=self.student, skill=self.python).updated_time
        self.assertEqual(before, after)

    def test_a_failing_refresh_never_breaks_the_skill_write(self):
        with patch('dashboard.skill_gap_snapshots.refresh_skill_gaps',
                   side_effect=RuntimeError('boom')):
            added, upgraded = apply_skills(self.student, {self.python: 'ADVANCED'})

        self.assertEqual(added, 1)
        self.assertTrue(
            StudentSkill.objects.filter(
                student=self.student, skill=self.python).exists(),
            'the validated skill must be saved even if the snapshot fails')


class DefaultTargetScopeTests(TestCase):
    """A student who names no scope gets the best one their target supports."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            email='scope-student@university.test', password='Strong1!',
            role=User.Role.STUDENT)
        cls.student = Student.objects.create(
            user=cls.user, student_name='Scope Student')

        cls.software = MarketRole.objects.create(
            name='Software Engineer', broad_area='Software & Applications')
        cls.frontend = MarketRole.objects.create(
            name='Frontend Developer', broad_area='Software & Applications')
        cls.lonely = MarketRole.objects.create(
            name='Data Scientist', broad_area='Data & AI')

        cls.python = Skill.objects.create(skill_name='Python')

        # Six adverts in the area, all on one role.
        for index in range(6):
            listing = JobListing.objects.create(
                job_title=f'Software Engineer {index}',
                market_role=cls.software,
                classification_method='EXACT_MARKET_ROLE',
                source_type=JobListing.SourceType.SCRAPED,
                source_url=f'https://example.test/scope/{index}')
            JobSkill.objects.create(job=listing, skill=cls.python)

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def _target(self, role):
        return StudentTargetRole.objects.create(student=self.student,
                                                market_role=role)

    def test_a_role_with_too_few_adverts_widens_to_its_broad_area(self):
        self._target(self.frontend)

        data = self.client.get('/api/dashboard/skill-gap/').data

        self.assertEqual(data['scope'], 'BROAD_AREA')
        self.assertEqual(data['mode'], 'TARGET')
        self.assertEqual(data['target_broad_area'], 'Software & Applications')
        # The role the student asked for is still named, so the page can say
        # which scope answered without losing what was requested.
        self.assertEqual(data['target_role'], 'Frontend Developer')
        self.assertTrue(data['data_quality']['has_target'])
        self.assertTrue(data['data_quality']['fell_back_to_broad_area'])
        self.assertFalse(data['data_quality']['fell_back_to_market'])

    def test_a_thin_role_in_a_thin_area_reaches_the_market(self):
        self._target(self.lonely)

        data = self.client.get('/api/dashboard/skill-gap/').data

        self.assertEqual(data['scope'], 'MARKET')
        self.assertTrue(data['data_quality']['has_target'])
        self.assertTrue(data['data_quality']['fell_back_to_market'])

    def test_a_role_above_the_evidence_floor_is_scoped_to_the_role(self):
        self._target(self.software)

        data = self.client.get('/api/dashboard/skill-gap/').data

        self.assertEqual(data['scope'], 'ROLE')
        self.assertEqual(data['target_role'], 'Software Engineer')
        self.assertEqual(data['data_quality']['role_listing_count'], 6)
        self.assertFalse(data['data_quality']['fell_back_to_broad_area'])

    def test_a_student_with_no_target_at_all_still_gets_the_market(self):
        data = self.client.get('/api/dashboard/skill-gap/').data

        self.assertEqual(data['scope'], 'MARKET')
        self.assertEqual(data['mode'], 'OVERVIEW')


class ClassificationCoverageTests(TestCase):
    """Coverage counts what the classifier placed on a Market Role.

    Per-listing human review was considered and dropped: scraped adverts lapse
    in about 30 days, so a review queue would never empty and the figure would
    sit at zero permanently. What the number reports is therefore *classified*,
    and the label says so rather than implying a check nobody performs.
    """

    @classmethod
    def setUpTestData(cls):
        cls.student_user = User.objects.create_user(
            email='coverage-student@university.test', password='Strong1!',
            role=User.Role.STUDENT)
        cls.student = Student.objects.create(
            user=cls.student_user, student_name='Coverage Student')

        cls.analyst = MarketRole.objects.create(
            name='Data Analyst', broad_area='Data & AI')
        cls.engineer = MarketRole.objects.create(
            name='Data Engineer', broad_area='Data & AI')

        month = timezone.localdate().replace(day=1)
        # Classified by the matcher, reviewed by nobody -- the state every
        # real advert is in.
        for i in range(3):
            JobListing.objects.create(
                job_title=f'Auto Matched {i}',
                source_type=JobListing.SourceType.SCRAPED,
                source_url=f'https://example.test/auto{i}',
                posted_date=month,
                market_role=cls.analyst,
                classification_method='REVIEWED_TITLE_ALIAS')
        # No Market Role: coverage does not count it, and nor does any ranking.
        JobListing.objects.create(
            job_title='Unplaceable',
            source_type=JobListing.SourceType.SCRAPED,
            source_url='https://example.test/none',
            classification_method='UNCLASSIFIED',
            posted_date=month)

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.student_user)

    def _quality(self):
        response = self.client.get('/api/dashboard/market-demand/')
        self.assertEqual(response.status_code, 200, response.data)
        return response.json()['data_quality']

    def test_classified_adverts_are_counted(self):
        quality = self._quality()

        self.assertEqual(quality['matched_postings_in_period'], 3)
        self.assertEqual(quality['matched_coverage_percentage'], 75.0)

    def test_unclassified_adverts_are_excluded(self):
        """An unclassified advert is the absence of a classification, so it is
        the 25% that coverage does not claim."""
        quality = self._quality()

        self.assertEqual(quality['market_postings_in_period'], 4)
        self.assertLess(quality['matched_coverage_percentage'], 100)

    def test_the_classification_method_does_not_gate_the_figure(self):
        """A JD_RESOLVED advert counts exactly as a REVIEWED_TITLE_ALIAS one
        does. The method is recorded for provenance, not as a quality gate."""
        before = self._quality()['matched_coverage_percentage']

        JobListing.objects.filter(job_title='Auto Matched 0').update(
            classification_method='JD_RESOLVED')

        self.assertEqual(self._quality()['matched_coverage_percentage'], before)

    def test_roles_are_reported_with_their_evidence_count(self):
        """A single-digit role count must not read as the whole market."""
        response = self.client.get('/api/dashboard/market-demand/').json()

        self.assertIn('top_market_roles', response)
        self.assertIn('market_role_postings', response)
        self.assertEqual(response['market_role_postings'], 3)

    def test_roles_are_ranked_by_market_role_not_by_broad_area(self):
        """A student looks for "Data Analyst", not "Data & AI"."""
        JobListing.objects.filter(job_title='Auto Matched 2').update(
            market_role=self.engineer)

        response = self.client.get('/api/dashboard/market-demand/').json()

        ranked = [(row['name'], row['job_count'])
                  for row in response['top_market_roles']]
        self.assertEqual(ranked, [('Data Analyst', 2), ('Data Engineer', 1)])
        self.assertEqual(response['market_role_postings'], 3)

    def test_rankings_include_every_classified_advert(self):
        response = self.client.get('/api/dashboard/market-demand/').json()

        self.assertEqual(len(response['top_broad_areas']), 1)
        self.assertEqual(response['top_broad_areas'][0]['job_count'], 3)

    def test_no_verified_language_is_reported(self):
        """The word is the thing that would be false, not the number."""
        quality = self._quality()

        self.assertNotIn('standardization_coverage_percentage', quality)
        self.assertNotIn('verified_postings_in_period', quality)


class StudentNotificationFeedTests(TestCase):
    """The bell had no handler and a permanently-lit dot. This is the feed."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            email="notif@university.test", password="Strong1!",
            role=User.Role.STUDENT)
        cls.student = Student.objects.create(user=cls.user, student_name="Notified")
        cls.other_user = User.objects.create_user(
            email="notif-other@university.test", password="Strong1!",
            role=User.Role.STUDENT)
        cls.other = Student.objects.create(
            user=cls.other_user, student_name="Somebody Else")
        cls.company_user = User.objects.create_user(
            email="notif@business.test", password="Strong1!", role=User.Role.COMPANY)
        cls.company = Company.objects.create(
            user=cls.company_user, company_name="Notify Ltd")
        cls.job = JobListing.objects.create(
            job_title="Backend Engineer", company=cls.company,
            status=JobListing.Status.ACTIVE)

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def _feed(self):
        response = self.client.get("/api/dashboard/notifications/")
        self.assertEqual(response.status_code, 200, response.data)
        return response.json()["results"]

    def test_an_undecided_application_is_not_announced(self):
        JobApplication.objects.create(student=self.student, job=self.job)

        self.assertEqual(self._feed(), [])

    def test_a_decided_application_appears(self):
        JobApplication.objects.create(
            student=self.student, job=self.job,
            status=JobApplication.Status.SHORTLISTED,
            status_changed_at=timezone.now())

        feed = self._feed()

        self.assertEqual(len(feed), 1)
        self.assertEqual(feed[0]["kind"], "APPLICATION")
        self.assertIn("shortlisted", feed[0]["title"].lower())
        self.assertIn("Backend Engineer", feed[0]["detail"])

    def test_another_students_events_are_never_returned(self):
        JobApplication.objects.create(
            student=self.other, job=self.job,
            status=JobApplication.Status.ACCEPTED,
            status_changed_at=timezone.now())

        self.assertEqual(self._feed(), [])

    def test_a_certificate_decision_appears_with_its_student_message(self):
        from resources.models import Certificate, CertificateSkillEvidence

        skill = Skill.objects.create(skill_name="Notified Skill")
        certificate = Certificate.objects.create(
            student=self.student, certificate_name="Notified Skill course",
            verified_status=Certificate.VerifiedStatus.REJECTED,
            rejection_reason="NAME_MISMATCH",
            verified_at=timezone.now())
        CertificateSkillEvidence.objects.create(
            certificate=certificate, skill=skill,
            claimed_level="INTERMEDIATE",
            review_status=CertificateSkillEvidence.ReviewStatus.REJECTED)

        feed = self._feed()

        self.assertEqual(feed[0]["kind"], "CERTIFICATE")
        self.assertIn("not approved", feed[0]["title"].lower())
        self.assertTrue(feed[0]["detail"])

    def test_internal_verification_notes_never_reach_the_feed(self):
        from resources.models import Certificate, CertificateSkillEvidence

        skill = Skill.objects.create(skill_name="Private Notes Skill")
        certificate = Certificate.objects.create(
            student=self.student, certificate_name="Private Notes course",
            verified_status=Certificate.VerifiedStatus.REJECTED,
            rejection_reason="SUSPECTED_INVALID_DOCUMENT",
            verification_notes="Looks forged, escalate to registrar",
            verified_at=timezone.now())
        CertificateSkillEvidence.objects.create(
            certificate=certificate, skill=skill, claimed_level="INTERMEDIATE",
            review_status=CertificateSkillEvidence.ReviewStatus.REJECTED)

        self.assertNotIn("escalate to registrar", str(self._feed()))

    def test_a_reviewed_transcript_appears(self):
        from resources.models import TranscriptUpload

        TranscriptUpload.objects.create(
            student=self.student,
            verification_status=TranscriptUpload.VerificationStatus.MANUALLY_VERIFIED,
            skills_added=3,
            reviewed_at=timezone.now())

        feed = self._feed()

        self.assertEqual(feed[0]["kind"], "TRANSCRIPT")
        self.assertIn("3", feed[0]["detail"])

    def test_announcements_appear(self):
        admin_user = User.objects.create_user(
            email="notif@admin.test", password="Strong1!", role=User.Role.ADMIN, is_staff=True)
        admin = AdminProfile.objects.create(user=admin_user, admin_name="Poster")
        Announcement.objects.create(
            admin=admin, title="Career fair on Friday", message="Come along")

        feed = self._feed()

        self.assertEqual(feed[0]["kind"], "ANNOUNCEMENT")
        self.assertEqual(feed[0]["title"], "Career fair on Friday")

    def test_events_are_newest_first(self):
        from resources.models import Certificate, CertificateSkillEvidence

        skill = Skill.objects.create(skill_name="Order Skill")
        certificate = Certificate.objects.create(
            student=self.student, certificate_name="Order Skill course",
            verified_status=Certificate.VerifiedStatus.APPROVED,
            verified_at=timezone.now() - timedelta(days=3))
        CertificateSkillEvidence.objects.create(
            certificate=certificate, skill=skill,
            claimed_level="INTERMEDIATE", approved_level="INTERMEDIATE",
            review_status=CertificateSkillEvidence.ReviewStatus.APPROVED)
        JobApplication.objects.create(
            student=self.student, job=self.job,
            status=JobApplication.Status.ACCEPTED,
            status_changed_at=timezone.now())

        feed = self._feed()

        self.assertEqual([event["kind"] for event in feed],
                         ["APPLICATION", "CERTIFICATE"])

    def test_a_company_cannot_read_the_student_feed(self):
        self.client.force_authenticate(self.company_user)

        response = self.client.get("/api/dashboard/notifications/")

        self.assertEqual(response.status_code, 403)

    def test_an_unauthenticated_visitor_cannot_read_it(self):
        self.client.force_authenticate(None)

        response = self.client.get("/api/dashboard/notifications/")

        self.assertIn(response.status_code, (401, 403))


class ApplicationStatusStampTests(TestCase):
    """status_changed_at must record a change, not a save."""

    @classmethod
    def setUpTestData(cls):
        cls.student_user = User.objects.create_user(
            email="stamp@university.test", password="Strong1!", role=User.Role.STUDENT)
        cls.student = Student.objects.create(
            user=cls.student_user, student_name="Stamped")
        cls.company_user = User.objects.create_user(
            email="stamp@business.test", password="Strong1!", role=User.Role.COMPANY)
        cls.company = Company.objects.create(
            user=cls.company_user, company_name="Stamp Ltd")
        cls.job = JobListing.objects.create(
            job_title="Backend Engineer", company=cls.company,
            status=JobListing.Status.ACTIVE)

    def setUp(self):
        self.application = JobApplication.objects.create(
            student=self.student, job=self.job)
        self.client = APIClient()
        self.client.force_authenticate(self.company_user)

    def _set(self, new_status):
        return self.client.patch(
            f"/api/job-listings/applications/{self.application.pk}/status/",
            {"status": new_status}, format="json")

    def test_a_status_change_is_stamped(self):
        self._set("SHORTLISTED")

        self.application.refresh_from_db()
        self.assertIsNotNone(self.application.status_changed_at)

    def test_re_saving_the_same_status_does_not_resurface_it(self):
        self._set("SHORTLISTED")
        self.application.refresh_from_db()
        first = self.application.status_changed_at

        self._set("SHORTLISTED")

        self.application.refresh_from_db()
        self.assertEqual(self.application.status_changed_at, first)


class ProficiencyAwareSkillGapTests(TestCase):
    """Holding a skill is not the same as being ready for it.

    The gap used to count a skill as matched the moment the student owned it
    at any level, so a student with Beginner Python against an Advanced market
    requirement read as a full match and was told nothing about the distance
    they still had to travel.
    """

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            email='prof@university.test', password='Strong1!',
            role=User.Role.STUDENT)
        cls.student = Student.objects.create(user=cls.user, student_name='P')

        cls.role = MarketRole.objects.create(
            name='Data Analyst', broad_area='Data & AI')

        cls.python = Skill.objects.create(skill_name='Python', skill_category='Technical')
        cls.sql = Skill.objects.create(skill_name='SQL', skill_category='Technical')
        cls.docker = Skill.objects.create(skill_name='Docker', skill_category='Technical')

        # Python: mostly Advanced. SQL: mostly Intermediate. Docker: Beginner.
        for index in range(6):
            listing = JobListing.objects.create(
                job_title=f'Data Analyst {index}',
                market_role=cls.role,
                classification_method='EXACT_MARKET_ROLE',
                source_type=JobListing.SourceType.SCRAPED,
                source_url=f'https://example.test/prof/{index}')
            JobSkill.objects.create(
                job=listing, skill=cls.python,
                required_level='ADVANCED' if index >= 2 else 'INTERMEDIATE')
            JobSkill.objects.create(
                job=listing, skill=cls.sql, required_level='INTERMEDIATE')
            JobSkill.objects.create(
                job=listing, skill=cls.docker, required_level='BEGINNER')

        StudentTargetRole.objects.create(student=cls.student, market_role=cls.role)

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def hold(self, skill, level):
        StudentSkill.objects.update_or_create(
            student=self.student, skill=skill,
            defaults={'skill_level': level})

    def rows(self):
        data = self.client.get('/api/dashboard/skill-gap/').data
        by_skill = {row['skill']: row
                    for row in data['matched_skills'] + data['missing_skills']}
        return data, by_skill

    def test_the_three_readiness_states(self):
        self.hold(self.python, 'INTERMEDIATE')   # required ADVANCED
        self.hold(self.sql, 'ADVANCED')          # required INTERMEDIATE
        # Docker not held at all.

        _data, rows = self.rows()

        self.assertEqual(rows['Python']['readiness_status'], 'DEVELOPING')
        self.assertEqual(rows['SQL']['readiness_status'], 'MATCHED')
        self.assertEqual(rows['Docker']['readiness_status'], 'MISSING')

    def test_each_row_reports_both_levels(self):
        self.hold(self.python, 'INTERMEDIATE')

        _data, rows = self.rows()

        self.assertEqual(rows['Python']['required_level'], 'ADVANCED')
        self.assertEqual(rows['Python']['student_level'], 'INTERMEDIATE')
        self.assertIsNone(rows['Docker']['student_level'])

    def test_the_required_level_is_the_most_common_not_the_highest(self):
        """One Advanced posting among many Intermediate ones does not make
        Advanced the market requirement."""
        _data, rows = self.rows()

        self.assertEqual(rows['SQL']['required_level'], 'INTERMEDIATE')
        self.assertEqual(rows['SQL']['level_distribution'], {'INTERMEDIATE': 6})

    def test_the_distribution_is_returned_so_the_figure_can_be_checked(self):
        _data, rows = self.rows()

        self.assertEqual(rows['Python']['level_distribution'],
                         {'INTERMEDIATE': 2, 'ADVANCED': 4})

    def test_a_developing_skill_is_both_held_and_still_a_gap(self):
        self.hold(self.python, 'BEGINNER')

        data, _rows = self.rows()

        self.assertIn('Python', [row['skill'] for row in data['matched_skills']])
        self.assertIn('Python', [row['skill'] for row in data['missing_skills']])

    def test_match_percentage_uses_the_proficiency_formula(self):
        """min(student, required) / required, summed -- the same formula the
        job recommendations use, so the two numbers are comparable."""
        self.hold(self.python, 'INTERMEDIATE')   # 2 of 3
        self.hold(self.sql, 'ADVANCED')          # 2 of 2 (capped)
        self.hold(self.docker, 'BEGINNER')       # 1 of 1

        data, _rows = self.rows()

        # achieved 2+2+1 = 5, required 3+2+1 = 6
        self.assertEqual(data['match_percentage'], round(5 / 6 * 100))

    def test_a_student_holding_nothing_scores_zero(self):
        data, _rows = self.rows()

        self.assertEqual(data['match_percentage'], 0)

    def test_meeting_every_requirement_scores_one_hundred(self):
        self.hold(self.python, 'ADVANCED')
        self.hold(self.sql, 'INTERMEDIATE')
        self.hold(self.docker, 'BEGINNER')

        data, _rows = self.rows()

        self.assertEqual(data['match_percentage'], 100)

    def test_exceeding_a_requirement_does_not_score_above_one_hundred(self):
        self.hold(self.python, 'ADVANCED')
        self.hold(self.sql, 'ADVANCED')
        self.hold(self.docker, 'ADVANCED')

        data, _rows = self.rows()

        self.assertEqual(data['match_percentage'], 100)

    def test_the_gap_and_the_job_match_agree(self):
        """Both sides of the platform must weigh a level the same way, or the
        student sees two incomparable percentages for the same skills."""
        from job_listings.matching import match_score, student_skill_levels

        self.hold(self.python, 'INTERMEDIATE')
        self.hold(self.sql, 'ADVANCED')
        self.hold(self.docker, 'BEGINNER')

        # Named explicitly rather than taken from .first(): the default
        # ordering is newest-first, so "the first advert" is not the one this
        # test means. This advert asks Intermediate Python, where the role as
        # a whole asks Advanced -- the formula is shared even though the
        # requirement differs.
        listing = (JobListing.objects
                   .filter(source_url='https://example.test/prof/0')
                   .prefetch_related('job_skills')
                   .get())
        job_percentage = match_score(listing, student_skill_levels(self.student))

        self.assertEqual(job_percentage, 100)
        data, _rows = self.rows()
        self.assertLess(data['match_percentage'], 100)


class LiveMarketScopeTests(TestCase):
    """The skill gap measures against adverts a student can still apply to.

    A posting JobStreet dropped last quarter describes a vacancy that has been
    filled. Letting it set the requirement tells a student to chase demand
    that no longer exists.
    """

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            email='live@university.test', password='Strong1!',
            role=User.Role.STUDENT)
        cls.student = Student.objects.create(user=cls.user, student_name='L')

        cls.role = MarketRole.objects.create(
            name='Data Analyst', broad_area='Data & AI')
        cls.python = Skill.objects.create(skill_name='Python',
                                          skill_category='Technical')
        cls.cobol = Skill.objects.create(skill_name='COBOL',
                                         skill_category='Technical')

        # Six open adverts asking for Python.
        for index in range(6):
            listing = JobListing.objects.create(
                job_title=f'Data Analyst {index}',
                market_role=cls.role,
                classification_method='EXACT_MARKET_ROLE',
                status=JobListing.Status.ACTIVE,
                source_type=JobListing.SourceType.SCRAPED,
                source_url=f'https://example.test/live/{index}')
            JobSkill.objects.create(job=listing, skill=cls.python)

        # Ten lapsed adverts asking for COBOL. Numerous enough to dominate any
        # ranking that counted them.
        for index in range(10):
            listing = JobListing.objects.create(
                job_title=f'Legacy Data Analyst {index}',
                market_role=cls.role,
                classification_method='EXACT_MARKET_ROLE',
                status=JobListing.Status.CLOSED,
                source_type=JobListing.SourceType.SCRAPED,
                source_url=f'https://example.test/closed/{index}')
            JobSkill.objects.create(job=listing, skill=cls.cobol)

        StudentTargetRole.objects.create(student=cls.student, market_role=cls.role)

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_the_gap_ignores_closed_adverts(self):
        data = self.client.get('/api/dashboard/skill-gap/').data

        skills = [row['skill'] for row in data['missing_skills']]
        self.assertIn('Python', skills)
        self.assertNotIn('COBOL', skills,
                         'a skill demanded only by lapsed adverts is not a gap')

    def test_the_gap_counts_only_open_adverts(self):
        data = self.client.get('/api/dashboard/skill-gap/').data

        self.assertEqual(data['total_listings'], 6)
        self.assertEqual(data['data_quality']['role_listing_count'], 6)

    def test_closing_every_advert_takes_the_role_below_the_floor(self):
        JobListing.objects.filter(market_role=self.role).update(
            status=JobListing.Status.CLOSED)

        data = self.client.get('/api/dashboard/skill-gap/').data

        self.assertEqual(data['scope'], 'MARKET')
        self.assertEqual(data['data_quality']['role_listing_count'], 0)

    def test_the_scope_selector_counts_only_open_adverts(self):
        response = self.client.get('/api/dashboard/skill-gap/market-roles/')

        roles = [role for area in response.data['results']
                 for role in area['roles']]
        self.assertEqual(roles, [{'id': self.role.id, 'name': 'Data Analyst',
                                  'listing_count': 6}])
        self.assertEqual(response.data['coverage']['scraped_total'], 6)

    def test_the_picker_counts_only_open_adverts(self):
        """The same number must mean the same thing on both screens: a picker
        promising 16 jobs for a role the analysis then calls unanalysable is
        two answers to one question."""
        data = self.client.get('/api/scrape-jobs/market-roles/').json()

        by_name = {r['name']: r for area in data['results'] for r in area['roles']}
        self.assertEqual(by_name['Data Analyst']['advert_count'], 6)
        self.assertTrue(by_name['Data Analyst']['analysable'])

    def test_the_role_profile_counts_only_open_adverts(self):
        response = self.client.get(
            '/api/dashboard/market-role/?role=Data%20Analyst')

        self.assertEqual(response.data['listing_count'], 6)

    def test_the_trend_keeps_the_closed_months_but_says_which_is_which(self):
        """A 12-month trend needs the closed postings or there is no trend.
        The two totals are reported separately rather than conflated -- that
        conflation is what put "486 postings" beside a jobs page listing 278."""
        response = self.client.get('/api/dashboard/market-demand/')

        self.assertEqual(response.data['total_postings'], 6)
        self.assertEqual(response.data['total_postings_in_period'], 16)
        self.assertEqual(
            response.data['data_quality']['live_market_postings'], 6)
        self.assertEqual(
            response.data['data_quality']['market_postings_in_period'], 16)


class DemandChangeHonestyTests(TestCase):
    """The change figure reports demand, or it reports nothing.

    A month with no scrape run is not a month with no demand, and a month
    scraped three times is not busier than one scraped once. Conflating those
    produced a "+880.9% three-month change" from a chart that was drawing the
    collection schedule.
    """

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            email='trend@university.test', password='Strong1!',
            role=User.Role.STUDENT)
        cls.student = Student.objects.create(user=cls.user, student_name='T')

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.this_month = timezone.localdate().replace(day=1)

    def run_scrape(self, month, times=1):
        """Record ``times`` successful scrape runs dated inside ``month``."""
        from job_listings.models import ScrapeLog

        when = timezone.make_aware(datetime.combine(month, datetime.min.time()))
        for _ in range(times):
            log = ScrapeLog.objects.create(status=ScrapeLog.Status.SUCCESS)
            # started_at is auto_now_add, so it has to be set after the fact.
            ScrapeLog.objects.filter(pk=log.pk).update(started_at=when)

    def adverts(self, month, count):
        for index in range(count):
            JobListing.objects.create(
                job_title=f'Engineer {month} {index}',
                source_type=JobListing.SourceType.SCRAPED,
                status=JobListing.Status.ACTIVE,
                source_url=f'https://example.test/{month}-{index}',
                posted_date=month)

    def demand(self):
        return self.client.get('/api/dashboard/market-demand/').data

    def test_an_uncollected_month_is_a_gap_not_a_zero(self):
        """The line breaks rather than plunging to the floor."""
        self.run_scrape(shift_month(self.this_month, -2))
        self.adverts(shift_month(self.this_month, -2), 5)

        series = {row['label']: row for row in self.demand()['series']}
        collected = [row for row in series.values() if row['observed']]
        uncollected = [row for row in series.values() if not row['observed']]

        self.assertEqual(len(collected), 1)
        self.assertTrue(all(row['job_count'] is None for row in uncollected),
                        'an uncollected month must be null, never 0')

    def test_uneven_collection_withholds_the_figure(self):
        """Three runs one month and one the next is our schedule, not demand."""
        earlier, recent = (shift_month(self.this_month, -2),
                           shift_month(self.this_month, -1))
        self.run_scrape(earlier, times=1)
        self.run_scrape(recent, times=3)
        self.adverts(earlier, 5)
        self.adverts(recent, 200)

        data = self.demand()

        self.assertIsNone(data['demand_change_percentage'])
        self.assertEqual(data['change_basis'], 'UNEVEN_COLLECTION')

    def test_equal_collection_reports_the_change(self):
        earlier, recent = (shift_month(self.this_month, -2),
                           shift_month(self.this_month, -1))
        self.run_scrape(earlier)
        self.run_scrape(recent)
        self.adverts(earlier, 10)
        self.adverts(recent, 15)

        data = self.demand()

        self.assertEqual(data['change_basis'], 'MONTH_ON_MONTH')
        self.assertEqual(data['demand_change_percentage'], 50.0)

    def test_the_month_in_progress_is_never_compared(self):
        """A part-month always looks like a crash against a full one."""
        earlier = shift_month(self.this_month, -1)
        self.run_scrape(earlier)
        self.run_scrape(self.this_month)
        self.adverts(earlier, 100)
        self.adverts(self.this_month, 3)

        data = self.demand()

        self.assertIsNone(data['demand_change_percentage'])
        self.assertEqual(data['change_basis'], 'SINGLE_MONTH')

    def test_the_month_in_progress_is_flagged_in_the_series(self):
        self.run_scrape(self.this_month)
        self.adverts(self.this_month, 3)

        current = next(row for row in self.demand()['series']
                       if row['month'] == self.this_month.isoformat())

        self.assertTrue(current['partial'])

    def test_one_month_of_history_reports_no_change(self):
        self.run_scrape(shift_month(self.this_month, -1))
        self.adverts(shift_month(self.this_month, -1), 10)

        data = self.demand()

        self.assertIsNone(data['demand_change_percentage'])
        self.assertEqual(data['change_basis'], 'SINGLE_MONTH')

    def test_no_collection_at_all_reports_no_change(self):
        data = self.demand()

        self.assertIsNone(data['demand_change_percentage'])
        self.assertEqual(data['change_basis'], 'NOT_ENOUGH_COLLECTED')
