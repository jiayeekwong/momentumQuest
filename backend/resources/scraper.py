import logging
import random
import re
import time
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

HEADERS = {"User-Agent": USER_AGENT}

# Phrases that indicate a bot-detection page — mirrors scraper.py
BOT_INDICATORS = [
    "access denied", "blocked", "captcha", "cloudflare",
    "just a moment", "verify you are human", "403 forbidden",
]


# ============================================================
# Shared helpers — mirror scraper.py patterns
# ============================================================

def random_delay(min_seconds=2, max_seconds=5):
    """Random sleep to simulate human browsing."""
    time.sleep(random.uniform(min_seconds, max_seconds))


def is_blocked(page_source, page_title=""):
    """Return True if the page looks like a bot-detection wall."""
    combined = (page_source[:5000] + page_title).lower()
    return any(indicator in combined for indicator in BOT_INDICATORS)


#: Resolved once per process. ChromeDriverManager().install() reaches
#: googlechromelabs.github.io to check for a newer driver, and the runner now
#: rebuilds the browser deliberately after a failure -- so without caching,
#: every recovery attempt would depend on the very network that just failed.
_CHROMEDRIVER_PATH = None


def _chromedriver_path():
    global _CHROMEDRIVER_PATH
    if _CHROMEDRIVER_PATH is None:
        _CHROMEDRIVER_PATH = ChromeDriverManager().install()
    return _CHROMEDRIVER_PATH


def create_driver():
    """
    Headless Chrome with full anti-detection stack.
    Mirrors create_driver() in scraper.py exactly, plus:
      - implicitly_wait(3) from coursera-scraper (TIME_TO_WAIT = 3)
    """
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument(f"--user-agent={USER_AGENT}")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    service = Service(_chromedriver_path())
    driver = webdriver.Chrome(service=service, options=options)

    # Hide navigator.webdriver — same CDP trick as scraper.py
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    })

    # coursera-scraper uses implicitly_wait(TIME_TO_WAIT=3); job scraper uses 10.
    # 10 is safer for slow SPAs.
    driver.implicitly_wait(10)
    return driver


def safe_load_page(driver, url, retries=3):
    """
    Load a URL with retries, gradual human-like scroll, and bot-detection check.
    Mirrors safe_get_page() in scraper.py.
    Returns page_source on success, "" on failure.
    """
    for attempt in range(1, retries + 1):
        try:
            driver.get(url)
            random_delay(3, 6)

            # 3-step gradual scroll — simulates a human reading the page
            for i in range(1, 4):
                driver.execute_script(
                    f"window.scrollTo(0, document.body.scrollHeight * {i / 3});"
                )
                random_delay(0.5, 1.5)

            if is_blocked(driver.page_source, driver.title):
                logger.warning("Bot detection on attempt %d for %s", attempt, url)
                time.sleep(5 * attempt)
                continue

            return driver.page_source

        except Exception as exc:
            logger.warning("Attempt %d/%d failed for %s: %s", attempt, retries, url, exc)
            if attempt < retries:
                random_delay(3, 6)

    logger.error("All %d attempts failed for %s", retries, url)
    return ""


def quit_driver(driver):
    """Safely quit driver — wraps the call so a dead ChromeDriver won't crash the scraper."""
    try:
        driver.quit()
    except Exception:
        pass


# Context words required for single-character skills to avoid false positives.
# A course title must contain at least one of these words alongside the skill
# letter, otherwise standalone "R" in breadcrumbs/badges/labels will match.
_SINGLE_CHAR_CONTEXT: dict[str, set[str]] = {
    'R': {'programming', 'statistical', 'statistics', 'data', 'language',
          'tidyverse', 'ggplot', 'cran', 'shiny', 'analytics', 'r studio',
          'rstudio', 'dplyr'},
    'C': {'programming', 'language', 'embedded', 'systems', 'c language',
          'pointer', 'memory', 'struct'},
}


