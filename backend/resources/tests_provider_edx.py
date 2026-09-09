"""The edX adapter: the route policy forces, and the shape it produces.

Hermetic. The sitemap is a fixture rather than a fetch, so these run without
network and cannot be broken by edX re-publishing its catalogue.

The most important assertion here is a negative one: this adapter must never
construct a ``/search?`` URL, because robots.txt disallows that path. A test
that only checked the happy path would pass just as well against an
implementation that fetched the forbidden endpoint.
"""

import re

from django.test import SimpleTestCase

from .providers.edx import CRAWL_DELAY, COURSE_PATH, EdXProvider, _title_from_slug

SITEMAP = """<?xml version="1.0" encoding="UTF-8"?>
<urlset>
<url><loc>https://www.edx.org/learn/python</loc></url>
<url><loc>https://www.edx.org/es/learn/python</loc></url>
<url><loc>https://www.edx.org/learn/python-for-finance</loc></url>
<url><loc>https://www.edx.org/learn/machine-learning</loc></url>
<url><loc>https://www.edx.org/learn/python/ibm-python-basics-for-data-science</loc></url>
<url><loc>https://www.edx.org/learn/python/harvard-university-cs50s-introduction</loc></url>
<url><loc>https://www.edx.org/es/learn/python/ibm-python-basics-for-data-science</loc></url>
<url><loc>https://www.edx.org/aprende/python/algun-curso</loc></url>
<url><loc>https://www.edx.org/masters/online-masters-in-data-science</loc></url>
</urlset>"""


class FakeResponse:
    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        pass


class RecordingSession:
    """Stands in for requests.Session and remembers every URL asked for."""

    def __init__(self, pages=None):
        self.requested = []
        self.pages = pages or {}
        self.headers = {}

    def get(self, url, timeout=None):
        self.requested.append(url)
        if url.endswith("/sitemap.xml"):
            return FakeResponse(SITEMAP)
        return FakeResponse(self.pages.get(url, "<html></html>"))

    def close(self):
        pass


class EdXSitemapTests(SimpleTestCase):

    def _provider(self, pages=None):
        provider = EdXProvider(sleep=lambda seconds: None)
        provider._session = RecordingSession(pages)
        return provider

    def test_the_sitemap_separates_subject_hubs_from_courses(self):
        """/learn/<topic> is a subject; /learn/<topic>/<course> is a course.

        Storing a hub as a course would put "Python" in the catalogue as
        something to enrol in.
        """
        provider = self._provider()

        topics = provider._load_topics()

        self.assertEqual(set(topics), {"python", "python-for-finance",
                                       "machine-learning"})
        self.assertEqual(len(provider._course_urls()), 2)

    def test_the_spanish_mirror_is_excluded(self):
        """Every English page is duplicated under /es/ and /aprende/.

        Keeping both would double the catalogue with translations of one
        course, and the extractor would map the Spanish copy on its English
        title.
        """
        provider = self._provider()
        provider._load_topics()

        for url in provider._course_urls():
            self.assertNotIn("/es/", url)
            self.assertNotIn("/aprende/", url)

    def test_hub_paths_are_not_mistaken_for_courses(self):
        self.assertFalse(COURSE_PATH.match("/learn/python"))
        self.assertTrue(COURSE_PATH.match("/learn/python/ibm-python-basics"))

    def test_the_exact_subject_outranks_a_narrower_one(self):
        """"python" is the subject asked about; "python-for-finance" is not.

        Shortest-first after the exact match, because a shorter slug is the
        more general subject.
        """
        provider = self._provider()

        hubs = [topic for topic, _ in provider._matching_hubs("Python")]

        self.assertEqual(hubs[0], "python")
        self.assertIn("python-for-finance", hubs)

    def test_a_phrase_with_spaces_becomes_a_slug(self):
        provider = self._provider()

        hubs = [topic for topic, _ in provider._matching_hubs("Machine Learning")]

        self.assertEqual(hubs, ["machine-learning"])

    def test_courses_come_from_the_sitemap_without_extra_requests(self):
        """Discovery is free; only title enrichment costs a fetch."""
        provider = self._provider()
        provider._load_topics()
        before = len(provider._session.requested)

        rows = provider._courses_from_sitemap("python")

        self.assertEqual(len(rows), 2)
        self.assertEqual(len(provider._session.requested), before)

    def test_a_slug_becomes_the_courses_own_name(self):
        """Not a guess at the title -- edX's own words, hyphenated by its URLs."""
        self.assertEqual(
            _title_from_slug("ibm-python-basics-for-data-science"),
            "Ibm Python Basics For Data Science")


