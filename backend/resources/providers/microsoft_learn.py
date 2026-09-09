"""Microsoft Learn, through its published catalog API.

Chosen as the second provider because it covers demand Coursera does not reach
well and Malaysian adverts ask for constantly: .NET (51 adverts), C# (65),
Azure (100), Microsoft SQL Server (63). It is also the vendor for all four,
which makes its material the reference documentation rather than a third
party's interpretation.

An API rather than a browser, which matters more than it sounds. The catalog is
one JSON document, so this provider needs no Chrome, cannot be broken by a
markup change, and is unaffected by the WebDriver failures that cost the
Coursera runner an entire acquisition. It is fetched once per run and filtered
in memory: 265 phrases against a cached catalogue is 265 dictionary scans, not
265 requests.

What it does *not* do is decide skills. The catalog publishes its own subject
taxonomy and it is deliberately ignored -- a "roles: developer" tag is
Microsoft's classification, not this project's, and mixing the two would put
courses in the catalogue under names no Malaysian advert uses. Titles and
summaries go to the canonical extractor like every other provider's.
"""

import logging
import re

import requests
from bs4 import BeautifulSoup

from .base import CourseProvider, register

logger = logging.getLogger(__name__)

#: Everything learnable, not only certifications. The previous integration
#: asked for certifications alone and stored 51 rows; modules and learning
#: paths are where the teaching actually is, and they are free.
CATALOG_URL = ("https://learn.microsoft.com/api/catalog/"
               "?locale=en-us&type=modules,learningPaths,certifications,courses")

#: The catalog nests each kind under its own key.
COLLECTIONS = {
    "modules": "Module",
    "learningPaths": "Learning Path",
    "certifications": "Certification",
    "courses": "Course",
}

#: Parity with a paginating provider's first page: Coursera yields ~36 courses
#: per query, and a catalogue-backed provider that returned everything would
#: dominate the seed files without being more useful.
MAX_RESULTS_PER_PHRASE = 40

#: Modules and learning paths are free to work through; a certification is an
#: exam with a fee, and an instructor-led course is paid. Recorded as the
#: provider states it, and left None where it does not.
FREE_BY_TYPE = {
    "Module": True,
    "Learning Path": True,
    "Certification": False,
    "Course": None,
}


#: The catalog does not use one field for every kind of entry: modules and
#: learning paths carry ``summary``, while certifications carry none of it and
#: describe themselves in ``subtitle``. Measured on a stored batch: all 24
#: certifications had an empty description, leaving their titles as the only
#: evidence a mapping could rest on. Tried in order, first non-empty wins.
DESCRIPTION_FIELDS = ("summary", "subtitle", "short_description",
                      "description", "abstract")


#: Microsoft marks retirement in the entry's own prose -- "Warning This
#: certification and the renewal assessment are retired" -- rather than in a
#: structured field, so it is read from the text.
RETIRED = re.compile(
    r"\b(?:is|are|was|were|has been|have been)\s+retired\b|\bretirement\b",
    re.IGNORECASE)


def _is_retired(description):
    # Only the opening: a live certification may mention the retirement of an
    # older one it replaces, and that must not retire the replacement.
    return bool(RETIRED.search(description[:300]))


def _description(entry):
    """The provider's own words about one entry, as plain text.

    HTML is stripped rather than stored. Some entries arrive as
    "<p>This course provides students with...</p>", and markup in the evidence
    field helps nobody: the extractor reads it as text, a reviewer reads it in
    a seed diff, and a stray tag can only get between a term and its context.
    """
    for field in DESCRIPTION_FIELDS:
        raw = (entry.get(field) or "").strip()
        if not raw:
            continue
        text = (BeautifulSoup(raw, "html.parser").get_text(" ")
                if "<" in raw else raw)
        text = " ".join(text.split())
        if text:
            return text[:2000]
    return ""


