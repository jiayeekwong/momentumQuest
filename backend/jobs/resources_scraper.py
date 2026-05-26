import logging
import time

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


# ============================================================
# Selenium driver (shared with scraper.py pattern)
# ============================================================

def create_driver():
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument(f"--user-agent={USER_AGENT}")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    })
    driver.implicitly_wait(10)
    return driver


# ============================================================
# freeCodeCamp — live curriculum page scrape
# ============================================================

FCC_LEARN_URL = "https://www.freecodecamp.org/learn"


def scrape_freecodecamp(skill_names):
    """
    Scrape freeCodeCamp's /learn page for available certifications.
    Matches cert titles against skill_names — no hardcoding.
    Students are redirected to the cert URL when they select it.
    Returns list of resource dicts.
    """
    results = []

    try:
        resp = requests.get(FCC_LEARN_URL, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        seen_urls = set()

        # Each certification block is an <a> linking into /learn/...
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

            title_lower = title.lower()
            for skill_name in skill_names:
                if skill_name.lower() in title_lower:
                    results.append({
                        "skill_name": skill_name,
                        "title":    title,
                        "platform": "freeCodeCamp",
                        "url":      url,
                        "type":     "Certification",
                    })
                    seen_urls.add(url)
                    break

        logger.info("freeCodeCamp: %d resources matched.", len(results))

    except Exception as exc:
        logger.error("freeCodeCamp scrape failed: %s", exc)

    return results


# ============================================================
# Microsoft Learn — public JSON catalog API
# ============================================================

MS_CATALOG_API = "https://learn.microsoft.com/api/catalog/?type=certifications&locale=en-us"


def scrape_microsoft_learn(skill_names):
    """
    Fetch Microsoft certifications via the public catalog API.
    Matches titles/subjects against skill_names.
    Returns list of resource dicts.
    """
    results = []
    skill_names_lower = {s.lower() for s in skill_names}

    try:
        resp = requests.get(MS_CATALOG_API, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        certifications = data.get("certifications", [])

        for cert in certifications:
            title   = cert.get("title", "")
            url     = cert.get("url", "")
            if not title or not url:
                continue

            # Ensure URL is absolute
            if not url.startswith("http"):
                url = f"https://learn.microsoft.com{url}"

            # Match against skill names in the cert title
            title_lower = title.lower()
            for skill_name in skill_names:
                if skill_name.lower() in title_lower:
                    results.append({
                        "skill_name": skill_name,
                        "title":    title,
                        "platform": "Microsoft Learn",
                        "url":      url,
                        "type":     "Certification",
                    })
                    break  # one skill per resource record

        logger.info("Microsoft Learn: %d resources matched.", len(results))

    except Exception as exc:
        logger.error("Microsoft Learn scrape failed: %s", exc)

    return results


# ============================================================
# Cisco NetAcad — public course catalog
# ============================================================

CISCO_CATALOG_URL = "https://www.netacad.com/courses/all-courses"

CISCO_CERT_KEYWORDS = ["ccna", "ccnp", "cyberops", "cybersecurity", "networking",
                        "python", "iot", "linux", "ethical hacking", "network security"]


def scrape_cisco_netacad(skill_names):
    """
    Scrape Cisco NetAcad public course catalog.
    Filters to courses that lead to badges/credentials.
    Returns list of resource dicts.
    """
    results = []
    skill_names_lower = {s.lower() for s in skill_names}

    try:
        resp = requests.get(CISCO_CATALOG_URL, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        course_cards = soup.find_all(
            lambda tag: tag.name in ["article", "div", "li"]
            and tag.find("a", href=True)
            and tag.get_text(strip=True)
        )

        seen_urls = set()
        for card in course_cards:
            link = card.find("a", href=True)
            if not link:
                continue

            title = link.get_text(strip=True)
            href  = link["href"]
            if not title or len(title) < 5:
                continue

            url = href if href.startswith("http") else f"https://www.netacad.com{href}"
            if url in seen_urls:
                continue

            title_lower = title.lower()
            for skill_name in skill_names:
                if skill_name.lower() in title_lower:
                    results.append({
                        "skill_name": skill_name,
                        "title":    title,
                        "platform": "Cisco NetAcad",
                        "url":      url,
                        "type":     "Badge",
                    })
                    seen_urls.add(url)
                    break

        logger.info("Cisco NetAcad: %d resources matched.", len(results))

    except Exception as exc:
        logger.error("Cisco NetAcad scrape failed: %s", exc)

    return results


# ============================================================
# IBM SkillsBuild — public course catalog
# ============================================================

IBM_CATALOG_URL = "https://skillsbuild.org/learn"


def scrape_ibm_skillsbuild(skill_names):
    """
    Scrape IBM SkillsBuild public catalog for digital credential courses.
    Returns list of resource dicts.
    """
    results = []
    skill_names_lower = {s.lower() for s in skill_names}

    try:
        resp = requests.get(IBM_CATALOG_URL, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        links = soup.find_all("a", href=True)
        seen_urls = set()

        for link in links:
            title = link.get_text(strip=True)
            href  = link["href"]
            if not title or len(title) < 5:
                continue

            url = href if href.startswith("http") else f"https://skillsbuild.org{href}"
            if url in seen_urls:
                continue

            title_lower = title.lower()
            for skill_name in skill_names:
                if skill_name.lower() in title_lower:
                    results.append({
                        "skill_name": skill_name,
                        "title":    title,
                        "platform": "IBM SkillsBuild",
                        "url":      url,
                        "type":     "Digital Credential",
                    })
                    seen_urls.add(url)
                    break

        logger.info("IBM SkillsBuild: %d resources matched.", len(results))

    except Exception as exc:
        logger.error("IBM SkillsBuild scrape failed: %s", exc)

    return results


# ============================================================
# Coursera — Selenium (JS-rendered search)
# ============================================================

def _scrape_coursera_for_skill(driver, skill_name):
    """Fetch Professional Certificate results for one skill from Coursera."""
    results = []
    search_url = (
        f"https://www.coursera.org/search?query={requests.utils.quote(skill_name)}"
        "&productDifficultyLevel=BEGINNER"
        "&productDifficultyLevel=INTERMEDIATE"
        "&productTypeDescription=Professional+Certificates"
    )

    try:
        driver.get(search_url)
        WebDriverWait(driver, 12).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "li.ais-InfiniteHits-item"))
        )
        time.sleep(2)

        soup = BeautifulSoup(driver.page_source, "html.parser")
        cards = soup.select("li.ais-InfiniteHits-item")

        for card in cards[:5]:  # top 5 per skill
            title_tag = card.select_one("h3, h2, [data-testid='product-card-title']")
            link_tag  = card.select_one("a[href]")
            if not title_tag or not link_tag:
                continue

            title = title_tag.get_text(strip=True)
            href  = link_tag["href"]
            url   = href if href.startswith("http") else f"https://www.coursera.org{href}"

            results.append({
                "skill_name": skill_name,
                "title":    title,
                "platform": "Coursera",
                "url":      url,
                "type":     "Professional Certificate",
            })

    except Exception as exc:
        logger.warning("Coursera scrape failed for skill '%s': %s", skill_name, exc)

    return results


def scrape_coursera(skill_names):
    """
    Scrape Coursera Professional Certificates for all given skill names.
    Uses one Selenium driver instance shared across all skill queries.
    Returns list of resource dicts.
    """
    results = []
    driver = create_driver()

    try:
        for skill_name in skill_names:
            skill_results = _scrape_coursera_for_skill(driver, skill_name)
            results.extend(skill_results)
            time.sleep(2)
    finally:
        driver.quit()

    logger.info("Coursera: %d resources found.", len(results))
    return results


# ============================================================
# Main entry point
# ============================================================

PLATFORM_SCRAPERS = {
    "freecodecamp": scrape_freecodecamp,
    "microsoft":    scrape_microsoft_learn,
    "cisco":        scrape_cisco_netacad,
    "ibm":          scrape_ibm_skillsbuild,
    "coursera":     scrape_coursera,
}

# Maps scraper key → the platform string stored in LearningResource.platform
PLATFORM_DISPLAY_NAMES = {
    "freecodecamp": "freeCodeCamp",
    "microsoft":    "Microsoft Learn",
    "cisco":        "Cisco NetAcad",
    "ibm":          "IBM SkillsBuild",
    "coursera":     "Coursera",
}


def scrape_learning_resources(skill_names, platforms=None):
    """
    Scrape learning resources for the given skill names across all platforms.

    Args:
        skill_names: list of skill name strings from the Skill table.
        platforms:   optional list of platform keys to limit scraping.
                     Defaults to all platforms.

    Returns:
        {
            "resources":       [list of resource dicts],
            "status":          "SUCCESS" | "PARTIAL" | "FAILED",
            "platform_counts": {"freecodecamp": N, ...},
            "errors":          [list of platform names that failed],
        }
    """
    if not skill_names:
        return {"resources": [], "status": "FAILED",
                "platform_counts": {}, "errors": ["No skills provided"]}

    active_platforms = platforms or list(PLATFORM_SCRAPERS.keys())
    all_resources = []
    platform_counts = {}
    errors = []

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
