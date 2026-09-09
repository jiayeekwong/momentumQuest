"""The multi-provider layer: shape, identity, and who is authoritative.

Hermetic on purpose. No network and no catalogue writes, so these run while an
acquisition is in flight and cannot disturb it. The Microsoft Learn adapter is
exercised against a captured catalog payload rather than the live API, because
a test that fails when DNS does is not testing the adapter.
"""

from django.test import SimpleTestCase

from .providers.authority import (
    NON_VENDOR, VENDOR, authority_index, is_authoritative, preference_rank,
    rank_resources,
)
from .providers.base import CourseProvider
from .providers.dedup import (
    CROSS_PROVIDER_EQUIVALENTS, cross_provider_report, deduplicate, group_key,
)
from .providers.microsoft_learn import MicrosoftLearnProvider
from .providers.normalize import InvalidCourse, merge_course, normalize_course


class NormalisationTests(SimpleTestCase):
    """Providers publish different things; the catalogue stores one shape."""

    def _row(self, **overrides):
        row = {
            "url": "https://learn.microsoft.com/training/modules/csharp",
            "title": "  Get   started with C#  ",
            "description": "Learn C#\nfundamentals.",
            "provider": "Microsoft Learn",
            "type": "Module",
            "is_free": True,
            "discovered_via": ["C# programming", "C# programming", " .NET "],
        }
        row.update(overrides)
        return row

    def test_whitespace_is_collapsed_so_diffs_mean_something(self):
        """A description differing only by line breaks is not a change.

        These strings are hashed into seed digests and read by a person in a
        diff, so unnormalised whitespace would churn the seed files for no
        catalogue movement.
        """
        course = normalize_course(self._row())

        self.assertEqual(course["title"], "Get started with C#")
        self.assertEqual(course["description"], "Learn C# fundamentals.")

    def test_discovered_via_is_a_sorted_set(self):
        """Which queries found a course matters; the order they ran does not."""
        course = normalize_course(self._row())

        self.assertEqual(course["discovered_via"], [".NET", "C# programming"])

    def test_unknown_price_stays_unknown(self):
        """None is an answer, and turning it into False would misinform.

        "Not stated" becoming "paid" tells a student a free course costs money.
        """
        self.assertIsNone(normalize_course(self._row(is_free=None))["is_free"])
        self.assertIs(normalize_course(self._row(is_free="free"))["is_free"], True)
        self.assertIs(normalize_course(self._row(is_free="paid"))["is_free"], False)
        self.assertIsNone(normalize_course(self._row(is_free="RM49"))["is_free"])

    def test_unusable_rows_are_rejected_with_a_reason(self):
        """A broken adapter should be a number in a report, not an empty table."""
        for bad, why in (
            ({"title": ""}, "missing title"),
            ({"url": ""}, "missing url"),
            ({"url": "/training/modules/x"}, "relative url"),
            ({"title": "Free"}, "navigation furniture, not a course"),
        ):
            with self.subTest(why=why):
                with self.assertRaises(InvalidCourse):
                    normalize_course(self._row(**bad))

    def test_merging_two_sightings_never_loses_information(self):
        """The second sighting of a course must not erase the first's evidence.

        "SAP" and "SAP ABAP" both surface the S/4HANA specialization, and the
        thinner card must not overwrite the richer one.
        """
        first = normalize_course(self._row(
            description="A full description of the course",
            discovered_via=["SAP"]))
        second = normalize_course(self._row(
            description="", is_free=None, discovered_via=["SAP ABAP"]))

        merged = merge_course(first, second)

        self.assertEqual(merged["description"],
                         "A full description of the course")
        self.assertEqual(merged["discovered_via"], ["SAP", "SAP ABAP"])
        self.assertIs(merged["is_free"], True)

    def test_a_stated_price_beats_an_unstated_one(self):
        first = normalize_course(self._row(is_free=None))
        second = normalize_course(self._row(is_free=False))

        self.assertIs(merge_course(first, second)["is_free"], False)