@register
class MicrosoftLearnProvider(CourseProvider):

    name = "Microsoft Learn"
    is_vendor = True
    #: Authority is per-technology. Microsoft Learn is the vendor for these and
    #: emphatically not for SAP or Oracle, so the preference cannot leak.
    vendor_for = (
        ".NET", "ASP.NET", "ASP.NET Core", "C#", "VB.NET", "Azure",
        "Microsoft SQL Server", "Power BI", "PowerShell", "SharePoint",
        "Dynamics 365", "Microsoft 365", "Excel", "Entra ID", "Active Directory",
    )

    def __init__(self, driver_factory=None, timeout=20):
        super().__init__(driver_factory)
        self.timeout = timeout
        self._catalog = None

    # ------------------------------------------------------------------

    def _load_catalog(self):
        """Fetch and flatten the catalog once per provider instance."""
        if self._catalog is not None:
            return self._catalog

        response = requests.get(
            CATALOG_URL, timeout=self.timeout,
            headers={"User-Agent": "MomentumQuest/1.0 (course catalogue)"})
        response.raise_for_status()
        payload = response.json()

        items = []
        for key, kind in COLLECTIONS.items():
            for entry in payload.get(key, []) or []:
                url = entry.get("url") or ""
                title = (entry.get("title") or "").strip()
                if not url or not title:
                    continue
                if not url.startswith("http"):
                    url = f"https://learn.microsoft.com{url}"
                description = _description(entry)
                items.append({
                    "url": self.canonical_url(url),
                    "title": title[:255],
                    # The provider's prose is its evidence; unlike a Coursera
                    # card there is no skills-gained list, so this is what the
                    # extractor reads.
                    "description": description,
                    "provider": self.name,
                    "type": kind,
                    "is_free": FREE_BY_TYPE.get(kind),
                    # A retired certification is still in the catalog and must
                    # never be recommended: the exam no longer exists. Kept as
                    # evidence, excluded from mapping. 8 of 201 in the first
                    # validation batch, every one a certification.
                    "is_active": not _is_retired(description),
                })

        logger.info("Microsoft Learn: catalog holds %d item(s).", len(items))
        self._catalog = items
        return items

    def search_terms(self, skill_name, phrase):
        """Canonical name first, then the normalised phrase.

        This provider matches substrings against a catalog it holds in memory,
        so an expansion built for a search engine is a narrower query here, not
        a broader one. Measured: "C# programming" returns nothing, "C#" returns
        66 items; ".NET development" returns one, ".NET" returns 59.

        Both are tried, because the expansion is occasionally the better query
        -- "Root Cause Analysis" appears in summaries where "RCA" does not.
        """
        terms = [skill_name]
        if phrase and phrase != skill_name:
            terms.append(phrase)
        return terms

    def search(self, phrase):
        """The best catalog entries for one phrase, title matches first.

        Substring containment, not the skill matcher. This is retrieval: it
        decides what to look at, and the extractor decides what it means. A
        loose match here costs a course that maps to nothing, which is stored
        in the catalogue and is harmless.

        Ranked and capped, because this provider is a whole catalogue rather
        than a page of results. "Azure" appears in 772 of its 4,488 titles --
        genuine breadth, not noise -- and storing all of them would bury the
        useful ones, bloat the seed files past reviewing, and help no student
        who needs three courses rather than seven hundred. The cap is the
        rough size of one search page from a provider that paginates, so the
        catalogue stays comparable across providers.

        A title match outranks a summary mention: a module called "Get started
        with C#" teaches C#, while one that merely mentions it in passing is
        usually about something else.
        """
        needle = phrase.casefold()
        scored = []
        for item in self._load_catalog():
            in_title = needle in item["title"].casefold()
            in_summary = needle in item["description"].casefold()
            if not (in_title or in_summary):
                continue
            row = dict(item)
            row["discovered_via"] = [phrase]
            scored.append((0 if in_title else 1, row))

        # Stable within a rank, so two runs over an unchanged catalog return
        # the same courses and the seed diff stays empty.
        scored.sort(key=lambda pair: (pair[0], pair[1]["url"]))
        return [row for _, row in scored[:MAX_RESULTS_PER_PHRASE]]
