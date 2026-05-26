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

    service = Service(ChromeDriverManager().install())
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


def skill_matches_title(skill_name, title):
    """
    Word-boundary match so single-char skills like 'R' or 'C' don't match
    every word that contains those letters (e.g. 'React', 'Framework').
    """
    pattern = r'\b' + re.escape(skill_name) + r'\b'
    return bool(re.search(pattern, title, re.IGNORECASE))


# ============================================================
# freeCodeCamp — React SPA, Selenium required
# ============================================================

FCC_LEARN_URL = "https://www.freecodecamp.org/learn"


def scrape_freecodecamp(skill_names):
    results = []
    driver = create_driver()

    try:
        page_source = safe_load_page(driver, FCC_LEARN_URL)
        if not page_source:
            logger.error("freeCodeCamp: page failed to load after retries.")
            return results

        # React may still be hydrating — wait for certification links
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'a[href*="/learn/"]'))
        )
        random_delay(2, 4)

        soup      = BeautifulSoup(driver.page_source, "html.parser")
        seen_urls = set()

        for link in soup.find_all("a", href=True):
            href = link["href"]
            if "/learn/" not in href:
                continue

            title = link.get_text(strip=True)
            if not title or len(title) < 8:
                continue

            url = href if href.startswith("http") else f"https://www.freecodecamp.org{href}"
            if url in seen_urls:
                continue

            for skill_name in skill_names:
                if skill_matches_title(skill_name, title):
                    results.append({
                        "skill_name": skill_name,
                        "title":      title[:255],
                        "platform":   "freeCodeCamp",
                        "url":        url,
                        "type":       "Certification",
                    })
                    seen_urls.add(url)
                    break

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

CISCO_CATALOG_URL = "https://www.netacad.com/catalog"


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

            # Only include links that point to enrollable course pages.
            # Cisco NetAcad course URLs contain /courses/ or /course/.
            # This excludes news, blogs, career resources, and static pages.
            if not any(seg in href for seg in ["/courses/", "/course/"]):
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
        from jobs.models import JobCategory
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