class DeduplicationTests(SimpleTestCase):
    """One provider's URL variants collapse; two providers' courses do not."""

    def _course(self, url, provider="Coursera", title="Python for Everybody"):
        return {"url": url, "provider": provider, "title": title,
                "description": "", "type": "Course", "is_free": None,
                "discovered_via": []}

    def test_url_variants_from_one_provider_are_one_course(self):
        provider = MicrosoftLearnProvider()
        variants = [
            "https://learn.microsoft.com/training/modules/csharp",
            "https://learn.microsoft.com/training/modules/csharp/",
            "https://learn.microsoft.com/training/modules/csharp?wt.mc_id=x",
            "https://learn.microsoft.com/training/modules/csharp#unit-1",
        ]

        self.assertEqual(
            {provider.canonical_url(url) for url in variants},
            {"https://learn.microsoft.com/training/modules/csharp"})

    def test_similar_courses_from_two_providers_stay_separate(self):
        """The thing a student is choosing between must survive.

        Merging Coursera's and Microsoft's Python courses would destroy the
        choice and leave the vendor preference with nothing to prefer.
        """
        courses = [
            self._course("https://www.coursera.org/learn/python", "Coursera"),
            self._course("https://learn.microsoft.com/training/paths/python",
                         "Microsoft Learn"),
        ]

        self.assertEqual(len(deduplicate(courses)), 2)

    def test_identical_titles_alone_never_merge(self):
        """"Merely similar" is the mistake this guards against."""
        courses = [
            self._course("https://www.coursera.org/learn/a", "Coursera",
                         "Introduction to SQL"),
            self._course("https://learn.microsoft.com/b", "Microsoft Learn",
                         "Introduction to SQL"),
        ]

        self.assertEqual(len(deduplicate(courses)), 2)

    def test_a_reviewed_equivalence_is_the_only_way_across_providers(self):
        rehosted = "https://partner.example.com/learn/x"
        canonical = "Coursera|https://www.coursera.org/learn/x"
        CROSS_PROVIDER_EQUIVALENTS[rehosted] = canonical
        try:
            self.assertEqual(
                group_key(self._course(rehosted, "Partner")), canonical)
        finally:
            CROSS_PROVIDER_EQUIVALENTS.pop(rehosted)

    def test_the_default_equivalence_table_is_empty(self):
        """Inferring identity is the bug; an entry must be a human claim."""
        self.assertEqual(CROSS_PROVIDER_EQUIVALENTS, {})

    def test_cross_provider_overlap_is_reported_not_merged(self):
        courses = [
            self._course("https://www.coursera.org/learn/a", "Coursera",
                         "Introduction to SQL"),
            self._course("https://learn.microsoft.com/b", "Microsoft Learn",
                         "Introduction to SQL"),
            self._course("https://www.coursera.org/learn/c", "Coursera",
                         "Something Else"),
        ]

        report = cross_provider_report(courses)

        self.assertEqual(list(report), ["introduction to sql"])
        self.assertEqual(len(deduplicate(courses)), 3)