def skill_matches_title(skill_name, title):
    """
    Word-boundary match so single-char skills like 'R' or 'C' don't match
    every word that contains those letters (e.g. 'React', 'Framework').

    For ambiguous single-character skills (R, C) a context-word check is
    applied on top of the boundary match so that lone "R" characters that
    appear as UI badges, trademark symbols, or breadcrumb fragments are
    not treated as the R programming language.
    """
    if len(skill_name) == 1:
        # Case-sensitive + exclude trademark (R) / (C) via lookbehind/lookahead.
        pattern = r'(?<!\()\b' + re.escape(skill_name) + r'\b(?!\))'
        if not re.search(pattern, title):
            return False
        # Additional context check for known ambiguous single-char skills.
        context_words = _SINGLE_CHAR_CONTEXT.get(skill_name.upper())
        if context_words:
            lower_title = title.lower()
            return any(kw in lower_title for kw in context_words)
        return True
    pattern = r'\b' + re.escape(skill_name) + r'\b'
    return bool(re.search(pattern, title, re.IGNORECASE))


# ============================================================
# freeCodeCamp — catalog page, Selenium required
# ============================================================
#
# Scrapes https://www.freecodecamp.org/catalog which lists every course as a
# structured card:
#   <a class="catalog-item" href="/learn/...">
#     <div class="block-label">Python</div>   ← category = skill name
#     <h3>Learn Python for Beginners</h3>     ← course title
#     <p>Description...</p>
#   </a>
#
# Strategy:
#   1. Extract the category label (block-label) from each card.
#   2. Match the label directly to a DB skill (case-insensitive) — most
#      reliable because "Python", "JavaScript", "CSS", "Git", etc. are exact
#      DB skill names.
#   3. Fall back to word-boundary title matching for categories that don't
#      directly match a DB skill (e.g., "Computer Science" → title may contain
#      "Data Structures" which matches a DB skill).
#   4. Skip courses that match neither.

FCC_CATALOG_URL = "https://www.freecodecamp.org/catalog"


def scrape_freecodecamp(skill_names):
    results = []
    driver  = create_driver()

    # Build a lookup map: lowercase skill name → original casing in DB
    skill_lookup = {s.lower(): s for s in skill_names}

    try:
        page_source = safe_load_page(driver, FCC_CATALOG_URL)
        if not page_source:
            logger.error("freeCodeCamp: catalog page failed to load after retries.")
            return results

        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "a.catalog-item"))
        )
        random_delay(2, 4)

        soup      = BeautifulSoup(driver.page_source, "html.parser")
        seen_urls = set()

        for card in soup.select("a.catalog-item[href]"):
            href = card["href"]
            url  = href if href.startswith("http") else f"https://www.freecodecamp.org{href}"
            if url in seen_urls:
                continue

            category_tag = card.select_one("div.block-label")
            title_tag    = card.select_one("h3")

            category = category_tag.get_text(strip=True) if category_tag else ""
            title    = title_tag.get_text(strip=True)    if title_tag    else ""

            if not title:
                continue

            # Step 1 — category label is the primary skill signal
            matched_skill = skill_lookup.get(category.lower())

            # Step 2 — fall back to word-boundary title matching
            if not matched_skill:
                for skill_name in skill_names:
                    if skill_matches_title(skill_name, title):
                        matched_skill = skill_name
                        break

            if not matched_skill:
                continue

            results.append({
                "skill_name": matched_skill,
                "title":      title[:255],
                "platform":   "freeCodeCamp",
                "url":        url,
                "type":       "Course",
            })
            seen_urls.add(url)

        logger.info("freeCodeCamp: %d resources matched.", len(results))

    except Exception as exc:
        logger.error("freeCodeCamp scrape failed: %s", exc)

    finally:
        quit_driver(driver)

    return results


# ============================================================
# Microsoft Learn — public JSON catalog API (no Selenium)
# ============================================================

MS_CATALOG_API = "https://learn.microsoft.com/api/catalog/?type=certifications&locale=en-us"


def scrape_microsoft_learn(skill_names):
    results = []

    for attempt in range(1, 4):
        try:
            resp = requests.get(MS_CATALOG_API, headers=HEADERS, timeout=15)
            resp.raise_for_status()
            certifications = resp.json().get("certifications", [])

            for cert in certifications:
                title = cert.get("title", "")
                url   = cert.get("url", "")
                if not title or not url:
                    continue
                if not url.startswith("http"):
                    url = f"https://learn.microsoft.com{url}"

                for skill_name in skill_names:
                    if skill_matches_title(skill_name, title):
                        results.append({
                            "skill_name": skill_name,
                            "title":      title[:255],
                            "platform":   "Microsoft Learn",
                            "url":        url,
                            "type":       "Certification",
                        })
                        break

            logger.info("Microsoft Learn: %d resources matched.", len(results))
            break

        except Exception as exc:
            logger.warning("Microsoft Learn attempt %d/3 failed: %s", attempt, exc)
            if attempt < 3:
                time.sleep(2 ** attempt)

    return results


