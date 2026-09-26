"""Why a crawl stopped, and whether the source said it had run out of pages.

A scrape that finishes without crashing says nothing about coverage. It may
have walked the whole result set, or stopped at its own page ceiling, or been
turned away on page three -- and every one of those ends with a tidy summary and
a pile of adverts. Reporting them the same way is how a third of a market
becomes "the market".

So the crawl records *why* it stopped, and only one of those reasons means the
configured search was traversed to its end.

The hard part is not detecting the last page; it is refusing to detect it by
accident. An empty page looks identical whether JobStreet ran out of results,
Cloudflare intervened, the DOM failed to render, or the markup changed under us.
Treating "no job cards" as completion would quietly convert every one of those
into a claim of a full traversal. So an empty page only ends pagination once the
page has been confirmed to have loaded as a JobStreet results page; anything
else is a failure, and failures never exhaust anything.

The same asymmetry governs the next-page check, and the first version of this
module broke it. It concluded that a pagination block containing no *recognised*
next control must be the last page -- so the first real run, against markup whose
next arrow is not named what this module expected, reported PAGINATION_EXHAUSTED
on page one of a search thousands of adverts deep. A wrong "there is more" costs
one fetch of an empty page, which the empty-page signal then ends correctly. A
wrong "that was the end" costs the truth, silently, in the direction that
flatters the run. Nothing here may infer the end of pagination from the absence
of markup; it has to be told, by a control that says it is disabled or by
numbered links that stop at the page being read.

``has_next_page`` therefore returns None whenever it cannot tell, which leaves
the decision to fetching the next page and finding it empty. Saying nothing is a
worse answer than a correct one and a far better answer than a confident wrong
one.

Kept free of Django imports so the detection can be tested against saved markup
without a database. BeautifulSoup is imported inside the functions rather than at
module scope, because job_listings.models reads the stop-reason vocabulary from
here and has no business pulling a scraping library into every process that
imports a model.
"""

import re

# ---------------------------------------------------------------- stop reasons

#: The crawl reached the last page the source offered. The only value that means
#: the configured search was covered end to end.
PAGINATION_EXHAUSTED = "PAGINATION_EXHAUSTED"

#: The crawl hit its own --max-pages ceiling. There may be more; nobody looked.
MAX_PAGES_REACHED = "MAX_PAGES_REACHED"

#: The source refused a page. Says nothing about how many pages exist.
BLOCKED = "BLOCKED"

#: A page did not load, or did not load as a results page.
FAILED = "FAILED"

#: The operator stopped the run. Distinct from FAILED because nothing went
#: wrong: the pages already crawled are saved and sound, and the run can be
#: resumed from the page after the last one recorded. A run that died of a dead
#: browser and a run someone deliberately paused call for different responses,
#: so the row says which it was.
INTERRUPTED = "INTERRUPTED"

#: Recorded before this distinction existed. Not a measurement.
UNKNOWN = "UNKNOWN"

STOP_REASONS = (PAGINATION_EXHAUSTED, MAX_PAGES_REACHED, BLOCKED, FAILED,
                INTERRUPTED, UNKNOWN)


# ------------------------------------------------------------- fetch outcomes

FETCH_OK = "ok"
FETCH_BLOCKED = "blocked"
FETCH_FAILED = "failed"


# ------------------------------------------------------- results page markers

#: Markup that only a JobStreet search-results page carries. Several, because
#: matching on one attribute makes a single markup change indistinguishable
#: from "the search returned nothing" -- and that mistake reads as completion.
RESULTS_MARKERS = (
    '[data-automation="searchResults"]',
    '[data-automation="searchResultsHeader"]',
    '[data-automation="totalJobsCount"]',
    '[data-automation="jobListing"]',
    '[data-automation="normalJob"]',
    '[data-automation="pageNumber"]',
    '[data-automation="page-next"]',
    '[data-automation="noJobsFound"]',
    '[data-automation="zeroResults"]',
)