class VendorAuthorityTests(SimpleTestCase):
    """Authority is a Skill x Provider fact, not a badge on either one."""

    class FakeSap(CourseProvider):
        name = "SAP Learning"
        is_vendor = True
        vendor_for = ("SAP", "ABAP", "SAP HANA")

        def search(self, phrase):
            return []

    def setUp(self):
        self.index = authority_index([MicrosoftLearnProvider(), self.FakeSap()])

    def test_authority_is_per_technology_not_per_provider(self):
        """The case that motivated modelling this as a pair.

        Microsoft Learn genuinely publishes "Planning and Deploying SAP on
        Azure". That must not make Microsoft the reference for SAP.
        """
        self.assertTrue(is_authoritative("C#", "Microsoft Learn", self.index))
        self.assertFalse(is_authoritative("SAP", "Microsoft Learn", self.index))
        self.assertTrue(is_authoritative("SAP", "SAP Learning", self.index))

    def test_the_same_resource_ranks_differently_per_skill(self):
        resource = {"provider": "Microsoft Learn", "is_free": True,
                    "title": "Planning and Deploying SAP on Azure"}

        self.assertEqual(
            preference_rank("Azure", resource["provider"], self.index), VENDOR)
        self.assertEqual(
            preference_rank("SAP", resource["provider"], self.index), NON_VENDOR)

    def test_ranking_orders_but_never_filters(self):
        """Every resource passed in already earned its mapping.

        A non-vendor course is often the better one, and for most skills no
        vendor exists at all -- so ranking must never drop anything.
        """
        resources = [
            {"provider": "Coursera", "is_free": False, "title": "C# on Coursera"},
            {"provider": "Microsoft Learn", "is_free": True, "title": "C# on Learn"},
            {"provider": "Coursera", "is_free": True, "title": "Free C# course"},
        ]

        ranked = rank_resources("C#", resources, self.index)

        self.assertEqual(len(ranked), len(resources))
        self.assertEqual(ranked[0]["provider"], "Microsoft Learn")
        # Within non-vendor, free before paid.
        self.assertEqual([row["title"] for row in ranked[1:]],
                         ["Free C# course", "C# on Coursera"])

    def test_unstated_price_sorts_last_within_a_rank(self):
        resources = [
            {"provider": "Coursera", "is_free": None, "title": "Unknown price"},
            {"provider": "Coursera", "is_free": True, "title": "Free"},
            {"provider": "Coursera", "is_free": False, "title": "Paid"},
        ]

        self.assertEqual(
            [row["title"] for row in rank_resources("C#", resources, self.index)],
            ["Free", "Paid", "Unknown price"])

    def test_a_contested_skill_is_reported_rather_than_resolved_silently(self):
        class Impostor(CourseProvider):
            name = "Impostor"
            is_vendor = True
            vendor_for = ("C#",)

            def search(self, phrase):
                return []

        with self.assertLogs("resources.providers.authority", "WARNING") as logs:
            index = authority_index([MicrosoftLearnProvider(), Impostor()])

        self.assertEqual(index["C#"], "Microsoft Learn")
        self.assertIn("claimed by both", logs.output[0])


class MicrosoftLearnAdapterTests(SimpleTestCase):
    """Retrieval only. What the courses teach is the extractor's decision."""

    CATALOG = [
        {"url": "https://learn.microsoft.com/a", "title": "Get started with C#",
         "description": "Write your first C# code.", "provider": "Microsoft Learn",
         "type": "Module", "is_free": True},
        {"url": "https://learn.microsoft.com/b", "title": "Deploy to Azure",
         "description": "Also mentions C# briefly.", "provider": "Microsoft Learn",
         "type": "Module", "is_free": True},
        {"url": "https://learn.microsoft.com/c", "title": "Planning SAP on Azure",
         "description": "Run SAP workloads.", "provider": "Microsoft Learn",
         "type": "Learning Path", "is_free": True},
    ]

    def _provider(self):
        provider = MicrosoftLearnProvider()
        provider._catalog = list(self.CATALOG)
        return provider

    def test_title_matches_outrank_passing_mentions(self):
        """A module called "Get started with C#" teaches C#.

        One that mentions it in passing is usually about something else.
        """
        results = self._provider().search("C#")

        self.assertEqual([row["title"] for row in results],
                         ["Get started with C#", "Deploy to Azure"])

    def test_the_search_phrase_is_recorded_as_provenance_only(self):
        results = self._provider().search("C#")

        self.assertEqual(results[0]["discovered_via"], ["C#"])
        # Retrieval provenance, never a skill claim: nothing in the returned
        # row asserts what the course teaches.
        self.assertNotIn("skill_name", results[0])
        self.assertNotIn("skills", results[0])

    def test_vendor_ownership_does_not_restrict_retrieval(self):
        """Microsoft does not vendor SAP, and still publishes SAP material.

        The adapter returns it; whether it maps to SAP is decided later, from
        the course's own words.
        """
        results = self._provider().search("SAP")

        self.assertEqual([row["title"] for row in results],
                         ["Planning SAP on Azure"])

    def test_results_are_stable_between_runs(self):
        """An unchanged catalog must produce an unchanged seed diff."""
        first = self._provider().search("Azure")
        second = self._provider().search("Azure")

        self.assertEqual([row["url"] for row in first],
                         [row["url"] for row in second])