# ============================================================
# Cisco NetAcad — Angular SPA, Selenium required
# ============================================================

CISCO_CATALOG_URL = "https://www.netacad.com/catalogs/learn"

# URL segments that identify non-course pages on Cisco NetAcad.
CISCO_NON_COURSE_SEGS = [
    "/news/", "/blog/", "/stories/",
    "/press-releases/", "/articles/", "/announcements/",
]

# Valid URL path prefixes that indicate an actual Cisco course or learning path.
CISCO_COURSE_SEGS = ["/courses/", "/course/", "/learn/", "/catalog/"]


def scrape_cisco_netacad(skill_names):
    results = []
    driver  = create_driver()

    try:
        page_source = safe_load_page(driver, CISCO_CATALOG_URL)
        if not page_source:
            logger.error("Cisco NetAcad: page failed to load after retries.")
            return results

        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "a[href]"))
        )
        random_delay(3, 5)

        soup = BeautifulSoup(driver.page_source, "html.parser")

        # Strip nav / header / footer so we never pick up navigation links.
        for el in soup.find_all(["nav", "header", "footer"]):
            el.decompose()

        seen_urls = set()

        for link in soup.find_all("a", href=True):
            href = link["href"]

            # Positive filter: must contain a course path segment.
            if not any(seg in href for seg in CISCO_COURSE_SEGS):
                continue
            # Negative filter: exclude news/blog/announcements.
            if any(seg in href for seg in CISCO_NON_COURSE_SEGS):
                continue

            # Prefer the first heading inside the card link — avoids concatenating
            # category labels, descriptions, and other child text into the title.
            heading = link.find(["h2", "h3", "h4", "h5", "h6"])
            if heading:
                title = heading.get_text(strip=True)
            else:
                title = link.get_text(separator=" ", strip=True)

            # Skip too-short or suspiciously long strings (nav text / full card dump).
            if not title or len(title) < 5 or len(title) > 120:
                continue

            url = href if href.startswith("http") else f"https://www.netacad.com{href}"
            if url in seen_urls:
                continue

            for skill_name in skill_names:
                if skill_matches_title(skill_name, title):
                    results.append({
                        "skill_name": skill_name,
                        "title":      title[:255],
                        "platform":   "Cisco NetAcad",
                        "url":        url,
                        "type":       "Badge",
                    })
                    seen_urls.add(url)
                    break

        logger.info("Cisco NetAcad: %d resources matched.", len(results))

    except Exception as exc:
        logger.error("Cisco NetAcad scrape failed: %s", exc)

    finally:
        quit_driver(driver)

    return results


# ============================================================
# Codecademy — catalog page, Selenium required
# ============================================================

CODECADEMY_CATALOG_URL = "https://www.codecademy.com/catalog/all"


def scrape_codecademy(skill_names):
    results = []
    driver  = create_driver()

    try:
        page_source = safe_load_page(driver, CODECADEMY_CATALOG_URL)
        if not page_source:
            logger.error("Codecademy: page failed to load after retries.")
            return results

        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'a[href*="/learn/"]'))
        )
        random_delay(3, 5)

        soup = BeautifulSoup(driver.page_source, "html.parser")

        for el in soup.find_all(["nav", "header", "footer"]):
            el.decompose()

        seen_urls = set()

        for link in soup.find_all("a", href=True):
            href = link["href"]
            if "/learn/" not in href:
                continue

            heading = link.find(["h2", "h3", "h4", "h5", "h6"])
            if heading:
                title = heading.get_text(strip=True)
            else:
                title = link.get_text(separator=" ", strip=True)

            if not title or len(title) < 5 or len(title) > 120:
                continue

            url = href if href.startswith("http") else f"https://www.codecademy.com{href}"
            if url in seen_urls:
                continue

            resource_type = "Career Path" if "/paths/" in href else "Course"

            for skill_name in skill_names:
                if skill_matches_title(skill_name, title):
                    results.append({
                        "skill_name": skill_name,
                        "title":      title[:255],
                        "platform":   "Codecademy",
                        "url":        url,
                        "type":       resource_type,
                    })
                    seen_urls.add(url)
                    break

        logger.info("Codecademy: %d resources matched.", len(results))

    except Exception as exc:
        logger.error("Codecademy scrape failed: %s", exc)

    finally:
        quit_driver(driver)

    return results


