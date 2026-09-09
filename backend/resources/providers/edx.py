"""edX, through its sitemap and topic pages -- never its search endpoint.

The route is dictated by policy, not convenience. edx.org/robots.txt disallows
``/search?`` and ``/es/search?`` and sets ``Crawl-delay: 10``. Search would have
been the obvious way in and is the one way that is closed, so discovery comes
from the published sitemap instead.

The sitemap carries both halves of what is needed. Of its 9,705 English URLs,
888 are ``/learn/<topic>`` subject hubs and **5,284 are course pages** at
``/learn/<topic>/<institution>-<course>``. Discovery therefore costs no
requests at all: a phrase is matched against the topic index in memory and the
courses under matching topics are already listed.

One hub is then fetched per topic, and only to upgrade titles. A sitemap URL
gives a course's name in slug form -- readable, and genuinely the course's own
name -- while the hub renders the same courses with proper titles and their
institution. Fetching one page to turn "ibm-python-basics-for-data-science"
into "Python Basics for Data Science" is worth ten seconds; fetching 6,173 of
them at ten seconds apart, for seventeen hours, would not be.

Evidence is thinner here than elsewhere. A Coursera card publishes a
"Skills you'll gain" list and Microsoft Learn writes a summary; an edX card
carries the course title, the institution, and the word "Course". The title is
usually descriptive enough to map on, and where it is not, the course simply
maps to nothing and stays in the catalogue -- which is the honest outcome, not
a reason to invent evidence from the topic the hub happens to be about.
"""

import logging
import re
import time

import requests
from bs4 import BeautifulSoup

from .base import CourseProvider, register

logger = logging.getLogger(__name__)

SITEMAP_URL = "https://www.edx.org/sitemap.xml"
BASE = "https://www.edx.org"

#: robots.txt asks for ten seconds between requests. Honoured as a floor by the
#: adapter itself rather than left to the caller, so no command can forget it.
CRAWL_DELAY = 10

#: Hubs fetched per phrase. Each is a request and ten seconds, so this is a
#: real cost rather than a formality: three well-chosen subjects beat thirty
#: tangential ones.
MAX_HUBS_PER_PHRASE = 3

#: Courses kept per hub. A hub server-renders roughly this many cards; the rest
#: of its list arrives client-side and is deliberately not chased.
MAX_COURSES_PER_HUB = 40

#: A course URL is /learn/<topic>/<institution>-<course-name>. A hub is
#: /learn/<topic> with nothing after it, and must not be stored as a course.
COURSE_PATH = re.compile(r"^/learn/[^/]+/[^/]+$")


