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
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from webdriver_manager.chrome import ChromeDriverManager


# ============================================================
# Scraper settings
# ============================================================

SOURCE_PORTAL = "JobStreet"
BASE_URL = "https://my.jobstreet.com"

MAX_PAGES = 1
MAX_JOBS_PER_PAGE = 10

# From Jobstreet - category: information-communication-technology
JOBSTREET_ICT_FILTER_URL = (
    "https://my.jobstreet.com/jobs-in-information-communication-technology/in-malaysia"
)


# ============================================================
# Basic helper functions
# ============================================================

def clean_text(value):
    if not value:
        return ""

    return " ".join(value.split())


def random_delay(min_seconds=2, max_seconds=5):
    time.sleep(random.uniform(min_seconds, max_seconds))


def normalize_job_url(href):
    if href.startswith("http"):
        return href

    return f"{BASE_URL}{href}"


def build_page_url(base_url, page):
    """
    Add or replace the page number in the copied JobStreet category URL.
    """
    parsed_url = urlparse(base_url)
    query_params = parse_qs(parsed_url.query)

    query_params["page"] = [str(page)]

    new_query = urlencode(query_params, doseq=True)

    return urlunparse((
        parsed_url.scheme,
        parsed_url.netloc,
        parsed_url.path,
        parsed_url.params,
        new_query,
        parsed_url.fragment,
    ))


def parse_salary(salary_text):
    if not salary_text:
        return None, None

    numbers = re.findall(r"\d[\d,]*", salary_text)

    if not numbers:
        return None, None

    salary_numbers = [
        int(number.replace(",", ""))
        for number in numbers
    ]

    if len(salary_numbers) == 1:
        return salary_numbers[0], None

    return min(salary_numbers), max(salary_numbers)


def parse_posted_date(posted_text):
    if not posted_text:
        return None

    posted_text = posted_text.lower().strip()

    if (
        "minute" in posted_text
        or "minutes" in posted_text
        or "hour" in posted_text
        or "hours" in posted_text
        or "minit" in posted_text
        or "jam" in posted_text
    ):
        return datetime.today().date()

    if "day" in posted_text or "days" in posted_text or "hari" in posted_text:
        match = re.search(r"(\d+)", posted_text)

        if match:
            days_ago = int(match.group(1))
            return (datetime.today() - timedelta(days=days_ago)).date()

    return None


# ============================================================
# Selenium setup
# ============================================================

def create_driver():
    chrome_options = Options()

    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")

    service = Service(ChromeDriverManager().install())

    driver = webdriver.Chrome(
        service=service,
        options=chrome_options,
    )

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

            driver.execute_script(
                "window.scrollTo(0, document.body.scrollHeight);"
            )

            random_delay(1, 2)

            page_source = driver.page_source

            if (
                "access denied" in page_source.lower()
                or "blocked" in page_source.lower()
            ):
                print(f"Blocked or denied on attempt {attempt}.")
                time.sleep(delay)
                continue

            return page_source

        except Exception as error:
            print(f"Attempt {attempt}/{retries} failed: {error}")

            if attempt < retries:
                time.sleep(delay)

    return ""


# ============================================================
# Search page extraction
# ============================================================

def extract_job_cards(search_page_html):
    soup = BeautifulSoup(search_page_html, "html.parser")

    job_cards = soup.find_all(
        "article",
        {"data-automation": "normalJob"},
    )

    jobs = []

    for card in job_cards:
        title_tag = card.find(
            "a",
            {"data-automation": "jobTitle"},
        )

        if not title_tag:
            continue

        job_title = clean_text(title_tag.get_text())
        href = title_tag.get("href", "")

        if not job_title or not href:
            continue

        job_url = normalize_job_url(href)

        posted_tag = card.find(
            "span",
            {"data-automation": "jobListingDate"},
        )

        posted_text = clean_text(posted_tag.get_text()) if posted_tag else ""

        jobs.append({
            "job_title": job_title,
            "source_url": job_url,
            "posted_date": parse_posted_date(posted_text),
            "source_portal": SOURCE_PORTAL,
        })

    return remove_duplicate_jobs(jobs)