class EdXPolicyComplianceTests(SimpleTestCase):
    """robots.txt disallows /search?; the adapter must never go there."""

    def test_no_request_is_ever_made_to_the_search_endpoint(self):
        provider = EdXProvider(sleep=lambda seconds: None)
        session = RecordingSession()
        provider._session = session

        provider.search("Python")

        self.assertTrue(session.requested, "the adapter made no requests at all")
        for url in session.requested:
            self.assertNotIn("/search", url)

    def test_only_the_sitemap_and_hub_pages_are_requested(self):
        provider = EdXProvider(sleep=lambda seconds: None)
        session = RecordingSession()
        provider._session = session

        provider.search("Python")

        for url in session.requested:
            self.assertTrue(
                url.endswith("/sitemap.xml") or re.match(
                    r"^https://www\.edx\.org/learn/[^/]+$", url),
                f"unexpected URL fetched: {url}")

    def test_the_crawl_delay_is_the_one_robots_asks_for(self):
        """Ten seconds, held by the adapter rather than left to the caller."""
        self.assertEqual(CRAWL_DELAY, 10)

    def test_the_adapter_sleeps_between_hub_fetches(self):
        """A delay that is configured but never applied is not a delay."""
        slept = []
        provider = EdXProvider(sleep=slept.append)
        provider._session = RecordingSession()

        # "Python" matches two hubs, so exactly one delay falls between them.
        provider.search("Python")

        self.assertEqual(slept, [CRAWL_DELAY])


class EdXEvidenceTests(SimpleTestCase):
    """What the adapter returns is evidence, never a skill claim."""

    HUB = """<html><body>
      <a href="/learn/python/ibm-python-basics-for-data-science">
        <img alt="Python Basics for Data Science"/>
        <div>Python Basics for Data Science</div><div>IBM</div><div>Course</div>
      </a>
    </body></html>"""

    def test_a_hub_upgrades_a_slug_title_to_the_real_one(self):
        provider = EdXProvider(sleep=lambda seconds: None)
        provider._session = RecordingSession(
            {"https://www.edx.org/learn/python": self.HUB})

        rows = {row["url"]: row for row in provider.search("Python")}
        upgraded = rows[
            "https://www.edx.org/learn/python/ibm-python-basics-for-data-science"]

        self.assertEqual(upgraded["title"], "Python Basics for Data Science")
        self.assertIn("IBM", upgraded["description"])

    def test_a_course_the_hub_does_not_render_keeps_its_sitemap_row(self):
        """A hub renders a handful of cards; the sitemap lists them all."""
        provider = EdXProvider(sleep=lambda seconds: None)
        provider._session = RecordingSession(
            {"https://www.edx.org/learn/python": self.HUB})

        rows = {row["url"]: row for row in provider.search("Python")}

        self.assertIn(
            "https://www.edx.org/learn/python/harvard-university-cs50s-introduction",
            rows)

    def test_a_failed_hub_costs_titles_and_not_courses(self):
        """The sitemap rows stand on their own."""
        import requests

        class FailingSession(RecordingSession):
            def get(self, url, timeout=None):
                if url.endswith("/sitemap.xml"):
                    return super().get(url, timeout)
                raise requests.RequestException("hub unavailable")

        provider = EdXProvider(sleep=lambda seconds: None)
        provider._session = FailingSession()

        rows = provider.search("Python")

        self.assertEqual(len(rows), 2)

    def test_nothing_returned_asserts_what_a_course_teaches(self):
        provider = EdXProvider(sleep=lambda seconds: None)
        provider._session = RecordingSession()

        for row in provider.search("Python"):
            self.assertNotIn("skill_name", row)
            self.assertNotIn("skills", row)
            # Price is unknown here and must stay unknown: edX audits are free
            # and certificates are not, and the card does not say which.
            self.assertIsNone(row["is_free"])