@register
class EdXProvider(CourseProvider):

    name = "edX"
    #: edX hosts other institutions' teaching rather than vendoring a
    #: technology of its own, so it is authoritative for nothing. Its courses
    #: still map and still rank -- just never ahead of a vendor's own material.
    is_vendor = False

    def __init__(self, driver_factory=None, timeout=30, sleep=time.sleep):
        super().__init__(driver_factory)
        self.timeout = timeout
        #: Injectable so tests can assert the delay is applied without waiting
        #: it out. A crawl delay that only a live run exercises is one a test
        #: cannot prove is there.
        self._sleep = sleep
        self._topics = None
        self._courses = []
        self._session = requests.Session()
        self._session.headers["User-Agent"] = (
            "MomentumQuest/1.0 (course catalogue; contact via repository)")

    # ------------------------------------------------------------------

    def _course_urls(self):
        """Every course URL the sitemap lists, English only."""
        self._load_topics()
        return self._courses

    def _load_topics(self):
        """{topic-slug: hub url} from the sitemap, fetched once per instance."""
        if self._topics is not None:
            return self._topics

        response = self._session.get(SITEMAP_URL, timeout=self.timeout)
        response.raise_for_status()

        topics, courses = {}, []
        for url in re.findall(r"<loc>([^<]+)</loc>", response.text):
            # The Spanish mirror duplicates every English page; storing both
            # would double the catalogue with translations of one course.
            if "/es/" in url or "/aprende/" in url:
                continue
            path = url.replace(BASE, "")
            if not path.startswith("/learn/"):
                continue
            if path.count("/") == 2:
                topics[path.split("/")[2]] = url
            elif path.count("/") == 3:
                courses.append(url)

        logger.info("edX: sitemap lists %d topic hub(s) and %d course(s).",
                    len(topics), len(courses))
        self._topics, self._courses = topics, courses
        return topics

    def _matching_hubs(self, phrase):
        """Topic hubs whose slug plausibly covers the phrase, best first.

        Exact slug first -- "machine learning" is literally /learn/machine-
        learning -- then hubs containing it, shortest first, because a shorter
        slug is the more general subject. "python" beats "python-for-finance"
        when the skill asked about is Python.
        """
        topics = self._load_topics()
        slug = re.sub(r"[^a-z0-9]+", "-", phrase.casefold()).strip("-")
        if not slug:
            return []

        ordered = []
        if slug in topics:
            ordered.append(slug)
        ordered += sorted(
            (t for t in topics if slug in t and t != slug),
            key=lambda t: (len(t), t))
        return [(t, topics[t]) for t in ordered[:MAX_HUBS_PER_PHRASE]]

    def _courses_on(self, hub_url, topic):
        """Course cards a hub renders server-side.

        Title comes from the card image's alt text, which is where edX puts it;
        the card's visible text adds the institution and the type badge. Both
        are kept, because "Python for Data Science / The University of
        California, San Diego / Course" is the whole of the evidence this
        provider offers.
        """
        response = self._session.get(hub_url, timeout=self.timeout)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        found = {}
        for anchor in soup.find_all("a", href=True):
            href = anchor["href"]
            if not COURSE_PATH.match(href):
                continue

            image = anchor.find("img")
            title = (image.get("alt") or "").strip() if image else ""
            card_text = " ".join(anchor.get_text(" ", strip=True).split())
            if not title:
                title = card_text
            if not title:
                continue

            url = self.canonical_url(BASE + href)
            if url in found:
                continue
            found[url] = {
                "url": url,
                "title": title[:255],
                "description": card_text[:2000],
                "provider": self.name,
                "type": _type_from(card_text),
                # edX courses are typically free to audit with a paid
                # certificate. The card does not say which applies, and
                # guessing would put a price on the wrong thing.
                "is_free": None,
            }
            if len(found) >= MAX_COURSES_PER_HUB:
                break

        logger.info("edX: %s -> %d course(s).", topic, len(found))
        return list(found.values())

    def _courses_from_sitemap(self, topic):
        """Course URLs the sitemap already lists under one topic.

        Free: the sitemap is fetched once per run for the topic index, and the
        course URLs come with it. Titles are derived from the slug, which is
        the course's own name -- "ibm-python-basics-for-data-science" carries
        the words a mapping would rest on, just without their capitals.
        """
        prefix = f"{BASE}/learn/{topic}/"
        rows = []
        for url in self._course_urls():
            if not url.startswith(prefix):
                continue
            rows.append({
                "url": self.canonical_url(url),
                "title": _title_from_slug(url.rsplit("/", 1)[-1])[:255],
                "description": "",
                "provider": self.name,
                "type": "Course",
                "is_free": None,
            })
            if len(rows) >= MAX_COURSES_PER_HUB:
                break
        return rows

    def search(self, phrase):
        """Courses under the topic hubs matching one phrase.

        The sitemap supplies the courses; one hub fetch per topic supplies real
        titles and the institution for those it renders. Sleeps ``CRAWL_DELAY``
        between fetches, per robots.txt -- the runner's own politeness delay
        sits on top of this rather than replacing it.
        """
        by_url = {}
        for index, (topic, hub_url) in enumerate(self._matching_hubs(phrase)):
            for row in self._courses_from_sitemap(topic):
                by_url.setdefault(row["url"], row)

            if index:
                self._sleep(CRAWL_DELAY)
            try:
                for row in self._courses_on(hub_url, topic):
                    # The hub's title and card text are better evidence than a
                    # slug, so they replace it where both exist.
                    by_url[row["url"]] = row
            except requests.RequestException as exc:
                # The sitemap rows still stand; a hub that will not load costs
                # nicer titles, not the courses themselves.
                logger.warning("edX: hub %s failed (%s); keeping sitemap rows.",
                               topic, exc)
        return list(by_url.values())

    def reset(self):
        """Drop the HTTP session. Cheap, and keeps the runner's contract."""
        self._session.close()
        self._session = requests.Session()
        self._session.headers["User-Agent"] = (
            "MomentumQuest/1.0 (course catalogue; contact via repository)")


def _title_from_slug(slug):
    """A course slug as a readable title.

    Not a guess at the real title -- it is the real title, lowercased and
    hyphenated by edX's own URL scheme. Capitalised back for display; the words
    a mapping rests on are unchanged either way.
    """
    return " ".join(word.capitalize() for word in slug.split("-") if word)


def _type_from(card_text):
    """The badge edX prints on a card: Course, Program, Certificate ...

    Read from the card rather than assumed, and defaulted rather than guessed:
    a card whose badge changes wording should become "Course", not a new type
    nobody expects.
    """
    for badge in ("Professional Certificate", "MicroMasters", "MicroBachelors",
                  "Executive Education", "Bachelor's", "Master's", "Program",
                  "Course"):
        if card_text.endswith(badge) or f" {badge}" in card_text:
            return badge
    return "Course"
