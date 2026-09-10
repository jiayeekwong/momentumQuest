"""Listing the courses related to a skill, and refusing to rank them by quality.

The page's job is to show a student what teaches a skill and let them choose.
These pin the properties that makes that honest: strong evidence first, no
empty slots, and no signal used that the data cannot support.
"""

from django.test import TestCase

from scrape_jobs.models import Skill

from .models import CourseCatalogue, LearningResource, RejectedResourceMapping
from .relevance import (
    DECLARED, MENTION, TITLE, UNKNOWN, evidence_tier, free_status,
    related_resources,
)


class EvidenceTierTests(TestCase):
    """How directly a course's own words support the skill it is filed under."""

    def test_the_title_naming_the_skill_is_the_strongest_signal(self):
        self.assertEqual(
            evidence_tier("Python", "Learn Python Programming", ""), TITLE)

    def test_a_provider_declaring_the_skill_comes_next(self):
        self.assertEqual(
            evidence_tier("SQL", "Data Analysis Foundations",
                          "Skills you'll gain: SQL, Tableau, Excel"),
            DECLARED)

    def test_a_passing_mention_is_the_weakest(self):
        """The failure this tier exists to demote.

        "5G Mobile Networks" reached a Machine Learning recommendation this
        way: its declared skills are Network Architecture, IoT and Network
        Security, and machine learning appears once in the prose.
        """
        self.assertEqual(
            evidence_tier(
                "Machine Learning", "5G Mobile Networks",
                "Skills you'll gain: Network Architecture, Network Security. "
                "The course touches on machine learning for traffic shaping."),
            MENTION)

    def test_no_supporting_text_at_all_ranks_last(self):
        self.assertEqual(evidence_tier("Kubernetes", "Some Course", ""),
                         UNKNOWN)


class RelatedResourceOrderTests(TestCase):

    def setUp(self):
        self.skill = Skill.objects.create(skill_name="Python")

    def _resource(self, title, platform, card_text="", url=None):
        url = url or f"https://example.com/{title.lower().replace(' ', '-')}"
        CourseCatalogue.objects.create(
            url=url, title=title, platform=platform, card_text=card_text,
            type="Course")
        return LearningResource.objects.create(
            skill=self.skill, url=url, title=title, platform=platform,
            type="Course")

    def test_strong_evidence_outranks_a_preferred_provider(self):
        """Evidence decides the band; nothing else may promote across bands.

        A vendor's passing mention must not outrank another provider's course
        that is actually about the skill.
        """
        self._resource("Advanced Topics", "VendorCo",
                       "The course mentions Python once.")
        self._resource("Learn Python", "OtherCo")

        rows, _ = related_resources(self.skill,
                                    authority={"Python": "VendorCo"})

        self.assertEqual([r.title for r in rows],
                         ["Learn Python", "Advanced Topics"])

    def test_the_vendor_leads_within_one_evidence_band(self):
        self._resource("Python Basics", "OtherCo")
        self._resource("Python Fundamentals", "VendorCo")

        rows, _ = related_resources(self.skill,
                                    authority={"Python": "VendorCo"})

        self.assertEqual(rows[0].platform, "VendorCo")

    def test_authority_is_per_skill_not_per_provider(self):
        """A vendor for one technology is an ordinary provider for another."""
        self._resource("Python Basics", "OtherCo")
        self._resource("Python Fundamentals", "VendorCo")

        rows, _ = related_resources(self.skill, authority={"SAP": "VendorCo"})

        self.assertEqual(rows[0].platform, "OtherCo")

    def test_providers_are_spread_within_a_band(self):
        for n in range(3):
            self._resource(f"Python Course A{n}", "BigCo")
        self._resource("Python Course B", "SmallCo")

        rows, _ = related_resources(self.skill, limit=2)

        self.assertEqual({r.platform for r in rows}, {"BigCo", "SmallCo"})

    def test_one_provider_fills_every_slot_rather_than_leaving_gaps(self):
        """No hard cap. A student with five slots and one provider wants five
        courses, not three and two gaps."""
        for n in range(5):
            self._resource(f"Python Course {n}", "OnlyCo")

        rows, total = related_resources(self.skill, limit=5)

        self.assertEqual(len(rows), 5)
        self.assertEqual(total, 5)

    def test_the_total_is_the_full_count_not_the_slice(self):
        """What "View more" needs to know whether it has anything to offer."""
        for n in range(9):
            self._resource(f"Python Course {n}", "OnlyCo")

        rows, total = related_resources(self.skill, limit=5)

        self.assertEqual((len(rows), total), (5, 9))

    def test_no_limit_returns_everything(self):
        for n in range(7):
            self._resource(f"Python Course {n}", "OnlyCo")

        rows, total = related_resources(self.skill, limit=None)

        self.assertEqual((len(rows), total), (7, 7))

    def test_the_order_is_the_same_every_time(self):
        """A student returning to the page must find what they saw."""
        for n in range(6):
            self._resource(f"Python Course {n}", "OnlyCo")

        first, _ = related_resources(self.skill, limit=4)
        second, _ = related_resources(self.skill, limit=4)

        self.assertEqual([r.id for r in first], [r.id for r in second])

    def test_retired_material_is_never_listed(self):
        resource = self._resource("Python Retired", "OnlyCo")
        LearningResource.objects.filter(id=resource.id).update(is_active=False)
        self._resource("Python Live", "OnlyCo")

        rows, total = related_resources(self.skill)

        self.assertEqual([r.title for r in rows], ["Python Live"])
        self.assertEqual(total, 1)