# ============================================================
# Coursera — search page scraping via Selenium
# ============================================================
#
# Mirrors the approach from github.com/lorenzowne/coursera-scraper:
#   1. Warm up on the homepage to establish a session.
#   2. For each JobCategory query, load /search?query={term}.
#   3. Wait for course links, then extract /learn/ and /specializations/ hrefs.
#
# Queries are sourced from JobCategory (populated by the job scraper) so we
# search by role (e.g. "Data Analyst") rather than individual skills — fewer
# requests and better relevance.
#
# coursera-scraper reference timing constants:
#   TIME_TO_WAIT      = 3   (implicitly_wait — already in create_driver)
#   TIME_TO_NEXT_PAGE = 10  (delay between searches)

COURSERA_SEARCH_URL = "https://www.coursera.org/search?query={query}&language=English"


def scrape_coursera(skill_names):
    results   = []
    seen_urls = set()
    driver    = create_driver()

    try:
        from scrape_jobs.models import JobCategory
        queries = list(JobCategory.objects.values_list("category_name", flat=True))
    except Exception:
        queries = []

    if not queries:
        logger.warning("Coursera: no JobCategory records found, skipping.")
        quit_driver(driver)
        return results

    # Warm up on the homepage first — same session-establishment step used by
    # coursera-scraper before issuing search queries.
    logger.info("Coursera: warming up session on homepage ...")
    safe_load_page(driver, "https://www.coursera.org/", retries=2)
    random_delay(4, 7)

    for query in queries:
        search_url  = COURSERA_SEARCH_URL.format(query=quote_plus(query))
        page_source = safe_load_page(driver, search_url, retries=2)
        if not page_source:
            logger.warning("Coursera: failed to load search for '%s'", query)
            random_delay(5, 9)
            continue

        # Wait for at least one course link — same pattern as coursera-scraper's
        # implicit wait before reading results.
        try:
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, 'a[href*="/learn/"], a[href*="/specializations/"]')
                )
            )
        except Exception:
            logger.warning("Coursera: no course links appeared for '%s'", query)
            random_delay(3, 6)
            continue

        random_delay(2, 4)
        soup = BeautifulSoup(driver.page_source, "html.parser")

        for el in soup.find_all(["nav", "header", "footer"]):
            el.decompose()

        for link in soup.find_all("a", href=True):
            href = link["href"]
            is_course = "/learn/" in href
            is_spec   = "/specializations/" in href
            if not is_course and not is_spec:
                continue

            heading = link.find(["h2", "h3", "h4", "h5", "h6"])
            if heading:
                title = heading.get_text(strip=True)
            else:
                title = link.get_text(separator=" ", strip=True)

            if not title or len(title) < 5 or len(title) > 120:
                continue

            url = href if href.startswith("http") else f"https://www.coursera.org{href}"
            if url in seen_urls:
                continue

            resource_type = "Professional Certificate" if is_spec else "Course"

            for skill_name in skill_names:
                if skill_matches_title(skill_name, title):
                    results.append({
                        "skill_name": skill_name,
                        "title":      title[:255],
                        "platform":   "Coursera",
                        "url":        url,
                        "type":       resource_type,
                    })
                    seen_urls.add(url)
                    break

        # coursera-scraper waits TIME_TO_NEXT_PAGE = 10 s between page loads.
        random_delay(8, 12)

    logger.info("Coursera: %d resources found.", len(results))

    quit_driver(driver)
    return results