#: A results page that is legitimately empty says so in words. Lowercase; the
#: page is folded before matching.
EMPTY_RESULT_PHRASES = (
    "no jobs found",
    "no matching jobs",
    "we couldn't find any jobs",
    "we could not find any jobs",
    "0 jobs found",
    "tiada pekerjaan",
)

#: Ways a "next page" control is spelled. Only a control found here can end
#: pagination, and only by saying it is disabled.
#:
#: rel~="next" leads because it is the one signal that is neither branded nor
#: translated. JobStreet's own next link is named data-automation="page-2" --
#: labelled by the page it goes to rather than as a next control -- so the
#: attribute this module would naturally look for does not exist, and the only
#: other thing identifying it is aria-label="Next", which is English. The word
#: match matters too: the attribute is rel="nofollow next", and [rel="next"]
#: tests the whole value and misses it.
NEXT_CONTROL_SELECTORS = (
    '[data-automation="page-next"]',
    '[data-automation="pagination-next"]',
    '[data-automation="nextPage"]',
    '[rel~="next"]',
    '[aria-label="Next"]',
    '[aria-label="Next page"]',
    '[aria-label="Go to next page"]',
)

#: Numbered page links, e.g. data-automation="page-4". The number is the one
#: piece of pagination state that can be compared against the page being read.
NUMBERED_PAGE_SELECTOR = '[data-automation^="page-"]'
_PAGE_NUMBER = re.compile(r"^page-(\d+)$")


def _soup(html):
    from bs4 import BeautifulSoup

    return BeautifulSoup(html, "html.parser")


def is_results_page(html):
    """Did this load as a JobStreet results page, empty or not?

    The gate in front of every "there were no jobs, so that was the last page"
    conclusion. A blocked page, an error page and a changed layout all fail it.
    """
    if not html:
        return False

    soup = _soup(html)
    if any(soup.select_one(marker) for marker in RESULTS_MARKERS):
        return True

    # A page whose markers all changed can still be recognised by what it says.
    text = soup.get_text(" ").lower()
    return any(phrase in text for phrase in EMPTY_RESULT_PHRASES)


def has_next_page(html, current_page=None):
    """True, False, or None when the markup does not support an answer.

    None is a real answer and the reason this is not a bool. Only two things
    may return False: a next-page control that states it is disabled, and a set
    of numbered page links that stops at ``current_page``. Everything else --
    unfamiliar markup, a missing control, a pagination block this module does
    not recognise -- is None, because inferring the end of a search from markup
    we failed to parse is how a one-page crawl reports that it covered the
    market.
    """
    if not html:
        return None

    soup = _soup(html)

    control = _next_control(soup)
    if control is not None:
        return _is_enabled(control)

    # No control found. Numbered links can still answer it, but only against
    # the page actually being read -- "there is a link to page 5" means nothing
    # without knowing whether this is page 4 or page 5.
    numbers = _page_numbers(soup)
    if numbers and current_page is not None:
        return max(numbers) > current_page

    return None


def _next_control(soup):
    for selector in NEXT_CONTROL_SELECTORS:
        control = soup.select_one(selector)
        if control is not None:
            return control
    return None


def _page_numbers(soup):
    """Page numbers offered by numbered pagination links."""
    numbers = set()
    for tag in soup.select(NUMBERED_PAGE_SELECTOR):
        match = _PAGE_NUMBER.match(tag.get("data-automation", ""))
        if match:
            numbers.add(int(match.group(1)))
    return numbers


def _is_enabled(control):
    """Is this next-page control usable?

    Biased towards True on anything ambiguous, for the reason in the module
    docstring: a control wrongly read as live costs one fetch of an empty page,
    a control wrongly read as dead ends the crawl and calls a partial traversal
    complete.
    """
    if control.get("aria-disabled") == "true":
        return False
    if control.has_attr("disabled"):
        return False
    if control.name in ("a", "link") and not control.get("href"):
        return False
    return True
