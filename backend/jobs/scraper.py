import logging
import random
import re
import time
from datetime import datetime, timedelta
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

logger = logging.getLogger(__name__)

# ============================================================
# Settings
# ============================================================

SOURCE_PORTAL = "JobStreet"
BASE_URL = "https://my.jobstreet.com"

JOBSTREET_ICT_URL = (
    "https://my.jobstreet.com/jobs-in-information-communication-technology/in-malaysia"
)

MAX_PAGES = 1
MAX_JOBS_PER_PAGE = 10

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

BOT_INDICATORS = ["access denied", "blocked", "captcha", "cloudflare", "just a moment"]


# ============================================================
# Helper functions
# ============================================================

def clean_text(value):
    if not value:
        return ""
    return " ".join(value.split())


def random_delay(min_seconds=2, max_seconds=5):
    time.sleep(random.uniform(min_seconds, max_seconds))


def build_page_url(base_url, page):
    """Append or replace the ?page= query parameter on the ICT category URL."""
    parsed = urlparse(base_url)
    params = parse_qs(parsed.query)
    params["page"] = [str(page)]
    new_query = urlencode(params, doseq=True)
    return urlunparse((
        parsed.scheme, parsed.netloc, parsed.path,
        parsed.params, new_query, parsed.fragment,
    ))


def parse_salary(salary_text):
    if not salary_text:
        return None, None
    numbers = re.findall(r"\d[\d,]*", salary_text)
    if not numbers:
        return None, None
    salary_numbers = [int(n.replace(",", "")) for n in numbers]
    if len(salary_numbers) == 1:
        return salary_numbers[0], None
    return min(salary_numbers), max(salary_numbers)


def parse_posted_date(posted_text):
    if not posted_text:
        return None
    posted_text = posted_text.lower().strip()
    if any(w in posted_text for w in ["minute", "minutes", "hour", "hours", "minit", "jam"]):
        return datetime.today().date()
    if any(w in posted_text for w in ["day", "days", "hari"]):
        match = re.search(r"(\d+)", posted_text)
        if match:
            days_ago = 31 if "+" in posted_text else int(match.group(1))
            return (datetime.today() - timedelta(days=days_ago)).date()
    return None


def is_blocked(page_source, page_title=""):
    combined = (page_source[:5000] + page_title).lower()
    return any(indicator in combined for indicator in BOT_INDICATORS)


# ============================================================
# Selenium setup — anti-detection flags
# ============================================================

def create_driver():
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

    # Hide navigator.webdriver from JavaScript detection
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    })

    driver.implicitly_wait(10)
    return driver


# ============================================================
# Page loading
# ============================================================

def safe_get_page(driver, url, retries=3, delay=5):
    for attempt in range(1, retries + 1):
        try:
            driver.get(url)
            random_delay(3, 6)

            # Gradual 3-step scroll — looks human
            for i in range(1, 4):
                driver.execute_script(
                    f"window.scrollTo(0, document.body.scrollHeight * {i / 3});"
                )
                random_delay(0.5, 1.5)

            page_source = driver.page_source

            if is_blocked(page_source, driver.title):
                logger.warning("Bot detection on attempt %d for %s", attempt, url)
                time.sleep(delay * attempt)
                continue

            return page_source

        except Exception as error:
            logger.warning("Attempt %d/%d failed for %s: %s", attempt, retries, url, error)
            if attempt < retries:
                time.sleep(delay)

    logger.error("All %d attempts failed for %s", retries, url)
    return ""


# ============================================================
# Search page extraction
# ============================================================

def extract_job_cards(search_page_html):
    soup = BeautifulSoup(search_page_html, "html.parser")
    job_cards = soup.find_all("article", {"data-automation": "normalJob"})

    jobs = []
    for card in job_cards:
        title_tag = card.find("a", {"data-automation": "jobTitle"})
        if not title_tag:
            continue

        job_title = clean_text(title_tag.get_text())
        href = title_tag.get("href", "")
        if not job_title or not href:
            continue

        job_url = href if href.startswith("http") else f"{BASE_URL}{href}"

        posted_tag = card.find("span", {"data-automation": "jobListingDate"})
        posted_text = clean_text(posted_tag.get_text()) if posted_tag else ""

        jobs.append({
            "job_title": job_title,
            "source_url": job_url,
            "posted_date": parse_posted_date(posted_text),
            "source_portal": SOURCE_PORTAL,
        })

    # Deduplicate by URL
    seen = {}
    for job in jobs:
        seen[job["source_url"]] = job
    return list(seen.values())


# ============================================================
# Detail page extraction
# ============================================================