# ============================================================
# Coursera — one search per skill, first page only
# ============================================================
#
# Two earlier designs failed here, and the reasons are worth keeping because
# they constrain what is possible.
#
# The original scrape_coursera above searched 12 *job-role* names, read the
# first page of each, and discarded a course unless a Skill name appeared in
# its title. 59 rows survived, covering 25 skills.
#
# The replacement walked Coursera's own Computer Science, Information
# Technology and Data Science categories and followed ``&page=N`` to the end.
# It found 108 courses -- exactly 36 x 3 -- because Coursera does not paginate
# by URL. Measured against the live site, page 2 returns a strict subset of
# page 1:
#
#     page 1: 36 urls;  page 2: 24 urls;  new on page 2: 0
#
# and the same held for ``?query=&page=``, ``?topic=&page=`` and
# ``&sortBy=BEST_MATCH``. So the pagination loop is gone rather than disabled:
# code that loops over pages implies a capability the site does not offer, and
# the next reader would have had to rediscover that the hard way.
#
# Breadth therefore has to come from more queries, not deeper pages. One search
# per skill puts that skill's courses on the only page available -- a search for
# "SAP ABAP" returns the ABAP courses at the top -- which is what neither
# earlier design ever asked for.
#
# What the search phrase is, and what the course is then mapped to, are kept
# strictly apart. The phrase is a retrieval device; mapping is decided
# afterwards from the course's own text by map_catalogue_to_skills. A course is
# never filed under the skill that found it merely because that skill found it.

COURSERA_SKILL_SEARCH_URL = (
    "https://www.coursera.org/search?query={query}&language=English"
)


#: Per-query attempt ceiling. A query that has failed three times with the
#: browser rebuilt in between will not succeed on the fourth; the run is better
#: off recording it FAILED and moving on, because a rerun retries it anyway.
MAX_QUERY_ATTEMPTS = 3

#: Consecutive network failures that stop the run. A dropped connection breaks
#: every query equally, so continuing means burning 265 timeouts to learn once
#: that the network is down -- which is precisely what happened: 0 of 265
#: searches completed and the log filled with ERR_INTERNET_DISCONNECTED. The
#: checkpoint survives, so recovery is rerunning the same command.
NETWORK_FAILURE_CIRCUIT_BREAKER = 8

#: Seconds between attempts, doubled per attempt, with jitter added.
BACKOFF_BASE = 4


class AcquisitionInterrupted(RuntimeError):
    """The circuit breaker tripped. Progress is on disk; rerun to resume."""


def _is_fatal_driver_error(exc):
    """Whether the WebDriver session itself is gone, rather than one page.

    This distinction decides whether to retry the query or rebuild the browser
    first, and getting it wrong is what wasted the previous run: the driver was
    created once, so a network drop mid-run left every later query talking to a
    dead chromedriver and timing out against it.
    """
    text = f"{type(exc).__name__}: {exc}".lower()
    return any(marker in text for marker in (
        "invalid session id", "session deleted", "no such session",
        "chrome not reachable", "disconnected", "connection refused",
        "connection aborted", "connection reset", "read timed out",
        "max retries exceeded", "target crashed", "browser has closed",
        "webdriverexception",
    ))


def _is_network_error(reason):
    """Whether the failure was the network rather than the page or the site.

    Driver-creation failures count. webdriver_manager resolves
    googlechromelabs.github.io to check for a newer chromedriver, so a DNS
    outage surfaces as a name-resolution error before any page is requested --
    and it will break every remaining query exactly as a dropped connection
    would, which is what the breaker is for.
    """
    text = str(reason).lower()
    return any(marker in text for marker in (
        "err_internet_disconnected", "err_name_not_resolved",
        "err_connection", "err_network", "err_proxy",
        "err_address_unreachable", "temporary failure in name resolution",
        "getaddrinfo failed", "failed to resolve", "nameresolutionerror",
        "max retries exceeded", "connectionerror",
    ))


