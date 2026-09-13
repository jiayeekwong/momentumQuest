from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from rest_framework.test import APIClient

from job_listings.models import JobListing, MarketRoleCandidate
from .market_role_classifier import (
    METHOD_ALIAS, METHOD_AMBIGUOUS, METHOD_EXACT, METHOD_JD,
    METHOD_LEVEL_ALIAS, METHOD_LEVEL_ROLE, METHOD_SEGMENT, METHOD_UNCLASSIFIED,
    build_index, classify_listing, classify_title,
)
from .catalogue import (
    DATA_DIR, FILES, database_snapshot, file_snapshot, snapshot_digest,
)
from .models import (JobCategory, JobTitle, MarketRole, MarketRoleAlias,
                     Skill, SkillAlias, SkillRelationship, SkillSource)
from .title_normalizer import (
    expand_abbreviations,
    extract_career_level,
    normalize_occupation_label,
    normalize_title,
    strip_recruiter_noise,
    title_segments,
    title_without_career_level,
)
from .services import (
    UNCATEGORIZED_CATEGORY,
    canonical_source_url,
    classify_job_category,
    save_scraped_job,
)


class TitleCleaningTests(TestCase):
    """The pure text helpers that feed the matcher."""

    def test_strips_bracketed_asides(self):
        self.assertEqual(
            strip_recruiter_noise('Software Engineer (ERP)'), 'Software Engineer')
        self.assertEqual(
            strip_recruiter_noise('Database Administrator (DBA)'), 'Database Administrator')

    def test_strips_recruiter_marketing(self):
        self.assertEqual(
            strip_recruiter_noise('IT Support Executive Fresh Grad Welcomed'),
            'IT Support Executive')
        self.assertEqual(
            strip_recruiter_noise('Desktop Engineer Based In Singapore'), 'Desktop Engineer')

    def test_expands_abbreviations_to_full_wording(self):
        # Only the abbreviation is rewritten; surrounding case is left alone
        # because normalize_occupation_label casefolds downstream.
        self.assertEqual(expand_abbreviations('IT Executive'), 'information technology Executive')
        self.assertEqual(expand_abbreviations('QA Engineer'), 'quality assurance Engineer')

    def test_expansion_respects_word_boundaries(self):
        """'it' inside a word must not be rewritten."""
        self.assertEqual(expand_abbreviations('Security Analyst'), 'Security Analyst')
        self.assertEqual(expand_abbreviations('Digital Designer'), 'Digital Designer')

    def test_splits_multi_role_titles(self):
        self.assertEqual(
            title_segments('Web Developer / Full Stack Developer'),
            ['Web Developer', 'Full Stack Developer'])

    def test_does_not_split_on_and(self):
        """'and' joins qualifiers more often than roles."""
        self.assertEqual(
            title_segments('Research and Development Engineer'),
            ['Research and Development Engineer'])

    def test_short_fragments_are_dropped(self):
        self.assertNotIn('IT', title_segments('IT / Software Engineer'))



class CanonicalSourceUrlTests(TestCase):
    """JobStreet's per-session tracking must not defeat deduplication."""

    def test_tracking_fragment_and_params_are_dropped(self):
        self.assertEqual(
            canonical_source_url(
                "https://my.jobstreet.com/job/92352106"
                "?type=standard&ref=search-standalone&origin=cardTitle"
                "#sol=d1d888ef46ea3dc5ed15f9178cfec5eace5820c9"),
            "https://my.jobstreet.com/job/92352106",
        )

    def test_two_scrapes_of_one_advert_produce_one_listing(self):
        first = {
            "job_title": "Software Engineer",
            "source_url": "https://my.jobstreet.com/job/1?ref=a#sol=aaa",
            "company_name": "Acme",
        }
        second = dict(first, source_url="https://my.jobstreet.com/job/1?ref=b#sol=bbb")

        save_scraped_job(first)
        save_scraped_job(second)

        self.assertEqual(
            JobListing.objects.filter(source_type="SCRAPED").count(), 1)

    def test_different_adverts_stay_separate(self):
        save_scraped_job({"job_title": "A", "source_url": "https://my.jobstreet.com/job/1"})
        save_scraped_job({"job_title": "B", "source_url": "https://my.jobstreet.com/job/2"})

        self.assertEqual(
            JobListing.objects.filter(source_type="SCRAPED").count(), 2)

    def test_a_malformed_url_is_left_alone(self):
        self.assertEqual(canonical_source_url("not-a-url"), "not-a-url")
        self.assertEqual(canonical_source_url(""), "")


class JobCategoryClassificationTests(TestCase):
    """Regression cover for classify_job_category.

    Every case below was mis-filed by the substring version this replaced.
    """

    def assertCategory(self, title, expected):
        self.assertEqual(classify_job_category(title), expected, msg=title)

    def test_substrings_no_longer_match_inside_words(self):
        # "ui" inside recr(ui)tment / b(ui)ld / g(ui)dewire / circ(ui)t / s(ui)te
        # used to file all of these as UI/UX Designer.
        for title in [
            "IT Recruitment Consultant", "Build Engineer",
            "Circuit Design Engineer", "Suite Implementation Consultant",
        ]:
            self.assertNotEqual(classify_job_category(title), "UI/UX Designer", msg=title)

        # "ios" inside k(ios)k / stud(ios) / B(IOS) used to mean Mobile.
        for title in ["Kiosk Software Engineer", "Digital Studios Developer"]:
            self.assertNotEqual(classify_job_category(title), "Mobile App Developer", msg=title)

        # "react" inside (react)or used to mean Web.
        self.assertNotEqual(
            classify_job_category("Senior Reactor Systems Analyst"), "Web Developer")

    def test_unmatched_titles_land_in_the_fallback_not_software_engineer(self):
        for title in [
            "IT Support Executive", "Project Manager (IT)", "Scrum Master",
            "ERP Consultant", "Salesforce Administrator", "Systems Analyst",
        ]:
            self.assertCategory(title, UNCATEGORIZED_CATEGORY)

    def test_security_titles_reach_cybersecurity(self):
        for title in [
            "Security Engineer", "SOC Engineer", "Information Security Officer",
            "Penetration Tester", "Cyber Security Analyst",
        ]:
            self.assertCategory(title, "Cybersecurity")

    def test_security_wins_over_network_and_qa(self):
        self.assertCategory("Network Security Engineer", "Cybersecurity")
        self.assertCategory("Penetration Tester", "Cybersecurity")

    def test_mobile_is_tested_before_web(self):
        self.assertCategory("React Native Mobile Developer", "Mobile App Developer")

    def test_data_and_ai_titles_are_separated(self):
        self.assertCategory("Data Engineer", "Data Analyst")
        self.assertCategory("Business Intelligence Developer", "Data Analyst")
        self.assertCategory("ML Engineer", "AI/ML Engineer")
        self.assertCategory("Machine Learning Scientist", "AI/ML Engineer")

    def test_cloud_titles_reach_devops(self):
        self.assertCategory("Cloud Architect", "DevOps Engineer")
        self.assertCategory("Site Reliability Engineer", "DevOps Engineer")

    def test_established_categories_still_resolve(self):
        self.assertCategory("Frontend Developer", "Web Developer")
        self.assertCategory("Full Stack Developer", "Web Developer")
        self.assertCategory("Senior Android Developer", "Mobile App Developer")
        self.assertCategory("Oracle Database Administrator", "Database Administrator")
        self.assertCategory("Software Tester", "QA Tester")
        self.assertCategory("UX Researcher", "UI/UX Designer")
        self.assertCategory("Network Engineer", "Network Engineer")
        self.assertCategory("Software Engineer", "Software Engineer")

    def test_recruiter_noise_does_not_decide_the_category(self):
        # The raw-title version let marketing appended to a title vote.
        self.assertCategory(
            "Data Analyst (Urgent Hiring, Fresh Grad Welcome)", "Data Analyst")

    def test_empty_title_is_not_a_software_engineer(self):
        self.assertCategory("", UNCATEGORIZED_CATEGORY)

    def test_classification_is_deterministic(self):
        title = "Senior Cloud Security Engineer"
        self.assertEqual(
            {classify_job_category(title) for _ in range(5)},
            {classify_job_category(title)},
        )


class RecategorizeCommandTests(TestCase):
    """The backfill must repair rows written under the old substring rules."""

    def setUp(self):
        self.wrong = JobCategory.objects.create(category_name="UI/UX Designer")
        self.listing = JobListing.objects.create(
            job_title="IT Recruitment Consultant",
            category=self.wrong,
            source_type=JobListing.SourceType.SCRAPED,
            source_url="https://example.test/recruiter",
        )
        self.title = JobTitle.objects.create(
            title_name="IT Recruitment Consultant", category=self.wrong)

    def test_mis_filed_listing_and_title_are_both_corrected(self):
        call_command("recategorize_job_listings", verbosity=0)

        self.listing.refresh_from_db()
        self.title.refresh_from_db()
        self.assertEqual(self.listing.category.category_name, UNCATEGORIZED_CATEGORY)
        self.assertEqual(self.title.category.category_name, UNCATEGORIZED_CATEGORY)

    def test_dry_run_writes_nothing(self):
        call_command("recategorize_job_listings", "--dry-run", verbosity=0)

        self.listing.refresh_from_db()
        self.title.refresh_from_db()
        self.assertEqual(self.listing.category.category_name, "UI/UX Designer")
        self.assertEqual(self.title.category.category_name, "UI/UX Designer")

    def test_rerunning_is_idempotent(self):
        call_command("recategorize_job_listings", verbosity=0)
        out = StringIO()
        call_command("recategorize_job_listings", stdout=out)

        self.assertIn("0 re-classified", out.getvalue())


class CareerLevelTests(TestCase):
    """Career level is separated from occupational function, or not at all.

    The regression these guard is real and was shipped: the previous stripper
    treated "manager", "head", "lead", "principal" and "director" as levels,
    so "IT Manager / Assistant Manager" reduced to "IT Assistant" and matched
    a support role. A word that names what the job *is* is never removable.
    """

    def test_genuine_levels_are_removed(self):
        for raw, expected in (
            ("Senior Data Engineer", "data engineer"),
            ("Junior Software Engineer", "software engineer"),
            ("Graduate AI Engineer", "artificial intelligence engineer"),
            ("Data Analyst Intern", "data analyst"),
            ("Mid-Level Backend Developer", "backend developer"),
        ):
            with self.subTest(raw=raw):
                self.assertEqual(title_without_career_level(raw), expected)

    def test_the_level_itself_is_reported(self):
        self.assertEqual(extract_career_level("Senior Data Engineer"), "SENIOR")
        self.assertEqual(extract_career_level("Junior Software Engineer"), "JUNIOR")
        self.assertEqual(extract_career_level("Data Analyst"), "")

    def test_a_level_is_read_even_from_recruiter_marketing(self):
        """"Fresh Grad Welcomed" is the advert's only statement of level."""
        self.assertEqual(
            extract_career_level("Data Center Engineer (Fresh Grad Welcomed!)"),
            "GRADUATE")

    def test_function_words_are_never_removed(self):
        for word in ("Manager", "Head", "Lead", "Architect", "Administrator",
                     "Consultant", "Specialist", "Support", "Officer",
                     "Engineer", "Analyst", "Developer", "Scientist"):
            raw = f"IT {word}"
            with self.subTest(word=word):
                self.assertIn(word.lower(), title_without_career_level(raw))

    def test_it_manager_is_not_reduced_to_an_assistant(self):
        """The shipped bug, kept as a test."""
        reduced = title_without_career_level("IT Manager / Assistant Manager")

        self.assertIn("manager", reduced)
        self.assertNotEqual(reduced, "information technology assistant")

    def test_associate_is_only_removed_when_something_survives(self):
        self.assertEqual(
            title_without_career_level("Associate Software Engineer",
                                       strip_associate=True),
            "software engineer")
        # "Associate Engineer" would leave "engineer", which names no career.
        self.assertEqual(
            title_without_career_level("Associate Engineer",
                                       strip_associate=True),
            "associate engineer")

    def test_associate_is_kept_by_default(self):
        self.assertEqual(
            title_without_career_level("Associate Software Engineer"),
            "associate software engineer")


class TitleNormalizationTests(TestCase):
    """Formatting differences collapse; meaning never does."""

    def test_spelling_variants_normalize_together(self):
        for raw in ("Front-End Developer", "Front End Developer",
                    "FRONTEND DEVELOPER", "frontend developer"):
            with self.subTest(raw=raw):
                self.assertEqual(normalize_title(raw), "frontend developer")

    def test_advert_metadata_is_stripped(self):
        for raw in ("Software Engineer (Remote)",
                    "Software Engineer | RM4,000 - RM5,000",
                    "Software Engineer - Penang & KL",
                    "Software Engineer (Singapore-based)",
                    "Urgently Hiring - Software Engineer"):
            with self.subTest(raw=raw):
                self.assertEqual(normalize_title(raw), "software engineer")

    def test_normalization_keeps_meaningful_words(self):
        self.assertEqual(normalize_title("Senior Front-End Engineer (Remote)"),
                         "senior frontend engineer")