def remove_duplicate_jobs(jobs):
    unique_jobs = {}

    for job in jobs:
        unique_jobs[job["source_url"]] = job

    return list(unique_jobs.values())


# ============================================================
# Detail page extraction
# ============================================================

def extract_job_detail(driver, job):
    driver.get(job["source_url"])

    WebDriverWait(driver, 10).until(
        EC.presence_of_element_located(
            (By.CSS_SELECTOR, 'h1[data-automation="job-detail-title"]')
        )
    )

    random_delay(2, 3)

    soup = BeautifulSoup(driver.page_source, "html.parser")

    title_tag = soup.select_one(
        'h1[data-automation="job-detail-title"]'
    )

    company_tag = soup.select_one(
        'span[data-automation="advertiser-name"]'
    )

    location_tag = soup.select_one(
        'span[data-automation="job-detail-location"]'
    )

    salary_tag = soup.select_one(
        'span[data-automation="job-detail-salary"]'
    )

    job_type_tag = soup.select_one(
        'span[data-automation="job-detail-work-type"]'
    )

    description_tag = soup.select_one(
        'div[data-automation="jobAdDetails"]'
    )

    job_title = (
        clean_text(title_tag.get_text())
        if title_tag
        else job["job_title"]
    )

    company_name = (
        clean_text(company_tag.get_text())
        if company_tag
        else ""
    )

    location = (
        clean_text(location_tag.get_text())
        if location_tag
        else ""
    )

    salary_text = (
        clean_text(salary_tag.get_text())
        if salary_tag
        else ""
    )

    job_type = (
        clean_text(job_type_tag.get_text())
        if job_type_tag
        else ""
    )

    description = (
        clean_text(description_tag.get_text(separator=" "))
        if description_tag
        else ""
    )

    salary_min, salary_max = parse_salary(salary_text)

    return {
        "job_title": job_title,
        "company_name": company_name,
        "location": location,
        "salary_text": salary_text,
        "salary_min": salary_min,
        "salary_max": salary_max,
        "description": description,
        "job_type": job_type,
        "posted_date": job.get("posted_date"),
        "source_portal": SOURCE_PORTAL,
        "source_url": job["source_url"],
    }


# ============================================================
# Main function used by Django command
# ============================================================

def scrape_jobs(
    max_pages=MAX_PAGES,
    max_jobs_per_page=MAX_JOBS_PER_PAGE,
):
    """
    Scrape JobStreet Malaysia ICT category without keyword.

    This function is called by:
    python manage.py scrape_jobs

    It returns a list of dictionaries.
    jobs/services.py saves the data into PostgreSQL.
    """
    if "PASTE_YOUR_JOBSTREET_ICT_FILTER_URL_HERE" in JOBSTREET_ICT_FILTER_URL:
        raise ValueError(
            "Please paste your JobStreet ICT filter URL into JOBSTREET_ICT_FILTER_URL."
        )

    driver = create_driver()
    scraped_jobs = []

    try:
        for page in range(1, max_pages + 1):
            page_url = build_page_url(
                JOBSTREET_ICT_FILTER_URL,
                page,
            )

            print(f"\nOpening ICT category page: {page_url}")

            search_page_html = safe_get_page(driver, page_url)

            if not search_page_html:
                print("No page HTML returned.")
                continue

            job_cards = extract_job_cards(search_page_html)

            if not job_cards:
                print("No job cards found.")
                continue

            job_cards = job_cards[:max_jobs_per_page]

            print(f"Found {len(job_cards)} jobs.")

            for job in job_cards:
                try:
                    detailed_job = extract_job_detail(driver, job)
                    scraped_jobs.append(detailed_job)

                    print(f"Scraped: {detailed_job['job_title']}")

                except Exception as error:
                    print(f"Failed to scrape job detail: {error}")

            random_delay(2, 4)

    finally:
        driver.quit()

    return remove_duplicate_jobs(scraped_jobs)