class FreeStatusTests(TestCase):
    """Price is displayed where stated and omitted where not -- never ranked on."""

    def test_only_stated_prices_are_returned(self):
        CourseCatalogue.objects.create(url="https://e.com/a", title="A",
                                       platform="P", type="Course", is_free=True)
        CourseCatalogue.objects.create(url="https://e.com/b", title="B",
                                       platform="P", type="Course", is_free=False)
        CourseCatalogue.objects.create(url="https://e.com/c", title="C",
                                       platform="P", type="Course", is_free=None)

        prices = free_status(["https://e.com/a", "https://e.com/b",
                              "https://e.com/c"])

        self.assertEqual(prices, {"https://e.com/a": True,
                                  "https://e.com/b": False})
        # Absent rather than None: a key that is not there is harder to render
        # as "Paid" by accident.
        self.assertNotIn("https://e.com/c", prices)

    def test_price_does_not_influence_the_order(self):
        """Coverage of this field is sparse -- only one provider states it --
        so ranking by it would order by platform wearing a different name."""
        skill = Skill.objects.create(skill_name="Docker")
        for title, is_free in (("Docker A", None), ("Docker B", True)):
            url = f"https://e.com/{title.replace(' ', '')}"
            CourseCatalogue.objects.create(url=url, title=title, platform="P",
                                           type="Course", is_free=is_free)
            LearningResource.objects.create(skill=skill, url=url, title=title,
                                            platform="P", type="Course")

        rows, _ = related_resources(skill)

        # Alphabetical within the band, untouched by the free flag.
        self.assertEqual([r.title for r in rows], ["Docker A", "Docker B"])


class RejectedMappingTests(TestCase):
    """A reviewed refusal has to survive the next offline remap.

    Mapping is lexical and re-run whenever the extractor changes. Some
    pairings are lexically valid and still wrong -- "2026 AI SEO Tools And
    Techniques (LLM SEO, GEO, AEO)" really does contain "LLM" -- so the
    judgement is recorded as data the mapper consults, rather than as a
    course-specific rule inside the extractor.
    """

    def setUp(self):
        self.skill = Skill.objects.create(skill_name="LLM")
        self.url = "https://www.coursera.org/learn/ai-seo"
        CourseCatalogue.objects.create(
            url=self.url, title="2026 AI SEO With Traffic From LLM SEO",
            platform="Coursera", type="Course",
            card_text="Skills you'll gain: Search Engine Optimization, LLM SEO")

    def _map(self):
        from .services import map_catalogue_to_skills
        return map_catalogue_to_skills(platform_name="Coursera")

    def test_a_rejected_pairing_is_not_recreated_by_remapping(self):
        """The property that makes a rejection worth recording at all."""
        RejectedResourceMapping.objects.create(
            skill=self.skill, url=self.url,
            reason="Search-marketing course, not language-model engineering.")

        self._map()

        self.assertFalse(
            LearningResource.objects.filter(skill=self.skill, url=self.url)
            .exists())

    def test_without_a_rejection_the_same_pairing_is_mapped(self):
        """Shows the rejection is what does the work, not the fixture."""
        self._map()

        self.assertTrue(
            LearningResource.objects.filter(skill=self.skill, url=self.url)
            .exists())

    def test_rejecting_after_the_fact_removes_the_existing_row(self):
        """Deactivating the row would not survive: the mapper writes
        is_active=True on every pass."""
        self._map()
        self.assertTrue(LearningResource.objects.filter(skill=self.skill).exists())

        RejectedResourceMapping.objects.create(skill=self.skill, url=self.url)
        self._map()

        self.assertFalse(LearningResource.objects.filter(skill=self.skill).exists())

    def test_a_rejection_is_scoped_to_one_skill(self):
        """The course may legitimately teach something else.

        An SEO course is a perfectly good SEO resource; only its claim on LLM
        was refused.
        """
        seo = Skill.objects.create(skill_name="Search Engine Optimization")
        RejectedResourceMapping.objects.create(skill=self.skill, url=self.url)

        self._map()

        self.assertTrue(
            LearningResource.objects.filter(skill=seo, url=self.url).exists())
        self.assertFalse(
            LearningResource.objects.filter(skill=self.skill, url=self.url)
            .exists())

    def test_rejections_travel_in_the_seed_files(self):
        """A decision that lived in one database would be re-learned by every
        deployment, which is the failure the seeds exist to prevent."""
        from .seeds import database_snapshot

        RejectedResourceMapping.objects.create(
            skill=self.skill, url=self.url, reason="SEO jargon, not LLM work.")

        rows = database_snapshot()["rejections"]

        self.assertEqual(rows, [{"skill_name": "LLM", "url": self.url,
                                 "reason": "SEO jargon, not LLM work."}])