class MarketRoleClassifierTests(TestCase):
    """Title-tier classification: exact, alias, level-normalized, segment."""

    @classmethod
    def setUpTestData(cls):
        cls.software = MarketRole.objects.create(
            name="Software Engineer", broad_area="Software & Applications")
        cls.frontend = MarketRole.objects.create(
            name="Frontend Developer", broad_area="Software & Applications")
        cls.backend = MarketRole.objects.create(
            name="Backend Developer", broad_area="Software & Applications")
        cls.fullstack = MarketRole.objects.create(
            name="Full Stack Developer", broad_area="Software & Applications")
        cls.data_engineer = MarketRole.objects.create(
            name="Data Engineer", broad_area="Data & AI")
        cls.support = MarketRole.objects.create(
            name="IT Support", broad_area="Operations & Support")

        for title, role in (
            ("software developer", cls.software),
            ("frontend engineer", cls.frontend),
            ("backend engineer", cls.backend),
            ("information technology support engineer", cls.support),
        ):
            MarketRoleAlias.objects.create(normalized_title=title,
                                           market_role=role)

    def setUp(self):
        self.index = build_index()

    def classify(self, title):
        return classify_title(title, self.index)

    # -- the regressions the specification names ---------------------------

    def test_required_title_to_market_role_mappings(self):
        for raw, expected in (
            ("Senior Software Engineer", "Software Engineer"),
            ("Senior Data Engineer", "Data Engineer"),
            ("Frontend Engineer", "Frontend Developer"),
            ("Backend Engineer", "Backend Developer"),
            ("Senior Full Stack Developer", "Full Stack Developer"),
        ):
            with self.subTest(raw=raw):
                result = self.classify(raw)
                self.assertIsNotNone(result.market_role, raw)
                self.assertEqual(result.market_role.name, expected)

    def test_it_manager_is_not_classified_as_a_support_role(self):
        """The destructive-reduction regression, at the classifier level."""
        result = self.classify("IT Manager / Assistant Manager")

        self.assertIsNone(result.market_role)
        self.assertNotEqual(result.method, METHOD_EXACT)

    # -- tiers --------------------------------------------------------------

    def test_exact_market_role_name(self):
        result = self.classify("Software Engineer")

        self.assertEqual(result.market_role, self.software)
        self.assertEqual(result.method, METHOD_EXACT)

    def test_reviewed_alias(self):
        result = self.classify("Frontend Engineer")

        self.assertEqual(result.market_role, self.frontend)
        self.assertEqual(result.method, METHOD_ALIAS)
        self.assertEqual(result.matched_alias, "frontend engineer")

    def test_career_level_normalized_role(self):
        result = self.classify("Senior Software Engineer")

        self.assertEqual(result.market_role, self.software)
        self.assertEqual(result.method, METHOD_LEVEL_ROLE)

    def test_career_level_normalized_alias(self):
        result = self.classify("Junior Frontend Engineer")

        self.assertEqual(result.market_role, self.frontend)
        self.assertEqual(result.method, METHOD_LEVEL_ALIAS)

    def test_reviewed_segment_of_a_compound_title(self):
        result = self.classify("Assistant Manager, Frontend Engineer")

        self.assertEqual(result.market_role, self.frontend)
        self.assertEqual(result.method, METHOD_SEGMENT)

    def test_recruiter_noise_does_not_defeat_a_match(self):
        result = self.classify(
            "Urgently Hiring - Software Developer (Remote) | RM6,000")

        self.assertEqual(result.market_role, self.software)

    # -- what must not classify --------------------------------------------

    def test_a_title_naming_two_careers_is_ambiguous(self):
        result = self.classify("Frontend Engineer / Backend Engineer")

        self.assertIsNone(result.market_role)
        self.assertEqual(result.method, METHOD_AMBIGUOUS)
        self.assertEqual({role.name for role in result.candidates},
                         {"Frontend Developer", "Backend Developer"})

    def test_an_unmapped_title_stays_unclassified(self):
        result = self.classify("Underwater Basket Weaver")

        self.assertIsNone(result.market_role)
        self.assertEqual(result.method, METHOD_UNCLASSIFIED)

    def test_lexical_similarity_alone_never_assigns(self):
        """"Software Support Engineer" shares two words with "Software
        Engineer" and is a different job. Overlap is not evidence."""
        for raw in ("Software Support Engineer", "Data Centre Engineer",
                    "Engineering Manager", "Support Analyst"):
            with self.subTest(raw=raw):
                self.assertIsNone(self.classify(raw).market_role)

    def test_a_broad_department_title_is_held_back(self):
        for raw in ("IT Executive", "Senior IT Executive", "IT Manager",
                    "Technical Executive", "Application Specialist"):
            with self.subTest(raw=raw):
                result = self.classify(raw)
                self.assertIsNone(result.market_role)
                self.assertEqual(result.method, METHOD_AMBIGUOUS)

    def test_an_unreviewed_alias_does_not_classify(self):
        MarketRoleAlias.objects.create(
            normalized_title="web application developer",
            market_role=self.software, reviewed=False)

        result = classify_title("Web Application Developer", build_index())

        self.assertIsNone(result.market_role)

    def test_an_inactive_role_is_not_assigned(self):
        self.frontend.is_active = False
        self.frontend.save(update_fields=["is_active"])

        self.assertIsNone(classify_title("Frontend Developer",
                                         build_index()).market_role)


class JdResolutionTests(TestCase):
    """Advert-level resolution, for titles that name a department not a job."""

    SUPPORT_JD = """
        Responsibilities: provide end-user support to staff across the office.
        Troubleshoot employee laptops and desktops, install software and
        applications, resolve tickets raised through the helpdesk, manage user
        account creation, and carry out hardware maintenance including
        printer servicing.
    """

    NETWORK_JD = """
        Responsibilities: configure routers and switches across all branches,
        firewall management and policy review, monitor network performance,
        maintain the LAN and WAN links, VPN administration and network
        troubleshooting for site connectivity.
    """

    THIN_JD = "We are looking for a motivated team player to join our IT team."

    @classmethod
    def setUpTestData(cls):
        cls.support = MarketRole.objects.create(
            name="IT Support", broad_area="Operations & Support")
        cls.network = MarketRole.objects.create(
            name="Network Engineer", broad_area="Infrastructure & Cloud")
        cls.software = MarketRole.objects.create(
            name="Software Engineer", broad_area="Software & Applications")

    def setUp(self):
        self.index = build_index()

    def classify(self, title, description):
        return classify_listing(title, description, self.index)

    def test_same_title_different_adverts_reach_different_roles(self):
        """The specification's central claim about Malaysian market titles:
        the same Normalized Job Title is not necessarily the same career."""
        support = self.classify("IT Executive", self.SUPPORT_JD)
        network = self.classify("IT Executive", self.NETWORK_JD)

        self.assertEqual(support.market_role, self.support)
        self.assertEqual(network.market_role, self.network)
        self.assertEqual(support.method, METHOD_JD)
        self.assertEqual(network.method, METHOD_JD)

    def test_the_evidence_is_recorded(self):
        result = self.classify("IT Executive", self.SUPPORT_JD)

        self.assertIn("helpdesk", result.evidence)
        self.assertIn("functional responsibilities", result.evidence)

    def test_an_ambiguous_title_without_evidence_stays_ambiguous(self):
        result = self.classify("IT Executive", self.THIN_JD)

        self.assertIsNone(result.market_role)
        self.assertEqual(result.method, METHOD_AMBIGUOUS)

    def test_one_isolated_keyword_is_not_enough(self):
        result = self.classify("IT Executive",
                               "You will occasionally reset a user account.")

        self.assertIsNone(result.market_role)

    def test_technologies_alone_do_not_classify(self):
        """Python is not Data Scientist and AWS is not Cloud Engineer -- the
        same tools appear across most ICT careers, and these same tools later
        become the role's measured skill demand."""
        result = self.classify(
            "IT Executive",
            "Requirements: Python, AWS, Docker, Kubernetes, SQL, Git, Linux.")

        self.assertIsNone(result.market_role)

    def test_an_unmapped_title_is_not_resolved_from_its_description(self):
        """Only a department title earns advert-level resolution. A title that
        says plainly what it is -- "Data Centre Manager" -- must not be
        overruled by whatever its responsibilities happen to mention."""
        result = self.classify("Data Centre Manager", self.SUPPORT_JD)

        self.assertIsNone(result.market_role)
        self.assertEqual(result.method, METHOD_UNCLASSIFIED)

    def test_a_title_naming_two_careers_is_not_broken_by_the_description(self):
        """Two careers in one title is an advert for two jobs. Responsibilities
        favouring one of them do not make it the answer -- the other job is
        still being advertised."""
        result = self.classify("Network Engineer / Software Engineer",
                               self.NETWORK_JD)

        self.assertIsNone(result.market_role)
        self.assertEqual(result.method, METHOD_AMBIGUOUS)

    def test_a_department_word_beside_a_career_does_not_block_the_match(self):
        """"IT Executive" names no career, so it cannot compete with the half
        of the title that does."""
        result = self.classify("IT Executive / Network Engineer", "")

        self.assertEqual(result.market_role, self.network)
        self.assertEqual(result.method, METHOD_SEGMENT)


