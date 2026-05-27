import logging
from decimal import Decimal, InvalidOperation

from django.utils import timezone

logger = logging.getLogger(__name__)

from .models import JobCategory, ScrapedJob, ScrapedJobSkill, Skill, ScrapeLog
from .skill_extractor import extract_skills_from_text


def classify_job_category(job_title):
    title = job_title.lower()

    if any(k in title for k in ["frontend", "react", "web developer", "full stack"]):
        return "Web Developer"
    if any(k in title for k in ["mobile", "android", "ios", "flutter"]):
        return "Mobile App Developer"
    if any(k in title for k in ["data analyst", "business analyst"]):
        return "Data Analyst"
    if any(k in title for k in ["data scientist", "machine learning", "ai engineer", "artificial intelligence"]):
        return "AI/ML Engineer"
    if any(k in title for k in ["cybersecurity", "security analyst", "soc analyst"]):
        return "Cybersecurity"
    if any(k in title for k in ["network", "network engineer"]):
        return "Network Engineer"
    if any(k in title for k in ["database", "dba"]):
        return "Database Administrator"
    if any(k in title for k in ["devops", "cloud engineer", "site reliability"]):
        return "DevOps Engineer"
    if any(k in title for k in ["qa", "quality assurance", "tester", "test engineer"]):
        return "QA Tester"
    if any(k in title for k in ["ui", "ux", "designer"]):
        return "UI/UX Designer"
    return "Software Engineer"


def get_or_create_job_category(category_name):
    job_category, _ = JobCategory.objects.get_or_create(category_name=category_name)
    return job_category


def clean_decimal(value):
    if value in [None, ""]:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def save_scraped_job(job_data):
    """Save one scraped job and its matched skills. Returns (instance, created)."""
    job_title = job_data.get("job_title", "").strip()
    source_url = job_data.get("source_url", "").strip()

    if not job_title or not source_url:
        return None, False

    category_name = classify_job_category(job_title)
    job_category = get_or_create_job_category(category_name)

    scraped_job, created = ScrapedJob.objects.update_or_create(
        source_url=source_url,
        defaults={
            "job_category":  job_category,
            "job_title":     job_title,
            "company_name":  job_data.get("company_name", ""),
            "location":      job_data.get("location", ""),
            "description":   job_data.get("description", ""),
            "salary_text":   job_data.get("salary_text", ""),
            "salary_min":    clean_decimal(job_data.get("salary_min")),
            "salary_max":    clean_decimal(job_data.get("salary_max")),
            "job_type":      job_data.get("job_type", ""),
            "posted_date":   job_data.get("posted_date"),
            "source_portal": job_data.get("source_portal", "JobStreet"),
        },
    )

    matched_skills = extract_skills_from_text(
        f"{job_title} {job_data.get('description', '')}"
    )
    for skill in matched_skills:
        ScrapedJobSkill.objects.get_or_create(
            scraped_job=scraped_job,
            skill=skill,
            defaults={"extraction_method": "keyword"},
        )

    return scraped_job, created


def save_scraped_jobs(jobs):
    """Bulk-save a list of scraped job dicts. Returns (created_count, updated_count)."""
    created_count = 0
    updated_count = 0

    for job_data in jobs:
        _, created = save_scraped_job(job_data)
        if created:
            created_count += 1
        else:
            updated_count += 1

    return created_count, updated_count


# ============================================================
# ScrapeLog helpers
# ============================================================

def create_scrape_log(roles_scraped, pages_attempted=0):
    return ScrapeLog.objects.create(
        roles_scraped=roles_scraped,
        pages_attempted=pages_attempted,
    )


def finish_scrape_log(log, status, jobs_scraped, jobs_created, jobs_updated, blocked_count, error_message=""):
    log.finished_at    = timezone.now()
    log.status         = status
    log.jobs_scraped   = jobs_scraped
    log.jobs_created   = jobs_created
    log.jobs_updated   = jobs_updated
    log.blocked_count  = blocked_count
    log.error_message  = error_message
    log.save()
