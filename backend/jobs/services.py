from decimal import Decimal, InvalidOperation

from .models import JobCategory, ScrapedJob, ScrapedJobSkill
from .skill_extractor import extract_skills_from_text


def classify_job_category(job_title):
    """
    Classify raw job title into a clean JobCategory.
    """
    title = job_title.lower()

    if any(keyword in title for keyword in ["frontend", "react", "web developer", "full stack"]):
        return "Web Developer"

    if any(keyword in title for keyword in ["mobile", "android", "ios", "flutter"]):
        return "Mobile App Developer"

    if any(keyword in title for keyword in ["data analyst", "business analyst"]):
        return "Data Analyst"

    if any(keyword in title for keyword in ["data scientist", "machine learning", "ai engineer", "artificial intelligence"]):
        return "AI/ML Engineer"

    if any(keyword in title for keyword in ["cybersecurity", "security analyst", "soc analyst"]):
        return "Cybersecurity"

    if any(keyword in title for keyword in ["network", "network engineer"]):
        return "Network Engineer"

    if any(keyword in title for keyword in ["database", "dba"]):
        return "Database Administrator"

    if any(keyword in title for keyword in ["devops", "cloud engineer", "site reliability"]):
        return "DevOps Engineer"

    if any(keyword in title for keyword in ["qa", "quality assurance", "tester", "test engineer"]):
        return "QA Tester"

    if any(keyword in title for keyword in ["ui", "ux", "designer"]):
        return "UI/UX Designer"

    return "Software Engineer"


def get_or_create_job_category(category_name):
    job_category, _ = JobCategory.objects.get_or_create(
        category_name=category_name
    )

    return job_category


def clean_decimal(value):
    """
    Convert salary value to Decimal.
    Return None if salary is missing or invalid.
    """
    if value in [None, ""]:
        return None

    try:
        return Decimal(str(value))

    except (InvalidOperation, ValueError):
        return None


def save_scraped_job(job_data):
    """
    Save one scraped job into database.
    Also extract skills and save them into ScrapedJobSkill.
    """
    job_title = job_data.get("job_title", "").strip()
    description = job_data.get("description", "").strip()
    source_url = job_data.get("source_url", "").strip()

    if not job_title or not source_url:
        return None, False

    category_name = classify_job_category(job_title)
    job_category = get_or_create_job_category(category_name)

    scraped_job, created = ScrapedJob.objects.update_or_create(
        source_url=source_url,
        defaults={
            "job_category": job_category,
            "job_title": job_title,
            "description": description,
            "salary_min": clean_decimal(job_data.get("salary_min")),
            "salary_max": clean_decimal(job_data.get("salary_max")),
            "source_portal": job_data.get("source_portal", "JobStreet"),
        },
    )

    matched_skills = extract_skills_from_text(
        f"{job_title} {description}"
    )

    for skill in matched_skills:
        ScrapedJobSkill.objects.get_or_create(
            scraped_job=scraped_job,
            skill=skill,
            defaults={
                "extraction_method": "keyword",
            },
        )

    return scraped_job, created


def save_scraped_jobs(jobs):
    """
    Save many scraped jobs.
    """
    created_count = 0
    updated_count = 0

    for job_data in jobs:
        scraped_job, created = save_scraped_job(job_data)

        if not scraped_job:
            continue

        if created:
            created_count += 1
        else:
            updated_count += 1

    return created_count, updated_count