def scrape_coursera_for_phrases(phrases, checkpoint=None, on_progress=None,
                                on_courses=None,
                                max_attempts=MAX_QUERY_ATTEMPTS):
    """Search Coursera once per phrase, surviving a browser or network failure.

    ``phrases`` is an iterable of ``(skill_name, search_phrase)`` -- the
    canonical skill that motivated the search, and the words actually typed.
    The two differ whenever an abbreviation searches badly ("RCA" finds
    chemistry, "Root Cause Analysis" finds the courses), so they are carried
    separately rather than conflated.

    ``checkpoint`` records which queries have already succeeded. It is runtime
    state and never catalogue data: it says what this machine has fetched, not
    what the catalogue holds.

    ``on_courses`` receives each query's courses as they are found, so a run
    that dies has already persisted its work. Without it a checkpoint could
    mark a query SUCCESS whose courses were then lost with the process, and the
    rerun would skip it.

    Returns catalogue dicts keyed by canonical URL. Raises
    AcquisitionInterrupted when the circuit breaker trips.
    """
    plan = list(phrases)
    by_url = {}
    driver = None
    consecutive_network_failures = 0

    try:
        for index, (skill_name, phrase) in enumerate(plan, start=1):
            if checkpoint is not None and checkpoint.is_done(phrase):
                if on_progress:
                    on_progress(index, len(plan), skill_name, phrase,
                                "skipped", 0, len(by_url))
                continue

            found, failure = 0, None
            for attempt in range(1, max_attempts + 1):
                try:
                    if driver is None:
                        # Inside the guarded region, not before it. Building a
                        # browser is itself a network operation -- webdriver
                        # manager fetches chromedriver metadata -- and the
                        # first resilient run died here, outside the try, on a
                        # DNS failure for googlechromelabs.github.io without
                        # reaching a single search.
                        logger.info("Coursera: starting a browser session")
                        driver = create_driver()
                        safe_load_page(driver, "https://www.coursera.org/",
                                       retries=2)
                        random_delay(3, 6)

                    found, failure = _run_one_search(driver, phrase, by_url)
                except Exception as exc:      # noqa: BLE001 -- classified below
                    failure = f"{type(exc).__name__}: {exc}"
                    if driver is None or _is_fatal_driver_error(exc):
                        # Rebuild rather than retry into a dead session. A
                        # driver that never started counts as fatal too.
                        quit_driver(driver)
                        driver = None

                if failure is None:
                    break

                if _is_network_error(failure):
                    consecutive_network_failures += 1
                    if (consecutive_network_failures
                            >= NETWORK_FAILURE_CIRCUIT_BREAKER):
                        if checkpoint is not None:
                            checkpoint.record(phrase, checkpoint.FAILED,
                                              attempt, failure)
                        raise AcquisitionInterrupted(
                            f"{consecutive_network_failures} consecutive "
                            f"network failures; stopped with progress saved. "
                            f"Rerun the same command to resume.")
                else:
                    consecutive_network_failures = 0

                if attempt < max_attempts:
                    # Exponential with jitter: a site that is rate-limiting
                    # wants a longer gap, and identical gaps look automated.
                    time.sleep(BACKOFF_BASE * (2 ** (attempt - 1))
                               + random.uniform(0, 3))

            if failure is None:
                consecutive_network_failures = 0
                # Persist before marking done, so SUCCESS never describes work
                # that was lost with the process.
                if on_courses:
                    on_courses([row for row in by_url.values()
                                if phrase in row["discovered_via"]])
                if checkpoint is not None:
                    checkpoint.record(phrase, checkpoint.SUCCESS, attempt, "")
            elif checkpoint is not None:
                checkpoint.record(phrase, checkpoint.FAILED, max_attempts,
                                  failure)

            if on_progress:
                on_progress(index, len(plan), skill_name, phrase,
                            "ok" if failure is None else "failed",
                            found, len(by_url))
            random_delay(8, 12)

    finally:
        quit_driver(driver)

    logger.info("Coursera: %d distinct courses from %d queries.",
                len(by_url), len(plan))
    return list(by_url.values())


def _run_one_search(driver, phrase, by_url):
    """One query. Returns ``(new_course_count, failure_reason_or_None)``."""
    url = COURSERA_SKILL_SEARCH_URL.format(query=quote_plus(phrase))
    page_source = safe_load_page(driver, url, retries=1)
    if not page_source:
        return 0, "page did not load"
    if is_blocked(page_source, driver.title or ""):
        return 0, "bot-detection page"

    try:
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((
                By.CSS_SELECTOR,
                'a[href*="/learn/"], a[href*="/specializations/"], '
                'a[href*="/professional-certificates/"]',
            ))
        )
    except Exception:
        # No results is a legitimate answer for a narrow skill, not a failure
        # to retry: retrying would spend three requests confirming an empty
        # result set.
        logger.info("Coursera: no courses for %r", phrase)
        return 0, None

    random_delay(2, 4)
    return _parse_coursera_cards(driver.page_source, phrase, by_url), None