def extract_job_detail(driver, job, retries=2):
    """
    Returns (job_data_dict, is_blocked).
    Returns (None, True) if blocked, (None, False) if failed for other reasons.
    """
    for attempt in range(1, retries + 1):
        try:
            driver.get(job["source_url"])
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, 'h1[data-automation="job-detail-title"]')
                )
            )
            random_delay(2, 3)

            if is_blocked(driver.page_source, driver.title):
                logger.warning("Blocked on detail page attempt %d: %s", attempt, job["source_url"])
                if attempt < retries:
                    random_delay(8, 12)
                    continue
                return None, True

            soup = BeautifulSoup(driver.page_source, "html.parser")

            def get_text(selector):
                tag = soup.select_one(selector)
                return clean_text(tag.get_text()) if tag else ""

            title       = get_text('h1[data-automation="job-detail-title"]') or job["job_title"]
            company     = get_text('span[data-automation="advertiser-name"]')
            location    = get_text('span[data-automation="job-detail-location"]')
            salary_text = get_text('span[data-automation="job-detail-salary"]')
            job_type    = get_text('span[data-automation="job-detail-work-type"]')

            desc_tag    = soup.select_one('div[data-automation="jobAdDetails"]')
            description = clean_text(desc_tag.get_text(separator=" ")) if desc_tag else ""

            salary_min, salary_max = parse_salary(salary_text)

            return {
                "job_title":    title,
                "company_name": company,
                "location":     location,
                "salary_text":  salary_text,
                "salary_min":   salary_min,
                "salary_max":   salary_max,
                "description":  description,
                "job_type":     job_type,
                "posted_date":  job.get("posted_date"),
                "source_portal": SOURCE_PORTAL,
                "source_url":   job["source_url"],
            }, False

        except Exception as error:
            logger.warning(
                "Detail page attempt %d failed for %s: %s",
                attempt, job.get("source_url"), error,
            )
            if attempt < retries:
                random_delay(3, 6)

    return None, False


# ============================================================
# Main scraper — called by management command
# ============================================================

def scrape_jobs(source_url=None, max_pages=MAX_PAGES, max_jobs_per_page=MAX_JOBS_PER_PAGE):
    """
    Scrape the JobStreet Malaysia ICT category.

    Args:
        source_url:        Category URL to scrape (defaults to JOBSTREET_ICT_URL).
        max_pages:         Number of listing pages to crawl.
        max_jobs_per_page: Max job detail pages to fetch per listing page.

    Returns:
        {
            "jobs":             [list of job dicts],
            "status":           "SUCCESS" | "BLOCKED" | "PARTIAL" | "FAILED",
            "blocked_count":    int,
            "pages_attempted":  int,
            "source_url":       str,
        }
    """
    if source_url is None:
        source_url = JOBSTREET_ICT_URL

    driver = create_driver()
    scraped_jobs = []
    blocked_count = 0
    pages_attempted = 0

    try:
        for page in range(1, max_pages + 1):
            pages_attempted += 1
            url = build_page_url(source_url, page)
            logger.info("Scraping page %d: %s", page, url)

            search_html = safe_get_page(driver, url)

            if not search_html:
                logger.warning("No HTML returned for page %d — likely blocked.", page)
                blocked_count += 1
                break

            if is_blocked(search_html, driver.title):
                logger.warning("Search page %d blocked.", page)
                blocked_count += 1
                break

            job_cards = extract_job_cards(search_html)

            if not job_cards:
                logger.info("No job cards on page %d. Stopping.", page)
                break

            job_cards = job_cards[:max_jobs_per_page]
            logger.info("Page %d: %d job cards found.", page, len(job_cards))

            for job in job_cards:
                try:
                    detailed_job, was_blocked = extract_job_detail(driver, job)

                    if was_blocked:
                        blocked_count += 1
                        logger.warning("Blocked scraping detail: %s", job["source_url"])
                        continue

                    if detailed_job:
                        scraped_jobs.append(detailed_job)
                        logger.info(
                            "  Scraped: %s @ %s",
                            detailed_job["job_title"],
                            detailed_job.get("company_name", "Unknown"),
                        )

                except Exception as error:
                    logger.error("Unexpected error on job detail: %s", error)

            random_delay(2, 4)

    finally:
        driver.quit()

    # Final deduplication by source URL
    seen = {}
    for job in scraped_jobs:
        seen[job["source_url"]] = job
    final_jobs = list(seen.values())

    if blocked_count > 0 and len(final_jobs) == 0:
        status = "BLOCKED"
    elif blocked_count > 0 and len(final_jobs) > 0:
        status = "PARTIAL"
    elif len(final_jobs) == 0:
        status = "FAILED"
    else:
        status = "SUCCESS"

    logger.info(
        "Scrape complete. Status=%s  Jobs=%d  Blocked=%d",
        status, len(final_jobs), blocked_count,
    )

    return {
        "jobs":            final_jobs,
        "status":          status,
        "blocked_count":   blocked_count,
        "pages_attempted": pages_attempted,
        "source_url":      source_url,
    }