class MarketRoleLoaderTests(TestCase):
    """The CSV is the source of truth; the command makes the database match."""

    def test_the_shipped_mapping_loads(self):
        call_command("load_market_roles", verbosity=0)

        self.assertGreater(MarketRole.objects.count(), 20)
        self.assertGreater(MarketRoleAlias.objects.count(), 150)
        self.assertTrue(MarketRole.objects.filter(name="Frontend Developer",
                                                  is_active=True).exists())

    def test_every_role_has_a_broad_area(self):
        call_command("load_market_roles", verbosity=0)

        self.assertFalse(MarketRole.objects.filter(broad_area="").exists())

    def test_a_role_name_normalizes_to_its_own_lookup_key(self):
        call_command("load_market_roles", verbosity=0)
        role = MarketRole.objects.get(name="Data Engineer")

        self.assertEqual(role.normalized_name, "data engineer")

    def test_one_title_cannot_mean_two_careers(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "roles.csv"
            path.write_text(
                "market_role,normalized_title,broad_area,mapping_type,notes\n"
                "Data Analyst,data analyst,Data & AI,exact,\n"
                "Data Engineer,data analyst,Data & AI,reviewed_alias,\n",
                encoding="utf-8")

            with self.assertRaises(CommandError) as caught:
                call_command("load_market_roles", "--path", str(path),
                             verbosity=0)

        self.assertIn("mapped to both", str(caught.exception))
        self.assertEqual(MarketRole.objects.count(), 0)

    def test_reloading_is_idempotent(self):
        call_command("load_market_roles", verbosity=0)
        roles, aliases = MarketRole.objects.count(), MarketRoleAlias.objects.count()

        call_command("load_market_roles", verbosity=0)

        self.assertEqual(MarketRole.objects.count(), roles)
        self.assertEqual(MarketRoleAlias.objects.count(), aliases)

    def test_an_alias_is_normalized_on_the_way_in(self):
        role = MarketRole.objects.create(name="Frontend Developer",
                                         broad_area="Software & Applications")
        alias = MarketRoleAlias.objects.create(
            normalized_title="Senior Front-End Engineer (Remote)",
            market_role=role)

        self.assertEqual(alias.normalized_title, "senior frontend engineer")


class ClassifyMarketRolesCommandTests(TestCase):
    """The reclassification pass, which is what the stored fields come from."""

    @classmethod
    def setUpTestData(cls):
        cls.role = MarketRole.objects.create(
            name="Frontend Developer", broad_area="Software & Applications")
        MarketRoleAlias.objects.create(normalized_title="frontend engineer",
                                       market_role=cls.role)
        MarketRole.objects.create(name="Backend Developer",
                                  broad_area="Software & Applications")
        MarketRoleAlias.objects.create(normalized_title="backend engineer",
                                       market_role=MarketRole.objects.get(
                                           name="Backend Developer"))

    def listing(self, title, description="", url=None):
        return JobListing.objects.create(
            job_title=title,
            description=description,
            source_type=JobListing.SourceType.SCRAPED,
            source_url=url or f"https://example.test/{abs(hash(title))}",
        )

    def test_all_three_values_are_stored_separately(self):
        listing = self.listing("Senior Front-End Engineer (Remote)")

        call_command("classify_market_roles", verbosity=0)
        listing.refresh_from_db()

        self.assertEqual(listing.job_title, "Senior Front-End Engineer (Remote)")
        self.assertEqual(listing.normalized_job_title, "senior frontend engineer")
        self.assertEqual(listing.market_role, self.role)
        self.assertEqual(listing.career_level, "SENIOR")
        self.assertEqual(listing.classification_method, METHOD_LEVEL_ALIAS)
        self.assertEqual(listing.matched_alias, "frontend engineer")

    def test_an_unclassifiable_advert_is_left_unclassified(self):
        listing = self.listing("Underwater Basket Weaver")

        call_command("classify_market_roles", verbosity=0)
        listing.refresh_from_db()

        self.assertIsNone(listing.market_role)
        self.assertEqual(listing.classification_method, METHOD_UNCLASSIFIED)

    def test_a_two_career_title_records_candidates_for_review(self):
        listing = self.listing("Frontend Engineer / Backend Engineer")

        call_command("classify_market_roles", verbosity=0)
        listing.refresh_from_db()

        self.assertIsNone(listing.market_role)
        self.assertEqual(listing.classification_method, METHOD_AMBIGUOUS)
        self.assertEqual(
            {c.market_role.name for c in listing.role_candidates.all()},
            {"Frontend Developer", "Backend Developer"})

    def test_rerunning_is_idempotent(self):
        self.listing("Frontend Engineer")
        self.listing("Frontend Engineer / Backend Engineer",
                     url="https://example.test/two")

        call_command("classify_market_roles", verbosity=0)
        first = MarketRoleCandidate.objects.count()
        call_command("classify_market_roles", verbosity=0)

        self.assertEqual(MarketRoleCandidate.objects.count(), first)

    def test_dry_run_writes_nothing(self):
        listing = self.listing("Frontend Engineer")

        call_command("classify_market_roles", "--dry-run", verbosity=0)
        listing.refresh_from_db()

        self.assertIsNone(listing.market_role)

    def test_a_reviewers_decision_survives_a_rerun(self):
        listing = self.listing("Frontend Engineer / Backend Engineer")
        call_command("classify_market_roles", verbosity=0)
        decided = listing.role_candidates.first()
        decided.status = MarketRoleCandidate.Status.REJECTED
        decided.save(update_fields=["status"])

        call_command("classify_market_roles", verbosity=0)
        decided.refresh_from_db()

        self.assertEqual(decided.status, MarketRoleCandidate.Status.REJECTED)


class ScrapeClassifiesOnIngestTests(TestCase):
    """A newly scraped advert is classified as it lands."""

    @classmethod
    def setUpTestData(cls):
        cls.role = MarketRole.objects.create(
            name="Data Engineer", broad_area="Data & AI")

    def test_a_scraped_advert_arrives_classified(self):
        listing, created = save_scraped_job({
            "job_title": "Senior Data Engineer",
            "source_url": "https://example.test/de",
            "description": "Build pipelines.",
        })

        self.assertTrue(created)
        self.assertEqual(listing.market_role, self.role)
        self.assertEqual(listing.career_level, "SENIOR")
        self.assertEqual(listing.normalized_job_title, "senior data engineer")

    def test_the_job_title_row_records_the_role_too(self):
        save_scraped_job({
            "job_title": "Data Engineer",
            "source_url": "https://example.test/de2",
            "description": "",
        })

        self.assertEqual(
            JobTitle.objects.get(title_name="Data Engineer").market_role,
            self.role)


class UnmatchedTitleReportTests(TestCase):
    """Coverage grows by review, so the review list has to be readable."""

    def setUp(self):
        MarketRole.objects.create(name="Data Engineer", broad_area="Data & AI")
        for index, title in enumerate((
                "Quantum Blockchain Evangelist",
                "Senior Quantum Blockchain Evangelist",
                "Data Engineer")):
            JobListing.objects.create(
                job_title=title,
                source_type=JobListing.SourceType.SCRAPED,
                source_url=f"https://example.test/{index}")
        call_command("classify_market_roles", verbosity=0)

    def test_variants_of_one_title_are_one_decision(self):
        out = StringIO()
        call_command("report_unmatched_titles", stdout=out)
        report = out.getvalue()

        self.assertIn("quantum blockchain evangelist", report)
        self.assertIn("2  quantum blockchain evangelist", report)

    def test_a_classified_title_is_not_listed(self):
        out = StringIO()
        call_command("report_unmatched_titles", stdout=out)

        self.assertNotIn("data engineer", out.getvalue().lower().split("e.g.")[0])


class ExtendedSkillCatalogueTests(TestCase):
    """The invariants the MTO merge relies on.

    The merge added 1,853 skills to a catalogue of 186 and staged some of them
    inactive. That only stays safe while "inactive" genuinely means "takes no
    part in extraction" -- these tests are what stop that quietly becoming
    untrue.
    """

    def setUp(self):
        self.live = Skill.objects.create(
            skill_name="Kubernetes",
            catalogue_status=Skill.CatalogueStatus.ACTIVE_INTERNAL)
        self.staged = Skill.objects.create(
            skill_name="Wireshark", is_active=False,
            catalogue_status=Skill.CatalogueStatus.REVIEW_REQUIRED)

    def test_an_inactive_skill_never_matches(self):
        from .skill_extractor import extract_skills_from_text

        names = {s.skill_name for s in extract_skills_from_text(
            "Strong Kubernetes and Wireshark experience required.")}

        self.assertIn("Kubernetes", names)
        self.assertNotIn("Wireshark", names)

    def test_an_inactive_alias_never_matches(self):
        SkillAlias.objects.create(skill=self.live, alias_name="k8s",
                                  source=SkillAlias.Source.MTO,
                                  is_active=False)
        from .skill_extractor import extract_skills_from_text

        names = {s.skill_name for s in extract_skills_from_text(
            "Deep k8s knowledge.")}

        self.assertNotIn("Kubernetes", names)

    def test_activating_the_alias_makes_it_match(self):
        alias = SkillAlias.objects.create(skill=self.live, alias_name="k8s",
                                          source=SkillAlias.Source.MTO,
                                          is_active=False)
        alias.is_active = True
        alias.save(update_fields=["is_active"])
        from .skill_extractor import extract_skills_from_text

        names = {s.skill_name for s in extract_skills_from_text(
            "Deep k8s knowledge.")}

        self.assertIn("Kubernetes", names)

    def test_an_alias_of_an_inactive_skill_never_matches(self):
        """Activating an alias must not resurrect the skill behind it."""
        SkillAlias.objects.create(skill=self.staged, alias_name="packet sniffer",
                                  source=SkillAlias.Source.MTO, is_active=True)
        from .skill_extractor import extract_skills_from_text

        names = {s.skill_name for s in extract_skills_from_text(
            "Experience with a packet sniffer.")}

        self.assertNotIn("Wireshark", names)

    def test_market_active_is_computed_not_asserted(self):
        """An imported skill with no Malaysian advert behind it is a valid
        catalogue entry that is simply not in demand -- and it must not be
        able to claim otherwise."""
        from job_listings.models import JobListing, JobSkill

        self.assertFalse(self.live.market_active)

        job = JobListing.objects.create(job_title="Platform Engineer",
                                        source_type="SCRAPED")
        JobSkill.objects.create(job=job, skill=self.live)

        self.assertTrue(Skill.objects.get(pk=self.live.pk).market_active)

    def test_a_company_posting_does_not_make_a_skill_market_active(self):
        """market_active means the Malaysian scrape asked for it. A company
        posting its own advert is not evidence about the wider market."""
        from job_listings.models import JobListing, JobSkill

        job = JobListing.objects.create(job_title="Platform Engineer",
                                        source_type="COMPANY")
        JobSkill.objects.create(job=job, skill=self.live)

        self.assertFalse(Skill.objects.get(pk=self.live.pk).market_active)


class ImportedAliasPruneTests(TestCase):
    """import_skills owns the curated CSVs and nothing else.

    An unscoped prune would delete every MTO alias on the next monthly run --
    silently, and only visible as a drop in extraction quality weeks later.
    """

    def test_pruning_leaves_imported_aliases_alone(self):
        python = Skill.objects.create(skill_name="Python")
        mto = SkillAlias.objects.create(skill=python, alias_name="python3",
                                        source=SkillAlias.Source.MTO)
        stale = SkillAlias.objects.create(skill=python, alias_name="py-lang",
                                          source=SkillAlias.Source.INTERNAL)

        call_command("import_skills", "--prune-aliases", stdout=StringIO())

        self.assertTrue(SkillAlias.objects.filter(pk=mto.pk).exists())
        self.assertFalse(SkillAlias.objects.filter(pk=stale.pk).exists())


class SkillProvenanceTests(TestCase):
    """One skill, several catalogues -- which is why provenance is a table."""

    def test_a_skill_can_be_vouched_for_by_several_sources(self):
        react = Skill.objects.create(skill_name="React")
        SkillSource.objects.create(skill=react,
                                   source=SkillSource.Source.INTERNAL,
                                   external_label="React")
        SkillSource.objects.create(skill=react, source=SkillSource.Source.MTO,
                                   external_label="React",
                                   source_version="2367527d")

        self.assertEqual(react.sources.count(), 2)

    def test_the_same_source_cannot_claim_the_same_label_twice(self):
        from django.db.utils import IntegrityError

        react = Skill.objects.create(skill_name="React")
        SkillSource.objects.create(skill=react, source=SkillSource.Source.MTO,
                                   external_label="React")

        with self.assertRaises(IntegrityError):
            SkillSource.objects.create(skill=react,
                                       source=SkillSource.Source.MTO,
                                       external_label="React")

    def test_a_relationship_is_not_an_alias(self):
        """Svelte implying JavaScript must not make one match the other."""
        svelte = Skill.objects.create(skill_name="Svelte")
        js = Skill.objects.create(skill_name="JavaScript")
        SkillRelationship.objects.create(
            from_skill=svelte, to_skill=js,
            relationship_type=SkillRelationship.Type.IMPLIES_KNOWING)

        from .skill_extractor import extract_skills_from_text
        names = {s.skill_name for s in extract_skills_from_text(
            "We build with Svelte.")}

        self.assertEqual(names, {"Svelte"})


class NormalizationCollisionTests(TestCase):
    """Matching happens on normalised text, so uniqueness must too.

    Phase 9 found an alias "kubernetes client" pointing at *Kubernetes Java
    Client* while a separate skill *kubernetes-client* existed. As raw strings
    they differ; as normalised text they are identical, so one advert phrase
    resolved to two skills depending on lookup order. The MTO merge's
    validator compared raw strings and could not see it. These tests compare
    the way the extractor actually matches.
    """

    @staticmethod
    def normalized(value):
        import re
        import unicodedata
        text = unicodedata.normalize("NFKC", str(value or "")).casefold().strip()
        text = text.replace("&", " and ")
        text = re.sub(r"[^\w+#.\- ]", " ", text)
        text = re.sub(r"[\s\-_]+", " ", text)
        return text.strip(" .")

    def test_no_two_skills_share_a_normalized_name(self):
        seen = {}
        for name in Skill.objects.values_list("skill_name", flat=True):
            if "," in name:
                continue        # quarantined malformed rows
            key = self.normalized(name)
            self.assertNotIn(
                key, seen,
                "%r and %r normalise identically" % (seen.get(key), name))
            seen[key] = name

    def test_no_active_alias_claims_another_skills_canonical_name(self):
        names = {}
        for pk, name in Skill.objects.values_list("id", "skill_name"):
            names.setdefault(self.normalized(name), pk)
        for alias in (SkillAlias.objects.filter(is_active=True)
                      .select_related("skill")):
            owner = names.get(self.normalized(alias.alias_name))
            if owner is not None and owner != alias.skill_id:
                self.fail("active alias %r points at %r but normalises onto a "
                          "different canonical skill"
                          % (alias.alias_name, alias.skill.skill_name))


class ExtractionProvenanceTests(TestCase):
    """Every detection must say how it was made.

    A link recorded without its matched text cannot be reviewed later, and
    "why did this advert get tagged with Go?" is the question that keeps
    coming up.
    """

    def setUp(self):
        self.skill = Skill.objects.create(skill_name="Kubernetes")

    def test_a_canonical_match_is_labelled_direct(self):
        from .skill_extractor import extract_skill_matches, DIRECT_CANONICAL

        matches = extract_skill_matches("Deep Kubernetes experience required.")

        self.assertEqual([(s.skill_name, t, m) for s, t, m in matches],
                         [("Kubernetes", "Kubernetes", DIRECT_CANONICAL)])

    def test_an_alias_match_is_labelled_alias(self):
        from .skill_extractor import extract_skill_matches, ALIAS

        SkillAlias.objects.create(skill=self.skill, alias_name="k8s")

        matches = extract_skill_matches("Deep k8s experience required.")

        self.assertEqual([m for _, _, m in matches], [ALIAS])

    def test_a_contextual_alias_needs_technical_surroundings(self):
        from .skill_extractor import extract_skill_matches, CONTEXTUAL_ALIAS

        SkillAlias.objects.create(skill=self.skill, alias_name="kube",
                                  requires_context=True)

        prose = extract_skill_matches("Our kube policy covers annual leave.")
        technical = extract_skill_matches(
            "kube experience with container orchestration and software "
            "engineering.")

        self.assertEqual(prose, [])
        self.assertEqual([m for _, _, m in technical], [CONTEXTUAL_ALIAS])

    def test_an_inactive_alias_never_produces_a_match(self):
        """Phase 9's near-miss: an inactive alias almost filed Malaysian XML
        demand under lxml, a Python parser."""
        from .skill_extractor import extract_skill_matches

        SkillAlias.objects.create(skill=self.skill, alias_name="k8s",
                                  is_active=False)

        self.assertEqual(extract_skill_matches("Deep k8s experience."), [])


class SeniorityNormalisationTests(TestCase):
    """Rank words must reach an approved role, or not come off at all.

    The failure this guards against is subtle: stripping a modifier is only
    safe when what remains is already a role we recognise. Unconditional
    stripping turns "Chief Information Officer" into "Information Officer" --
    an occupation that does not exist here -- and would let modifier removal
    invent roles rather than reach them.
    """

    def setUp(self):
        from .seniority_normalizer import analyse
        self.analyse = analyse
        self.approved = {
            "software engineer", "business analyst", "data analyst",
            "network engineer", "data scientist", "data engineer",
        }

    def is_approved(self, name):
        return str(name or "").strip().lower() in self.approved

    def candidate(self, title):
        return self.analyse(title, self.is_approved)["role_candidate"]

    def seniority(self, title):
        return self.analyse(title, self.is_approved)["seniority_level"]

    # ---- rank reaches an approved role: strip it --------------------------

    def test_senior_software_engineer_becomes_software_engineer(self):
        self.assertEqual(self.candidate("Senior Software Engineer"),
                         "software engineer")
        self.assertEqual(self.seniority("Senior Software Engineer"), "SENIOR")

    def test_junior_software_engineer_becomes_software_engineer(self):
        self.assertEqual(self.candidate("Junior Software Engineer"),
                         "software engineer")
        self.assertEqual(self.seniority("Junior Software Engineer"), "JUNIOR")

    def test_associate_software_engineer_becomes_software_engineer(self):
        self.assertEqual(self.candidate("Associate Software Engineer"),
                         "software engineer")
        self.assertEqual(self.seniority("Associate Software Engineer"),
                         "ASSOCIATE")

    def test_senior_business_analyst_becomes_business_analyst(self):
        self.assertEqual(self.candidate("Senior Business Analyst"),
                         "business analyst")

    def test_junior_data_analyst_becomes_data_analyst(self):
        self.assertEqual(self.candidate("Junior Data Analyst"), "data analyst")

    def test_abbreviated_rank_words_are_recognised(self):
        for title in ("Sr Software Engineer", "Sr. Software Engineer",
                      "Jr Software Engineer", "Snr Software Engineer"):
            self.assertEqual(self.candidate(title), "software engineer", title)

    # ---- functional words are never removed ------------------------------

    def test_senior_network_engineer_keeps_network(self):
        """Not "Engineer" -- Network is what the role is."""
        self.assertEqual(self.candidate("Senior Network Engineer"),
                         "network engineer")

    def test_associate_business_analyst_keeps_business(self):
        """Not "Analyst" -- that would merge three different careers."""
        self.assertEqual(self.candidate("Associate Business Analyst"),
                         "business analyst")

    # ---- the Chief safety rule -------------------------------------------

    def test_chief_is_stripped_only_onto_an_approved_role(self):
        self.assertEqual(self.candidate("Chief Data Scientist"),
                         "data scientist")

    def test_chief_information_officer_is_not_collapsed(self):
        """"Information Officer" is not an approved role, so nothing is
        stripped and the executive title survives intact."""
        result = self.analyse("Chief Information Officer", self.is_approved)

        self.assertEqual(result["role_candidate"], "chief information officer")
        self.assertEqual(result["removed_modifiers"], [])
        self.assertIn("not an approved role", result["decision"])

    def test_stripping_never_invents_a_role(self):
        """Every rank-stripped candidate must already be approved."""
        for title in ("Junior Developer", "Senior Product Owner",
                      "Associate SAS Programmer", "Senior Java Engineer"):
            result = self.analyse(title, self.is_approved)
            if result["removed_modifiers"]:
                self.assertTrue(self.is_approved(result["role_candidate"]),
                                "%r stripped to an unapproved role" % title)

    # ---- multi-role titles stay ambiguous --------------------------------

    def test_two_role_title_is_not_force_matched(self):
        result = self.analyse("Senior IT Lead / IT Supervisor",
                              self.is_approved)

        self.assertTrue(result["multi_role"])
        self.assertEqual(result["removed_modifiers"], [])

    def test_a_matching_half_does_not_win(self):
        """"Software Engineer / DevOps Engineer" names two roles; the first
        one matching must not decide the advert."""
        result = self.analyse("Software Engineer / DevOps Engineer",
                              self.is_approved)

        self.assertTrue(result["multi_role"])

    # ---- qualifiers are separated, not treated as the role ---------------

    def test_technology_and_recruitment_qualifiers_are_split_out(self):
        result = self.analyse(
            "Software Developer (.NET/C#) - Open to Fresh Graduate",
            self.is_approved)

        self.assertEqual(result["role_candidate"], "software developer")
        self.assertIn(".NET/C#", result["qualifiers"])
        self.assertEqual(result["seniority_level"], "ENTRY")

    def test_the_raw_title_is_never_destroyed(self):
        result = self.analyse("Senior Software Engineer", self.is_approved)

        self.assertEqual(result["raw_title"], "Senior Software Engineer")


class MarketRoleVocabularyTests(TestCase):
    """The Market Role set itself must stay well-formed."""

    def test_no_market_role_name_carries_a_rank_word(self):
        """Seniority is metadata. A Market Role called "Senior X" would split
        one career's demand across two rows."""
        from .seniority_normalizer import MODIFIERS

        offenders = [r.name for r in MarketRole.objects.all()
                     if r.name.split()[0].lower() in MODIFIERS]

        self.assertEqual(offenders, [])

    def test_market_role_names_are_unique_when_normalized(self):
        import re
        import unicodedata

        def key(value):
            text = unicodedata.normalize("NFKC", value).casefold().strip()
            return re.sub(r"[\s\-_]+", " ", text)

        seen = {}
        for role in MarketRole.objects.all():
            k = key(role.name)
            self.assertNotIn(k, seen,
                             "%r and %r normalise identically"
                             % (seen.get(k), role.name))
            seen[k] = role.name


class IMDAReferenceLayerTests(TestCase):
    """The two layers must stay two layers.

    The whole reason IMDA lives in its own table is that "this occupation
    exists" and "Malaysian employers are hiring for it" are different claims.
    These tests fail if the second one starts being inferred from the first.
    """

    def test_official_names_are_preserved_verbatim(self):
        """Normalisation writes derived fields; it never rewrites the source."""
        from .models import IMDARoleReference

        for reference in IMDARoleReference.objects.all()[:200]:
            self.assertTrue(reference.official_name.strip(),
                            "an IMDA reference row lost its official name")
            if reference.seniority_level:
                # The rank word must still be in the official name even though
                # base_role_name has had it removed.
                self.assertNotEqual(reference.official_name,
                                    reference.base_role_name)

    def test_every_reference_row_has_a_normalized_form(self):
        from .models import IMDARoleReference

        missing = IMDARoleReference.objects.filter(normalized_name="")
        self.assertFalse(missing.exists())

    def test_no_zero_evidence_imda_role_was_promoted(self):
        """The rule the whole architecture exists to enforce."""
        from .models import IMDARoleReference

        promoted = IMDARoleReference.objects.filter(
            mapping_status=IMDARoleReference.MappingStatus.PROMOTED_MARKET_ROLE)
        for reference in promoted:
            self.assertGreater(
                reference.malaysia_advert_count, 0,
                "%r was promoted with no Malaysian evidence"
                % reference.official_name)

    def test_every_promoted_market_role_is_labelled_as_such(self):
        from .models import IMDARoleReference, MarketRole

        promoted = IMDARoleReference.objects.filter(
            mapping_status=IMDARoleReference.MappingStatus.PROMOTED_MARKET_ROLE
        ).select_related("market_role")
        for reference in promoted:
            self.assertEqual(reference.market_role.catalogue_origin,
                             "IMDA_MARKET_EXTENSION")

    def test_reference_only_roles_have_no_market_role(self):
        """A role with no evidence must not leak into the production universe."""
        from .models import IMDARoleReference

        leaked = IMDARoleReference.objects.filter(
            mapping_status=IMDARoleReference.MappingStatus.NO_MARKET_EVIDENCE,
            market_role__isnull=False)
        self.assertFalse(
            leaked.exists(),
            "reference-only roles are pointing at Market Roles: %s"
            % list(leaked.values_list("official_name", flat=True))[:5])

    def test_every_mapping_is_explicit(self):
        """A market_role FK without a mapping row records the destination but
        not the reasoning, which is what makes it unreviewable later."""
        from .models import IMDARoleMarketMapping, IMDARoleReference

        mapped = IMDARoleReference.objects.filter(market_role__isnull=False)
        for reference in mapped:
            self.assertTrue(
                IMDARoleMarketMapping.objects.filter(
                    imda_role=reference,
                    market_role=reference.market_role).exists(),
                "%r has no mapping row" % reference.official_name)

    def test_seniority_is_stored_outside_the_market_role(self):
        from .models import IMDARoleReference

        for reference in IMDARoleReference.objects.exclude(
                seniority_level="").select_related("market_role")[:50]:
            if reference.market_role is None:
                continue
            self.assertNotIn(reference.seniority_level.lower(),
                             reference.market_role.name.lower(),
                             "rank leaked into the Market Role name")


class IMDASeniorityCollapseTests(TestCase):
    """The section 22 mappings, asserted against fixtures built here.

    These deliberately construct their own reference rows rather than reading
    whatever the development database happens to hold: a regression test that
    depends on ambient data passes for the wrong reasons and, under an empty
    test database, passes while asserting nothing.
    """

    def setUp(self):
        from .models import IMDARoleReference, IMDARoleMarketMapping

        self.roles = {name: MarketRole.objects.create(
            name=name, normalized_name=name.lower(), broad_area="Test")
            for name in ("Software Engineer", "Business Analyst",
                         "Network Engineer", "Data Engineer")}

        def reference(official, base, rank, target):
            row = IMDARoleReference.objects.create(
                official_name=official, normalized_name=official.lower(),
                base_role_name=base, seniority_level=rank,
                malaysia_advert_count=5 if target else 0,
                market_role=self.roles.get(target),
                mapping_status=("MAPPED_EXISTING" if target
                                else "NO_MARKET_EVIDENCE"))
            if target:
                IMDARoleMarketMapping.objects.create(
                    imda_role=row, market_role=self.roles[target],
                    mapping_type="SENIORITY_COLLAPSE", evidence_count=5)
            return row

        reference("Associate Software Engineer", "Software Engineer",
                  "ASSOCIATE", "Software Engineer")
        reference("Junior Software Engineer", "Software Engineer",
                  "JUNIOR", "Software Engineer")
        reference("Senior Software Engineer", "Software Engineer",
                  "SENIOR", "Software Engineer")
        reference("Associate Business Analyst", "Business Analyst",
                  "ASSOCIATE", "Business Analyst")
        reference("Associate Network Engineer", "Network Engineer",
                  "ASSOCIATE", "Network Engineer")
        reference("Senior Data Engineer", "Data Engineer", "SENIOR",
                  "Data Engineer")
        # "Information Officer" is not an approved role, so nothing is mapped.
        reference("Chief Information Officer", "Information Officer",
                  "CHIEF", None)

    def collapse(self, official):
        from .models import IMDARoleReference

        row = IMDARoleReference.objects.filter(
            official_name__iexact=official).first()
        return row.market_role.name if (row and row.market_role) else None

    def test_all_rank_variants_reach_the_same_market_role(self):
        for official in ("Associate Software Engineer",
                         "Junior Software Engineer",
                         "Senior Software Engineer"):
            self.assertEqual(self.collapse(official), "Software Engineer",
                             official)

    def test_associate_business_analyst_keeps_business(self):
        """Business Analyst, never bare "Analyst"."""
        self.assertEqual(self.collapse("Associate Business Analyst"),
                         "Business Analyst")

    def test_associate_network_engineer_keeps_network(self):
        """Network Engineer, never bare "Engineer"."""
        self.assertEqual(self.collapse("Associate Network Engineer"),
                         "Network Engineer")

    def test_senior_data_engineer_collapses(self):
        self.assertEqual(self.collapse("Senior Data Engineer"), "Data Engineer")

    def test_chief_information_officer_is_not_collapsed(self):
        """The safety rule at the data layer: "Information Officer" is not an
        approved role, so this executive title maps to nothing rather than to
        an invented one."""
        self.assertIsNone(self.collapse("Chief Information Officer"))

    def test_rank_variants_do_not_multiply_market_roles(self):
        """Three rungs, one career."""
        self.assertEqual(MarketRole.objects.filter(
            name="Software Engineer").count(), 1)

    def test_no_market_role_was_created_for_a_rank_variant(self):
        """Seniority must never fragment the Market Role universe."""
        from .seniority_normalizer import MODIFIERS

        offenders = [r.name for r in MarketRole.objects.all()
                     if r.name.split()[0].lower().strip(".") in MODIFIERS]
        self.assertEqual(offenders, [])


class ReviewedAliasResolutionTests(TestCase):
    """Aliases resolve by exact match, and only when reviewed.

    An alias is a human decision recorded once so it need not be made again.
    These tests guard the two ways that goes wrong: a keyword sneaking in as
    an alias, and an unreviewed row being allowed to classify.
    """

    def setUp(self):
        self.backend = MarketRole.objects.create(
            name="Backend Developer", normalized_name="backend developer",
            broad_area="Software & Applications")
        self.software = MarketRole.objects.create(
            name="Software Engineer", normalized_name="software engineer",
            broad_area="Software & Applications")
        MarketRoleAlias.objects.create(
            normalized_title="back end developer", market_role=self.backend,
            reviewed=True, is_active=True,
            source=MarketRoleAlias.Source.MALAYSIA_TITLE_REVIEW)
        MarketRoleAlias.objects.create(
            normalized_title="it software engineer", market_role=self.software,
            reviewed=True, is_active=True,
            source=MarketRoleAlias.Source.MALAYSIA_TITLE_REVIEW)

    def resolve(self, title):
        """Resolve the way production does.

        ``normalize_title`` is applied to both sides, because that is what
        MarketRoleAlias.save() stores and what the classifier feeds in. It
        expands "IT" to "information technology"; comparing raw strings misses
        every alias that starts with a department prefix.
        """
        import re
        import unicodedata

        from .title_normalizer import normalize_title

        def tight(value):
            text = unicodedata.normalize(
                "NFKC", str(normalize_title(value))).casefold().strip()
            text = re.sub(r"[^\w+#./ -]", " ", text)
            return re.sub(r"[\s./_-]+", "", text)

        index = {tight(a.normalized_title): a.market_role
                 for a in MarketRoleAlias.objects.filter(is_active=True,
                                                         reviewed=True)}
        index.update({tight(r.name): r for r in MarketRole.objects.all()})
        role = index.get(tight(title))
        return role.name if role else None

    def test_back_end_developer_reaches_backend_developer(self):
        self.assertEqual(self.resolve("Back End Developer"),
                         "Backend Developer")

    def test_senior_back_end_developer_reaches_backend_developer(self):
        from .seniority_normalizer import analyse

        parsed = analyse("Senior Back End Developer",
                         lambda n: self.resolve(n) is not None)
        self.assertEqual(self.resolve(parsed["role_candidate"]),
                         "Backend Developer")
        self.assertEqual(parsed["seniority_level"], "SENIOR")

    def test_it_software_engineer_reaches_software_engineer(self):
        self.assertEqual(self.resolve("IT Software Engineer"),
                         "Software Engineer")

    def test_a_bare_keyword_resolves_nothing(self):
        """"Engineer" fits several roles, so it must never be an alias."""
        self.assertIsNone(self.resolve("Engineer"))
        self.assertIsNone(self.resolve("Developer"))
        self.assertIsNone(self.resolve("Analyst"))

    def test_back_end_developer_resolves_without_any_alias(self):
        """"Back End Developer" and "Backend Developer" normalise identically,
        so the role name alone reaches it. The alias is redundant, which is
        worth knowing before minting more like it."""
        MarketRoleAlias.objects.filter(
            market_role=self.backend).update(is_active=False)

        self.assertEqual(self.resolve("Back End Developer"),
                         "Backend Developer")

    def test_an_inactive_alias_does_not_classify(self):
        """Uses a title only an alias can reach, so deactivating it really
        does remove the only route."""
        MarketRoleAlias.objects.create(
            normalized_title="scripting specialist", market_role=self.software,
            reviewed=True, is_active=True,
            source=MarketRoleAlias.Source.MALAYSIA_TITLE_REVIEW)
        self.assertEqual(self.resolve("Scripting Specialist"),
                         "Software Engineer")

        MarketRoleAlias.objects.filter(
            normalized_title__icontains="scripting specialist").update(
            is_active=False)

        self.assertIsNone(self.resolve("Scripting Specialist"))

    def test_an_unreviewed_alias_does_not_classify(self):
        MarketRoleAlias.objects.create(
            normalized_title="java engineer", market_role=self.software,
            reviewed=False, is_active=True,
            source=MarketRoleAlias.Source.MALAYSIA_TITLE_REVIEW)

        self.assertIsNone(self.resolve("Java Engineer"))


class GenericTitleBodyResolverTests(TestCase):
    """A generic title is settled by the body, or not at all."""

    MIN_SIGNALS = 3
    MIN_SCORE = 0.60
    MIN_MARGIN = 1.60

    def decide(self, scored, usable):
        """The production decision model, restated for the test."""
        if not scored:
            return "INSUFFICIENT_EVIDENCE", None
        overall = max(scored, key=lambda c: c[1])
        if overall[0] not in usable:
            return "ROLE_PROFILE_TOO_THIN", None
        assignable = sorted([c for c in scored if c[0] in usable],
                            key=lambda c: -c[1])
        best = assignable[0]
        runner = assignable[1] if len(assignable) > 1 else None
        if best[2] < self.MIN_SIGNALS or best[1] < self.MIN_SCORE:
            return "INSUFFICIENT_EVIDENCE", None
        if runner and runner[1] and best[1] / runner[1] < self.MIN_MARGIN:
            return "STILL_AMBIGUOUS", None
        return "RESOLVED", best[0]

    def test_helpdesk_evidence_resolves_to_it_support(self):
        scored = [("IT Support", 4.0, 5), ("Network Engineer", 0.9, 2)]
        self.assertEqual(self.decide(scored, {"IT Support",
                                              "Network Engineer"}),
                         ("RESOLVED", "IT Support"))

    def test_routing_evidence_resolves_to_network_engineer(self):
        scored = [("Network Engineer", 6.2, 6), ("IT Support", 1.1, 3)]
        self.assertEqual(self.decide(scored, {"IT Support",
                                              "Network Engineer"}),
                         ("RESOLVED", "Network Engineer"))

    def test_mixed_evidence_with_no_winner_stays_ambiguous(self):
        """"IT Engineer" with support and network signals in balance."""
        scored = [("IT Support", 3.1, 5), ("Network Engineer", 2.9, 5)]
        self.assertEqual(self.decide(scored, {"IT Support",
                                              "Network Engineer"})[0],
                         "STILL_AMBIGUOUS")

    def test_one_isolated_signal_never_resolves(self):
        scored = [("Network Engineer", 4.0, 1)]
        self.assertEqual(self.decide(scored, {"Network Engineer"})[0],
                         "INSUFFICIENT_EVIDENCE")

    def test_a_thin_role_profile_blocks_assignment(self):
        """When the best-scoring role is too thin to assign from, the answer
        is not the runner-up -- the advert's role is probably outside the
        usable set entirely."""
        scored = [("Data Engineer", 8.0, 6), ("Full Stack Developer", 2.0, 4)]

        self.assertEqual(self.decide(scored, {"Full Stack Developer"})[0],
                         "ROLE_PROFILE_TOO_THIN")

    def test_soft_skills_are_excluded_from_profiles(self):
        """Communication is top-5 in most roles; a signal present everywhere
        discriminates nowhere."""
        from pathlib import Path
        import csv
        import io

        path = (Path(__file__).resolve().parent.parent.parent
                / "research" / "market_role_alias_body_resolution"
                / "results" / "market_role_body_evidence.csv")
        if not path.exists():
            self.skipTest("body evidence not built in this environment")
        with io.open(path, encoding="utf-8", newline="") as handle:
            positives = [r for r in csv.DictReader(handle)
                         if r["signal_type"] == "POSITIVE"]
        soft = {"communication", "teamwork", "leadership", "problem solving"}
        offenders = [r["signal"] for r in positives
                     if r["signal"].strip().lower() in soft]
        self.assertEqual(offenders, [])


class CatalogueReproducibilityTests(TestCase):
    """A fresh database must rebuild the whole catalogue from the repository.

    The defect this guards: the development database held 2,102 skills and
    3,684 aliases while the repository could rebuild 162 and 39. Everything
    else -- the MTO import, the market extensions, all provenance and every
    relationship -- lived only in one database, so a fresh deployment computed
    different skill gaps and different match scores from identical code.

    Counts alone would not catch that. Two catalogues can agree on how many
    skills they hold and disagree on which are active, which alias points where,
    and which aliases may match unguarded -- and each of those changes what the
    extractor does. So the comparison is a full sorted snapshot, field by field,
    plus a digest over it.
    """

    def _empty_the_catalogue(self):
        """Leave the catalogue genuinely empty.

        The test database has migrations applied, and some of them seed rows.
        Clearing first is what makes this a test of the seed files rather than
        of whatever the migrations happened to leave behind.

        Order matters only for legibility -- deleting Skill cascades -- but
        being explicit says which tables are in scope.
        """
        SkillRelationship.objects.all().delete()
        SkillSource.objects.all().delete()
        SkillAlias.objects.all().delete()
        Skill.objects.all().delete()

    def test_fresh_import_reproduces_the_exported_catalogue(self):
        self._empty_the_catalogue()
        self.assertEqual(Skill.objects.count(), 0)

        call_command("import_skills", verbosity=0)

        expected = file_snapshot(DATA_DIR)
        rebuilt = database_snapshot()

        # Per table first: an assertion over the whole snapshot reports a
        # difference somewhere in nine thousand rows, which is not a report.
        for table in FILES:
            self.assertEqual(
                rebuilt[table], expected[table],
                f"{table} differs between the database and the seed files")

        self.assertEqual(snapshot_digest(rebuilt), snapshot_digest(expected))

    def test_rebuild_preserves_every_property_the_extractor_reads(self):
        """The fields a count-based check would miss.

        Each of these changes behaviour on its own: an alias pointing at the
        wrong canonical skill files demand under the wrong career, an
        is_active flag decides whether a skill can match at all, and
        requires_context decides whether a short or overloaded alias may match
        unguarded. A rebuild that got the counts right and any of these wrong
        would be silently wrong.
        """
        # The expectation is the repository, never the database this test
        # started with: the test database carries whatever the migrations
        # seeded, which is precisely the state these files exist to replace.
        before = file_snapshot(DATA_DIR)
        self._empty_the_catalogue()
        call_command("import_skills", verbosity=0)
        after = database_snapshot()

        names = lambda snap: [row["skill_name"] for row in snap["skills"]]
        self.assertEqual(names(after), names(before))

        mappings = lambda snap: {row["alias_name"]: row["skill_name"]
                                 for row in snap["aliases"]}
        self.assertEqual(mappings(after), mappings(before))

        def distribution(snap):
            counts = {}
            for row in snap["skills"]:
                counts[row["catalogue_status"]] = (
                    counts.get(row["catalogue_status"], 0) + 1)
            return counts
        self.assertEqual(distribution(after), distribution(before))

        active = lambda snap: {row["skill_name"]: row["is_active"]
                               for row in snap["skills"]}
        self.assertEqual(active(after), active(before))

        contextual = lambda snap: {row["alias_name"]: row["requires_context"]
                                   for row in snap["aliases"]}
        self.assertEqual(contextual(after), contextual(before))

        alias_active = lambda snap: {row["alias_name"]: row["is_active"]
                                     for row in snap["aliases"]}
        self.assertEqual(alias_active(after), alias_active(before))

        self.assertEqual(after["sources"], before["sources"])
        self.assertEqual(after["relationships"], before["relationships"])

    def test_import_is_idempotent(self):
        """Importing twice is importing once.

        The command runs on deploy without a guard, so a second run must not
        duplicate a row, flip a flag, or change the digest.
        """
        self._empty_the_catalogue()
        call_command("import_skills", verbosity=0)
        once = snapshot_digest(database_snapshot())

        call_command("import_skills", verbosity=0)
        self.assertEqual(snapshot_digest(database_snapshot()), once)

    # There is deliberately no test that the committed files match a developer's
    # own database. A test database is built from migrations, not from the
    # files, so such a check would compare the seeds against whatever the
    # migrations happened to seed and fail for a reason that is not staleness.
    # `manage.py export_skills --check` is that check, run against a real
    # database in CI or before a commit.


class DotNetPlatformSplitTests(TestCase):
    """.NET is the platform; ASP.NET is one web framework built on it.

    MTO shipped ".NET" as an *alias of ASP.NET*, which filed every advert
    asking for a ".NET developer" under a framework it had not asked for. In
    the Malaysian corpus the platform is named in 39 adverts against 19 for
    ASP.NET, so the conflation overstated the framework and hid the platform.

    Extraction is tested against a fixture rather than the imported catalogue,
    matching the other extractor tests here: what is under test is the boundary
    logic that keeps two overlapping names apart, and building the two skills
    directly says so without a 2,100-row import.
    """

    def setUp(self):
        self.dotnet, _ = Skill.objects.get_or_create(skill_name=".NET")
        self.aspnet, _ = Skill.objects.get_or_create(skill_name="ASP.NET")
        Skill.objects.get_or_create(skill_name="C#")
        SkillAlias.objects.get_or_create(
            alias_name=".NET Framework", defaults={"skill": self.dotnet})

    def _names(self, text):
        from .skill_extractor import extract_skills_from_text
        return {skill.skill_name for skill in extract_skills_from_text(text)}

    def test_bare_dotnet_is_the_platform_not_the_web_framework(self):
        names = self._names("Strong .NET developer with C# experience")

        self.assertIn(".NET", names)
        self.assertIn("C#", names)
        self.assertNotIn("ASP.NET", names)

    def test_aspnet_does_not_leak_a_dotnet_match(self):
        """The left boundary is what keeps these apart.

        ".NET" is a literal substring of "ASP.NET", so without an assertion
        that the term is not glued to a preceding token character, every
        ASP.NET advert would also count as a platform advert.
        """
        names = self._names("Design web applications using the ASP.NET framework")

        self.assertIn("ASP.NET", names)
        self.assertNotIn(".NET", names)

    def test_dotnet_framework_resolves_to_the_platform(self):
        """Malaysian adverts use "the .NET framework" to mean the platform.

        "Strong proficiency in the .NET framework (C#, ASP.NET, .NET Core/5+)"
        lists .NET Core inside "the .NET framework", which the strict legacy
        product reading cannot survive. Exactly one advert in the corpus uses
        the strict sense, so the alias points at the platform.
        """
        names = self._names("Proficient in the .NET framework and Visual Studio")

        self.assertIn(".NET", names)
        self.assertNotIn("ASP.NET", names)


class DotNetSeedDecisionTests(TestCase):
    """The split must survive a rebuild, so it is asserted where it lives.

    These read the seed files rather than the database. The files are what a
    fresh import reproduces, and a decision that held only in one developer's
    database is the exact failure the catalogue seeds were introduced to end.
    """

    @classmethod
    def setUpTestData(cls):
        cls.seeds = file_snapshot(DATA_DIR)
        cls.skills = {row["skill_name"] for row in cls.seeds["skills"]}
        cls.aliases = {row["alias_name"]: row["skill_name"]
                       for row in cls.seeds["aliases"]}

    def test_dotnet_is_a_canonical_skill_in_the_seeds(self):
        self.assertIn(".NET", self.skills)

    def test_dotnet_is_no_longer_an_alias_of_anything(self):
        """A name cannot be both canonical and an alias.

        alias_name is unique and the extractor reads canonical names and alias
        names from one term table, so leaving the alias in place would be a
        second, competing route to a different skill.
        """
        self.assertNotIn(".NET", self.aliases)

    def test_aspnet_and_aspnet_core_stay_canonical(self):
        self.assertIn("ASP.NET", self.skills)
        self.assertIn("ASP.NET Core", self.skills)

    def test_dotnet_framework_is_an_alias_of_the_platform(self):
        self.assertEqual(self.aliases.get(".NET Framework"), ".NET")

    def test_the_platform_carries_malaysian_provenance(self):
        """A market extension must say what vouched for it.

        .NET is in the catalogue because Malaysian adverts ask for it, not
        because an external taxonomy listed it, and the provenance row is what
        lets that claim be re-derived rather than trusted.
        """
        rows = [row for row in self.seeds["sources"]
                if row["skill_name"] == ".NET" and row["source"] == "MALAYSIA_JD"]

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source_type"], "market-evidence")
        self.assertIn("Malaysian adverts", rows[0]["source_version"])

    def test_the_platform_is_a_market_extension_and_active(self):
        row = next(r for r in self.seeds["skills"] if r["skill_name"] == ".NET")

        self.assertEqual(row["catalogue_status"], "MARKET_EXTENSION")
        self.assertEqual(row["is_active"], "true")


class DotNetCoreAndVbNetTests(TestCase):
    """Runtime variants collapse into .NET; languages and frameworks do not.

    ``.NET Core`` was an alias of ``ASP.NET Core`` -- the same platform/framework
    conflation removed for bare ".NET". The corpus names .NET Core in 13 adverts
    against 4 for ASP.NET Core, so the alias filed platform demand under a
    framework three times more often than that framework was asked for.

    VB.NET is deliberately *not* collapsed. It is a language that targets the
    platform, as C# is; mapping it to .NET would lose the distinction between
    knowing the ecosystem and knowing a particular language in it.
    """

    def setUp(self):
        self.dotnet, _ = Skill.objects.get_or_create(skill_name=".NET")
        Skill.objects.get_or_create(skill_name="ASP.NET Core")
        Skill.objects.get_or_create(skill_name="VB.NET")
        Skill.objects.get_or_create(skill_name="Visual Basic")
        SkillAlias.objects.get_or_create(
            alias_name=".NET Core", defaults={"skill": self.dotnet})

    def _names(self, text):
        from .skill_extractor import extract_skills_from_text
        return {skill.skill_name for skill in extract_skills_from_text(text)}

    def test_dotnet_core_alone_does_not_produce_the_web_framework(self):
        names = self._names("Backend services built on .NET Core and SQL Server")

        self.assertIn(".NET", names)
        self.assertNotIn("ASP.NET Core", names)

    def test_explicit_aspnet_core_still_resolves(self):
        """The repoint must not cost the framework its own adverts.

        ".NET Core" cannot match inside "ASP.NET Core": the term begins with a
        dot and its left assertion rejects a preceding token character, which
        is the same guard that keeps ".NET" out of "ASP.NET".
        """
        names = self._names("Build REST APIs with ASP.NET Core and Dapper")

        self.assertIn("ASP.NET Core", names)

    def test_an_advert_naming_no_web_framework_gets_none(self):
        """The advert that made the conflation visible.

        It names two runtimes and a UI library, and was recorded as ASP.NET
        Core -- a server-side web framework it never mentions.
        """
        names = self._names("Hands-on with .NET Core, .NET Framework, and React")

        self.assertIn(".NET", names)
        self.assertNotIn("ASP.NET Core", names)

    def test_vbnet_is_a_language_and_stays_separate_from_the_platform(self):
        names = self._names("Experience in VB.NET and MS SQL Server")

        self.assertIn("VB.NET", names)
        self.assertNotIn(".NET", names)

    def test_classic_visual_basic_is_not_vbnet(self):
        """Two QES adverts ask for VB in an industrial-automation context.

        "MS Office, Visual Basic, C# & C++" is VB6/VBA, not VB.NET, and folding
        the two together would file them under a language they do not name.
        """
        names = self._names(
            "Computer literate ( MS Office , Visual Basic , C# & C++ Programming .)")

        self.assertIn("Visual Basic", names)
        self.assertNotIn("VB.NET", names)


class DotNetCoreSeedDecisionTests(TestCase):
    """Both decisions must survive a rebuild, so they are asserted in the seeds."""

    @classmethod
    def setUpTestData(cls):
        cls.seeds = file_snapshot(DATA_DIR)
        cls.aliases = {row["alias_name"]: row["skill_name"]
                       for row in cls.seeds["aliases"]}
        cls.skills = {row["skill_name"] for row in cls.seeds["skills"]}

    def test_dotnet_core_is_an_alias_of_the_platform(self):
        self.assertEqual(self.aliases.get(".NET Core"), ".NET")

    def test_aspnet_core_remains_canonical(self):
        self.assertIn("ASP.NET Core", self.skills)

    def test_vbnet_and_visual_basic_are_both_canonical_and_distinct(self):
        self.assertIn("VB.NET", self.skills)
        self.assertIn("Visual Basic", self.skills)
        # Neither may be an alias of the other, nor of the platform.
        self.assertNotIn("VB.NET", self.aliases)
        self.assertNotIn("Visual Basic", self.aliases)

    def test_vbnet_records_its_malaysian_evidence_alongside_mto(self):
        """SkillSource exists so one skill can be attested by several sources.

        VB.NET came from MTO, and Malaysian adverts corroborate it. Recording
        only the first would leave the market evidence unstated; replacing it
        would lose where the skill actually came from.
        """
        sources = {row["source"] for row in self.seeds["sources"]
                   if row["skill_name"] == "VB.NET"}

        self.assertEqual(sources, {"MTO", "MALAYSIA_JD"})

        malaysian = next(row for row in self.seeds["sources"]
                         if row["skill_name"] == "VB.NET"
                         and row["source"] == "MALAYSIA_JD")
        self.assertEqual(malaysian["source_type"], "market-evidence")
        self.assertIn("4 employers", malaysian["source_version"])


class MarketRoleAliasControlTests(TestCase):
    """Every control on the alias table must actually gate classification.

    The resolver filtered on ``reviewed`` alone while the table carries three
    more controls. Nothing misbehaved, because all 231 rows were active and
    approved -- so the failure was latent: the first time somebody retired an
    alias or marked one pending, it would have kept classifying adverts and
    the deactivation would have looked applied.
    """

    def setUp(self):
        self.role = MarketRole.objects.create(name="Data Analyst",
                                              normalized_name="data analyst")

    def _alias(self, title, **kwargs):
        return MarketRoleAlias.objects.create(
            normalized_title=title, market_role=self.role, **kwargs)

    def test_an_active_approved_alias_classifies(self):
        self._alias("data analytics specialist")

        index = build_index()

        self.assertEqual(index.lookup("data analytics specialist")[0], self.role)

    def test_a_deactivated_alias_does_not_classify(self):
        self._alias("retired title", is_active=False)

        self.assertEqual(build_index().lookup("retired title"), (None, None))

    def test_a_pending_alias_does_not_classify(self):
        """Pending means nobody has looked at it yet.

        Classifying on it would make review a formality applied after the fact.
        """
        self._alias("pending title",
                    review_status=MarketRoleAlias.ReviewStatus.PENDING)

        self.assertEqual(build_index().lookup("pending title"), (None, None))

    def test_a_rejected_alias_does_not_classify(self):
        self._alias("rejected title",
                    review_status=MarketRoleAlias.ReviewStatus.REJECTED)

        self.assertEqual(build_index().lookup("rejected title"), (None, None))

    def test_a_body_context_alias_does_not_fire_on_the_title(self):
        """The flag means "too weak to fire on the title alone".

        Nothing reads it yet -- resolve_from_description scores the body rules
        and consults by_role only -- so leaving these in the title index made
        the flag mean the opposite of what it says.
        """
        self._alias("weak title", requires_body_context=True)

        self.assertEqual(build_index().lookup("weak title"), (None, None))

    def test_an_alias_of_a_retired_role_does_not_classify(self):
        self.role.is_active = False
        self.role.save(update_fields=["is_active"])
        self._alias("orphaned title")

        self.assertEqual(build_index().lookup("orphaned title"), (None, None))


class SkillDemandParameterTests(TestCase):
    """?top= is caller input and is validated as such.

    int("abc") raised straight out of the view and surfaced as a 500, which
    reads as a server fault: it pages whoever is on call for somebody else's
    typo, and buries real faults in the same signal.
    """

    def setUp(self):
        self.client = APIClient()
        self.url = "/api/scrape-jobs/skills/demand/"

    def test_a_non_numeric_top_is_rejected_not_crashed(self):
        response = self.client.get(self.url, {"top": "abc"})

        self.assertEqual(response.status_code, 400)
        self.assertIn("top", response.data)

    def test_a_zero_or_negative_top_is_rejected(self):
        for value in ("0", "-5"):
            with self.subTest(top=value):
                self.assertEqual(
                    self.client.get(self.url, {"top": value}).status_code, 400)

    def test_an_unbounded_top_is_rejected(self):
        """The ranking is a dashboard panel, not an export.

        Without a ceiling, ?top=999999 asks an anonymous request to rank the
        whole catalogue.
        """
        response = self.client.get(self.url, {"top": "999999"})

        self.assertEqual(response.status_code, 400)

    def test_a_valid_top_still_works(self):
        Skill.objects.create(skill_name="Python")

        self.assertEqual(self.client.get(self.url, {"top": "5"}).status_code, 200)
        self.assertEqual(self.client.get(self.url).status_code, 200)


class GenericTermGuardTests(TestCase):
    """Terms that are ordinary words, product families, or English idioms.

    Each of these matched as a technology skill in the live corpus and was
    wrong. They share one shape -- a real skill whose name is also something
    else -- and one failure mode: the generic context gate passes them, because
    a cabling advert and a Spark advert both read as technical.

    Both directions are fixtures here. A guard that only rejected would be
    indistinguishable from deleting the skill, and the true positives are what
    make these guards worth having rather than blunt removals.
    """

    def setUp(self):
        for name in ("Backbone.js", "Chart.js", "Sage", "Apache", "REST API",
                     "Xamarin.Essentials"):
            Skill.objects.get_or_create(skill_name=name)
        for alias, canonical in (("backbone", "Backbone.js"),
                                 ("charts", "Chart.js"),
                                 ("apache", "Apache"),
                                 ("REST", "REST API")):
            SkillAlias.objects.get_or_create(
                alias_name=alias,
                defaults={"skill": Skill.objects.get(skill_name=canonical),
                          "requires_context": True})

    def _names(self, text):
        from .skill_extractor import extract_skills_from_text
        return {skill.skill_name for skill in extract_skills_from_text(text)}

    # ---- Apache: the Foundation's name, worn by hundreds of projects -------

    def test_apache_web_server_context_is_accepted(self):
        self.assertIn("Apache", self._names(
            "Configure Apache HTTP Server virtual hosts and mod_rewrite rules"))
        self.assertIn("Apache", self._names(
            "Experience administering Nginx and Apache on Linux web servers"))

    def test_other_apache_projects_are_rejected(self):
        """43 of 44 corpus occurrences were a different project."""
        for text in (
            "Exposure to Databricks, Apache Spark, cloud platforms and analytics",
            "Kafka Connect and Apache Flink writing to Iceberg tables on S3",
            "Experience with Dubbo (Apache or Alibaba) and service discovery",
            "Build pipelines with Apache Airflow and Apache Hadoop",
        ):
            with self.subTest(text=text[:40]):
                self.assertNotIn("Apache", self._names(text))

    def test_apache_tomcat_is_not_the_http_server(self):
        """Tomcat is an Apache project and a web server, and neither is httpd.

        An advert asking for Tomcat is asking for a servlet container with its
        own skill identity, so it must not satisfy Apache HTTP Server.
        """
        self.assertNotIn("Apache", self._names(
            "Deploy Java applications to Apache Tomcat application servers"))

    # ---- REST: an API style, and an ordinary English word -----------------

    def test_rest_with_api_context_is_accepted(self):
        for text in (
            "Basic understanding of REST APIs and client-server architecture",
            "Build interfaces including REST API, JSON, TCP/IP and OPC UA",
            # Not "RESTful": REST cannot match inside it, and the
            # catalogue has no RESTful alias -- a gap worth its own review,
            # not something to assert as working here.
            "Develop REST endpoints returning JSON payloads",
        ):
            with self.subTest(text=text[:40]):
                self.assertIn("REST API", self._names(text))

    def test_ordinary_english_rest_is_rejected(self):
        """The five corpus occurrences that were the English word."""
        for text in (
            "Handle requests on Sat/Sun and Public Holidays (rest day given in lieu)",
            "Object storage is a strong plus (trainable for the rest)",
        ):
            with self.subTest(text=text[:40]):
                self.assertNotIn("REST API", self._names(text))

    # ---- The three fixed earlier, kept as regressions ----------------------

    def test_backbone_is_cabling_and_metaphor_more_often_than_javascript(self):
        self.assertIn("Backbone.js", self._names(
            "Experience with Backbone and Underscore in a JavaScript front-end"))
        for text in (
            "Coordinate fiber optic, backbone, and horizontal cabling scope",
            "Build and manage the data backbone that powers our AI capability",
            "You will serve as the technical backbone for global operations",
        ):
            with self.subTest(text=text[:40]):
                self.assertNotIn("Backbone.js", self._names(text))

    def test_charts_is_reporting_vocabulary(self):
        self.assertIn("Chart.js", self._names(
            "Build interactive charts with Chart.js and D3 in a web app"))
        for text in (
            "Help create project timelines (Gantt charts) and workflows",
            "Author and review Kubernetes manifests, Helm charts and configs",
            "Skills you'll gain: Microsoft Excel, Pivot Tables And Charts",
        ):
            with self.subTest(text=text[:40]):
                self.assertNotIn("Chart.js", self._names(text))

    def test_sage_is_accounting_software_not_a_publisher(self):
        self.assertIn("Sage", self._names(
            "Working understanding of ERP systems (ideally SAP, Sage, etc.)"))
        self.assertIn("Sage", self._names(
            "Support MAS 200 / Sage 100 accounting and payroll applications"))
        self.assertNotIn("Sage", self._names(
            "Sage Publications Advanced Project Management: Managing Stakeholders"))

    def test_essentials_no_longer_reaches_the_xamarin_library(self):
        """Deactivated rather than guarded: no context makes it the library.

        Every corpus hit was a title noun -- "The essentials of the role",
        "Google AI Essentials", "Jira Essentials" -- so a guard would have been
        a rule with no true positives to protect.
        """
        for text in ("The essentials of the role: convert designs into code",
                     "Google Prompting Essentials",
                     "Microsoft SQL Server: Performance Tuning Essentials"):
            with self.subTest(text=text[:40]):
                self.assertNotIn("Xamarin.Essentials", self._names(text))


class AICodingAssistantGuardTests(TestCase):
    """Product names that are evidence for a competence only in one sense.

    ChatGPT, Copilot, Cursor, Claude, Codex, Amazon Q and Gemini are all used
    far outside software development -- to draft email, to generate marketing
    copy, to build Power Platform flows, and as an API to program against.
    Only one of those uses is "AI Coding Assistants", so every product name is
    a contextual trigger and none is a synonym.

    Both directions are fixtures, and both are drawn from the Malaysian corpus
    rather than invented: the accepted texts are adverts the re-extraction
    linked, the rejected ones are adverts it deliberately left alone.
    """

    def setUp(self):
        skill, _ = Skill.objects.get_or_create(
            skill_name="AI Coding Assistants",
            defaults={"skill_category": "Software Engineering",
                      "catalogue_status": "MARKET_EXTENSION"})
        for alias in ("chatgpt", "github copilot", "copilot", "cursor",
                      "claude", "claude code", "codex", "amazon q", "gemini"):
            SkillAlias.objects.get_or_create(
                alias_name=alias,
                defaults={"skill": skill, "source": "INTERNAL",
                          "requires_context": True})

    def _names(self, text):
        from .skill_extractor import extract_skills_from_text
        return {skill.skill_name for skill in extract_skills_from_text(text)}

    def test_every_product_name_is_guarded_rather_than_unconditional(self):
        """The property the whole design rests on.

        An unguarded entry here would make one of these a plain alias, and an
        advert mentioning ChatGPT for customer support would acquire a
        software-engineering skill.
        """
        from .skill_extractor import AI_ASSISTANT_PRODUCTS, TERM_GUARDS

        for product in AI_ASSISTANT_PRODUCTS:
            with self.subTest(product=product):
                self.assertIn(product, TERM_GUARDS)

    def test_assistants_used_to_write_software_are_accepted(self):
        for text in (
            "Proficient in using AI coding assistants such as Claude Code, "
            "GitHub, or OpenAI Codex",
            "Productive from day one in a workflow where most code is written "
            "with AI coding tools (Claude Code)",
            "Active experience using AI-driven coding tools (e.g., GitHub "
            "Copilot, ChatGPT, Cursor, or Amazon Q) to accelerate development",
            "Experience using AI-assisted development tools such as GitHub "
            "Copilot, Claude Code, Cursor, or equivalent",
            "Use AI tools (e.g., GitHub Copilot, ChatGPT/Claude) to generate "
            "and optimize test cases",
        ):
            with self.subTest(text=text[:44]):
                self.assertIn("AI Coding Assistants", self._names(text))

    def test_the_microsoft_business_stack_is_not_a_coding_assistant(self):
        """Three adverts in the first shadow run were exactly this.

        Copilot beside Power Apps or SharePoint is the M365 assistant or
        Copilot Studio -- an automation product that happens to share a name.
        """
        for text in (
            "Build low-code solutions with Power Apps, Power Automate and "
            "Copilot Studio across SharePoint",
            "Deploy Microsoft 365 Copilot agents with Purview DLP controls "
            "and troubleshoot adoption",
            "Support Microsoft Fabric and Copilot rollout for corporate "
            "communications teams",
        ):
            with self.subTest(text=text[:44]):
                self.assertNotIn("AI Coding Assistants", self._names(text))

    def test_content_and_design_uses_are_not_a_coding_assistant(self):
        for text in (
            "Use ChatGPT and Adobe Firefly for content generation and social "
            "media marketing",
            "Produce marketing copy with ChatGPT and design assets in Figma",
        ):
            with self.subTest(text=text[:44]):
                self.assertNotIn("AI Coding Assistants", self._names(text))

    def test_programming_against_the_model_is_a_different_competence(self):
        """The catalogue already carries this as LLM, GenAI and OpenAI API.

        Someone integrating Claude's API is building an AI feature, not being
        helped to write the code that does it.
        """
        for text in (
            "Integrate LLM APIs such as OpenAI and Claude into backend "
            "services",
            "Experience consuming Gemini APIs from a Python codebase",
        ):
            with self.subTest(text=text[:44]):
                self.assertNotIn("AI Coding Assistants", self._names(text))

    def test_a_borrowed_trigger_word_is_not_a_coding_context(self):
        """Phrases that contain a trigger word and mean something else.

        Six course pairings fired on nothing but these. "No-Code Development"
        contains "Code" and promises you will write none; "Application
        Programming Interface" contains "Programming" and names an integration
        boundary. Negating them is a general vocabulary fix, not a
        course-specific exception -- an advert would misread them identically.
        """
        for text in (
            "Build with Copilot Studio: No-Code Development and Email "
            "Automation",
            "Low-Code Development with Microsoft Copilot",
            "Claude and Application Programming Interface (API) design",
            "ChatGPT, Infrastructure as Code (IaC), Cloud Deployment",
            "Microsoft Copilot, Code Reusability, Continuous Monitoring",
        ):
            with self.subTest(text=text[:44]):
                self.assertNotIn("AI Coding Assistants", self._names(text))

    def test_the_negation_does_not_swallow_genuine_neighbours(self):
        """"such as code review" must still fire.

        The bare cod(?:e|ing) alternative refuses it -- "as " precedes it --
        and the code_review alternative then matches at the same position.
        Worth pinning: the fix would otherwise silently narrow the trigger.
        """
        for text in (
            "Use GitHub Copilot for tasks such as code review and refactoring",
            "Cursor with Secure Coding and Debugging practice",
        ):
            with self.subTest(text=text[:44]):
                self.assertIn("AI Coding Assistants", self._names(text))

    def test_a_product_name_with_no_development_context_does_not_fire(self):
        """The default is silence.

        Most mentions in the corpus are neither coding nor an explicit reject
        -- they are a passing reference -- and those must produce nothing
        rather than falling through to a match.
        """
        for text in (
            "Familiarity with ChatGPT and other generative AI tools",
            "Comfortable using Gemini for day-to-day research",
        ):
            with self.subTest(text=text[:44]):
                self.assertNotIn("AI Coding Assistants", self._names(text))


class DriverPathConfigurationTests(TestCase):
    """Where the container finds Chromium, and why it must not look it up.

    ChromeDriverManager fetches a version manifest over the network on every
    call and raises when it cannot reach it. That is how a release-validation
    scrape came to report

        Status : FAILED
        Error  : Could not reach host. Are you offline?

    having never contacted the job board -- with a perfectly good driver already
    cached. The image installs chromium and chromium-driver from one apt
    snapshot and exports their paths, so these pin the property the Dockerfile
    depends on: given the paths, nothing is looked up.
    """

    def _create_driver(self, env):
        from unittest.mock import patch
        import os as _os

        from scrape_jobs import scraper

        with patch.dict(_os.environ, env, clear=False), \
                patch.object(scraper.webdriver, "Chrome") as chrome, \
                patch.object(scraper, "Service") as service, \
                patch.object(scraper, "ChromeDriverManager") as manager:
            scraper.create_driver()
        return chrome, service, manager

    def test_an_explicit_driver_path_is_used_without_a_version_lookup(self):
        _, service, manager = self._create_driver(
            {"CHROMEDRIVER_PATH": "/usr/bin/chromedriver", "CHROME_BINARY": ""})

        service.assert_called_once_with("/usr/bin/chromedriver")
        manager.assert_not_called()

    def test_an_explicit_chromium_binary_is_passed_to_chrome(self):
        chrome, _, _ = self._create_driver(
            {"CHROMEDRIVER_PATH": "/usr/bin/chromedriver",
             "CHROME_BINARY": "/usr/bin/chromium"})

        options = chrome.call_args.kwargs["options"]
        self.assertEqual(options.binary_location, "/usr/bin/chromium")

    def test_without_the_paths_the_previous_behaviour_is_unchanged(self):
        """A local clone must keep working with nothing configured."""
        _, _, manager = self._create_driver(
            {"CHROMEDRIVER_PATH": "", "CHROME_BINARY": ""})

        manager.assert_called_once()


class RefreshMarketDataTests(TestCase):
    """The exit code must mean something.

    `scrape_jobs` exits 0 whether it worked or not, which is why this
    orchestration exists. These pin the property that makes it schedulable:
    the verdict comes from the persisted ScrapeLog row, and a failed
    acquisition stops before any downstream stage can make the run look busy
    and successful.

    No network here -- the acquisition is replaced by a fake that writes the
    ScrapeLog row a real run would have written.
    """

    def _run(self, log_fields=None, write_log=True, **options):
        """Run the command with a faked acquisition. Returns (error, calls)."""
        from unittest.mock import patch

        from job_listings.models import ScrapeLog
        from scrape_jobs.management.commands import refresh_market_data

        calls = []

        def fake_call_command(name, *args, **kwargs):
            calls.append(name)
            if name == "scrape_jobs" and write_log:
                fields = {"status": "SUCCESS", "pages_attempted": 3,
                          "jobs_scraped": 90, "jobs_created": 90,
                          "jobs_updated": 0, "blocked_count": 0,
                          "error_message": ""}
                fields.update(log_fields or {})
                ScrapeLog.objects.create(**fields)

        options.setdefault("skip_taxonomies", True)
        options.setdefault("max_pages", 1)
        options.setdefault("max_jobs", 1)
        options.setdefault("allow_no_new_adverts", False)

        error = None
        with patch.object(refresh_market_data, "call_command", fake_call_command):
            try:
                call_command("refresh_market_data", **options)
            except CommandError as exc:
                error = exc
        return error, calls

    def test_a_successful_acquisition_runs_every_downstream_stage(self):
        error, calls = self._run()

        self.assertIsNone(error)
        self.assertEqual(calls[0], "scrape_jobs")
        for stage in ("dedupe_scraped_listings", "recategorize_job_listings",
                      "reextract_job_skills", "classify_market_roles",
                      "refresh_skill_gaps"):
            self.assertIn(stage, calls)

    def test_a_failed_scrapelog_fails_the_refresh(self):
        """The exact case that makes the bare scraper unschedulable."""
        error, _ = self._run(
            {"status": "FAILED", "jobs_scraped": 0, "jobs_created": 0,
             "error_message": "Could not reach host. Are you offline?"})

        self.assertIsNotNone(error)
        self.assertIn("FAILED", str(error))

    def test_no_downstream_stage_runs_after_a_failed_acquisition(self):
        """Otherwise the run reports success having acquired nothing.

        Re-extraction and classification over an unchanged table succeed
        perfectly well, which is what would make a stale refresh look healthy.
        """
        _, calls = self._run(
            {"status": "FAILED", "jobs_scraped": 0, "jobs_created": 0})

        self.assertEqual(calls, ["scrape_jobs"])

    def test_a_fully_blocked_run_fails_even_though_it_says_success(self):
        """A bot wall is recorded as a count, not as a failure status."""
        error, calls = self._run(
            {"status": "SUCCESS", "pages_attempted": 3, "blocked_count": 3,
             "jobs_scraped": 0, "jobs_created": 0})

        self.assertIsNotNone(error)
        self.assertIn("blocked", str(error).lower())
        self.assertEqual(calls, ["scrape_jobs"])

    def test_a_partially_blocked_run_with_adverts_still_succeeds(self):
        """Being turned away from one page of forty is not a failed refresh."""
        error, _ = self._run(
            {"status": "SUCCESS", "pages_attempted": 40, "blocked_count": 1,
             "jobs_scraped": 90, "jobs_created": 90})

        self.assertIsNone(error)

    def test_a_scrape_that_wrote_no_log_row_fails(self):
        """No row means nothing can be said about whether it ran."""
        error, calls = self._run(write_log=False)

        self.assertIsNotNone(error)
        self.assertEqual(calls, ["scrape_jobs"])

    def test_acquiring_nothing_new_fails_unless_that_is_expected(self):
        error, _ = self._run({"jobs_created": 0, "jobs_updated": 0})
        self.assertIsNotNone(error)

        error, _ = self._run({"jobs_created": 0, "jobs_updated": 0},
                             allow_no_new_adverts=True)
        self.assertIsNone(error)

    def test_a_second_refresh_refuses_while_one_holds_the_lock(self):
        """Two Selenium crawls writing the same adverts, one re-extracting
        while the other replaces the rows underneath it, is not a state worth
        reasoning about afterwards -- so the second one refuses.

        The lock is taken on a separate connection because PostgreSQL advisory
        locks are re-entrant within a session: asking twice on one connection
        succeeds twice and would prove nothing.
        """
        import psycopg2
        from django.conf import settings

        from scrape_jobs.management.commands.refresh_market_data import (
            ADVISORY_LOCK_KEY)

        db = settings.DATABASES["default"]
        holder = psycopg2.connect(
            dbname=db["NAME"], user=db["USER"], password=db["PASSWORD"],
            host=db["HOST"], port=db["PORT"])
        try:
            holder.autocommit = True
            with holder.cursor() as cursor:
                cursor.execute("SELECT pg_try_advisory_lock(%s)",
                               [ADVISORY_LOCK_KEY])
                self.assertTrue(cursor.fetchone()[0], "could not take the lock")

            error, calls = self._run()

            self.assertIsNotNone(error)
            self.assertIn("advisory lock", str(error))
            self.assertEqual(calls, [], "nothing may run without the lock")
        finally:
            holder.close()

    def test_the_lock_is_released_so_the_next_run_can_take_it(self):
        """A refresh that holds the lock forever breaks every later one."""
        self._run()
        error, calls = self._run()

        self.assertIsNone(error)
        self.assertIn("scrape_jobs", calls)


class MarketRoleSeedReproducibilityTests(TestCase):
    """A fresh database must reproduce the reviewed state, and say so if not.

    Market roles had no seed check while skills and resources did, and they
    drifted: three MALAYSIA_TITLE_REVIEW aliases and one IMDA_MARKET_EXTENSION
    role were approved into a database and never written back to the file. A
    fresh deployment would have classified those adverts differently from the
    one the decision was reviewed on, and nothing would have reported it.
    """

    #: The reviewed decisions the seed did not carry until this was fixed.
    REVIEWED = (
        ("information technology product manager", "Product Manager"),
        ("information technology application support analyst",
         "Application Support Analyst"),
        ("information technology software engineer", "Software Engineer"),
    )

    @classmethod
    def setUpTestData(cls):
        call_command("load_market_roles")

    def test_a_fresh_load_produces_the_whole_reviewed_taxonomy(self):
        self.assertEqual(MarketRole.objects.count(), 32)
        self.assertEqual(MarketRoleAlias.objects.count(), 231)

    def test_product_manager_exists_after_a_fresh_load(self):
        """The role the seed was missing.

        It reached the database as a reviewed market extension and lived only
        there, so a fresh deployment had 31 roles and filed "IT Product Manager"
        as unclassified.
        """
        role = MarketRole.objects.get(name="Product Manager")

        self.assertEqual(role.catalogue_origin, "IMDA_MARKET_EXTENSION")
        self.assertTrue(role.is_active)

    def test_each_reviewed_alias_resolves_to_its_approved_role(self):
        for title, role_name in self.REVIEWED:
            with self.subTest(title=title):
                alias = MarketRoleAlias.objects.select_related(
                    "market_role").get(normalized_title=title)
                self.assertEqual(alias.market_role.name, role_name)
                self.assertEqual(alias.source, "MALAYSIA_TITLE_REVIEW")
                self.assertEqual(alias.review_status, "APPROVED")
                self.assertTrue(alias.reviewed)

    def test_loading_twice_changes_nothing(self):
        call_command("load_market_roles")

        self.assertEqual(MarketRole.objects.count(), 32)
        self.assertEqual(MarketRoleAlias.objects.count(), 231)

    # ---- the check itself --------------------------------------------------

    def test_the_check_passes_on_the_seeded_state(self):
        call_command("load_market_roles", check=True)   # raises if it disagrees

    def test_the_check_does_not_write(self):
        """It must be safe to run against production."""
        MarketRoleAlias.objects.filter(
            normalized_title="information technology product manager").delete()

        with self.assertRaises(CommandError):
            call_command("load_market_roles", check=True)

        # Still missing: the check reported, it did not repair.
        self.assertFalse(MarketRoleAlias.objects.filter(
            normalized_title="information technology product manager").exists())

    def test_an_extra_role_in_the_database_fails_the_check(self):
        MarketRole.objects.create(name="Invented Role",
                                  normalized_name="invented role")

        with self.assertRaises(CommandError) as caught:
            call_command("load_market_roles", check=True)

        self.assertIn("not the seed", str(caught.exception))

    def test_a_missing_alias_fails_the_check(self):
        MarketRoleAlias.objects.filter(
            normalized_title="information technology software engineer").delete()

        with self.assertRaises(CommandError) as caught:
            call_command("load_market_roles", check=True)

        self.assertIn("alias missing", str(caught.exception))

    def test_an_alias_pointing_at_the_wrong_role_fails_the_check(self):
        """The failure a row count cannot see.

        Counts still agree; the classification is simply wrong, which is the
        shape of drift most worth catching.
        """
        alias = MarketRoleAlias.objects.get(
            normalized_title="information technology product manager")
        alias.market_role = MarketRole.objects.get(name="Software Engineer")
        alias.save()

        with self.assertRaises(CommandError) as caught:
            call_command("load_market_roles", check=True)

        self.assertIn("market_role", str(caught.exception))

    def test_changed_review_metadata_fails_the_check(self):
        """A reviewed decision downgraded in the database is a real difference,
        even though every row is still present and pointing correctly."""
        MarketRoleAlias.objects.filter(
            normalized_title="information technology product manager"
        ).update(source="LEGACY")

        with self.assertRaises(CommandError) as caught:
            call_command("load_market_roles", check=True)

        self.assertIn("source", str(caught.exception))

    def test_a_changed_role_catalogue_origin_fails_the_check(self):
        MarketRole.objects.filter(name="Product Manager").update(
            catalogue_origin="MARKET_DERIVED")

        with self.assertRaises(CommandError) as caught:
            call_command("load_market_roles", check=True)

        self.assertIn("catalogue_origin", str(caught.exception))


class BootstrapDomainInvariantTests(TestCase):
    """A seed digest proves the database equals the file. Not that the file is sane.

    Both checks were needed here, and only one existed. A role reached the seed
    with no broad_area, the database matched the file exactly, and the digest
    was satisfied -- while the role itself was counted, verified, and unreachable
    from every career-area view.

    So this invariant is deliberately not part of the digest: it asks a
    different question.
    """

    def _verify(self):
        """Run just the invariant, without the rest of a bootstrap."""
        from scrape_jobs.management.commands.bootstrap_database import Command

        command = Command()
        command.stdout = StringIO()
        command._check_domain_invariants()

    @classmethod
    def setUpTestData(cls):
        call_command("load_market_roles")

    def test_the_seeded_taxonomy_satisfies_the_invariant(self):
        self.assertEqual(MarketRole.objects.count(), 32)

        self._verify()   # raises if any role has no area

    def test_a_role_with_no_broad_area_fails_verification(self):
        MarketRole.objects.filter(name="Product Manager").update(broad_area="")

        with self.assertRaises(CommandError):
            self._verify()

    def test_the_failure_names_the_offending_role(self):
        """A count alone sends the operator looking through 32 rows."""
        MarketRole.objects.filter(name="Product Manager").update(broad_area="")

        with self.assertRaises(CommandError) as caught:
            self._verify()

        self.assertIn("Product Manager", str(caught.exception))

    def test_every_offender_is_named_not_just_the_first(self):
        MarketRole.objects.filter(
            name__in=["Product Manager", "Data Engineer"]).update(broad_area="")

        with self.assertRaises(CommandError) as caught:
            self._verify()

        message = str(caught.exception)
        self.assertIn("Product Manager", message)
        self.assertIn("Data Engineer", message)

    def test_a_whitespace_only_area_is_treated_as_empty(self):
        """It would pass exclude(broad_area="") and still be unbrowsable."""
        MarketRole.objects.filter(name="Product Manager").update(broad_area="   ")

        with self.assertRaises(CommandError) as caught:
            self._verify()

        self.assertIn("Product Manager", str(caught.exception))

    def test_the_invariant_does_not_write(self):
        """It must be safe to run against a real database."""
        MarketRole.objects.filter(name="Product Manager").update(broad_area="")

        with self.assertRaises(CommandError):
            self._verify()

        self.assertEqual(
            MarketRole.objects.get(name="Product Manager").broad_area, "")