def canonical_course_url(href):
    """One stable identity per Coursera course.

    The same course arrives under several URLs -- with tracking parameters,
    with or without a trailing slash, occasionally with a fragment -- and each
    variant would otherwise become its own catalogue row and its own set of
    skill mappings. Identity is the path: /learn/<slug>,
    /specializations/<slug>, /professional-certificates/<slug>.
    """
    url = href if href.startswith("http") else f"https://www.coursera.org{href}"
    url = url.split("?")[0].split("#")[0].rstrip("/")
    return url


def _parse_coursera_cards(page_source, via, by_url):
    """Merge one result page into ``by_url``. Returns how many were new.

    ``via`` is the search phrase that produced this page, recorded on each
    course as retrieval provenance. A course surfaced by two searches is one
    row carrying both phrases, never two rows.
    """
    soup = BeautifulSoup(page_source, "html.parser")
    for element in soup.find_all(["nav", "header", "footer"]):
        element.decompose()

    new_count = 0
    for link in soup.find_all("a", href=True):
        href = link["href"]
        if "/learn/" in href:
            resource_type = "Course"
        elif "/specializations/" in href:
            resource_type = "Specialization"
        elif "/professional-certificates/" in href:
            resource_type = "Professional Certificate"
        else:
            continue

        heading = link.find(["h2", "h3", "h4", "h5", "h6"])
        title = (heading.get_text(strip=True) if heading
                 else link.get_text(separator=" ", strip=True))
        if not title or len(title) < 5:
            continue
        title = title[:255]

        url = canonical_course_url(href)

        existing = by_url.get(url)
        if existing:
            if via not in existing["discovered_via"]:
                existing["discovered_via"].append(via)
            continue

        # The card's whole text, not just the title. "Google Data Analytics"
        # names no skill in its title but its card lists SQL, R and Tableau,
        # and that line is the only evidence the listing page carries.
        card = link.find_parent(["li", "article"]) or link
        by_url[url] = {
            "url":            url,
            "title":          title,
            "platform":       "Coursera",
            "type":           resource_type,
            "categories":     [],
            "discovered_via": [via],
            "card_text":      card.get_text(separator=" ", strip=True)[:2000],
        }
        new_count += 1

    return new_count


# ============================================================
# Main entry point
# ============================================================

PLATFORM_SCRAPERS = {
    "freecodecamp": scrape_freecodecamp,
    "microsoft":    scrape_microsoft_learn,
    "cisco":        scrape_cisco_netacad,
    "codecademy":   scrape_codecademy,
    "coursera":     scrape_coursera,
}

# Maps scraper key → the platform string stored in LearningResource.platform
PLATFORM_DISPLAY_NAMES = {
    "freecodecamp": "freeCodeCamp",
    "microsoft":    "Microsoft Learn",
    "cisco":        "Cisco NetAcad",
    "codecademy":   "Codecademy",
    "coursera":     "Coursera",
}


def scrape_learning_resources(skill_names, platforms=None):
    """
    Scrape learning resources for the given skill names across all platforms.

    Returns:
        {
            "resources":       [list of resource dicts],
            "status":          "SUCCESS" | "PARTIAL" | "FAILED",
            "platform_counts": {"freecodecamp": N, ...},
            "errors":          [list of platform keys that failed],
        }
    """
    if not skill_names:
        return {"resources": [], "status": "FAILED",
                "platform_counts": {}, "errors": ["No skills provided"]}

    active_platforms = platforms or list(PLATFORM_SCRAPERS.keys())
    all_resources    = []
    platform_counts  = {}
    errors           = []

    for platform_key in active_platforms:
        scraper_fn = PLATFORM_SCRAPERS.get(platform_key)
        if not scraper_fn:
            logger.warning("Unknown platform key: %s", platform_key)
            continue

        try:
            logger.info("Scraping platform: %s", platform_key)
            results = scraper_fn(skill_names)
            platform_counts[platform_key] = len(results)
            all_resources.extend(results)
        except Exception as exc:
            logger.error("Platform %s crashed: %s", platform_key, exc)
            platform_counts[platform_key] = 0
            errors.append(platform_key)

    total = len(all_resources)
    if total == 0 and errors:
        status = "FAILED"
    elif errors:
        status = "PARTIAL"
    else:
        status = "SUCCESS"

    logger.info(
        "Resource scrape complete. Status=%s  Total=%d  Errors=%s",
        status, total, errors,
    )

    return {
        "resources":       all_resources,
        "status":          status,
        "platform_counts": platform_counts,
        "errors":          errors,
    }
