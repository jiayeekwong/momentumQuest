from urllib.parse import urlparse, urlunparse
import logging
import re
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

from .models import JobCategory, Skill
from .title_normalizer import (
    extract_career_level, normalize_title, strip_recruiter_noise,
)
from job_listings.models import ScrapeLog
from .skill_extractor import extract_skills_from_text


# Every title that matches no rule lands here rather than being folded into a
# real category. The previous version fell through to "Software Engineer",
# which silently absorbed IT Support, Project Manager, Scrum Master, ERP
# Consultant and every other unlisted role -- and those counts are read
# straight into the dashboard's top-categories chart, so the chart reported
# demand that did not exist. An explicit bucket keeps the uncovered share
# visible rather than inflating a real one.
UNCATEGORIZED_CATEGORY = "Other IT"

# Ordered: first match wins, most specific category first.
#
# Patterns are \b-anchored. The previous version tested bare substrings, so
# "ui" matched recr(ui)tment / b(ui)ld / g(ui)dewire / circ(ui)t / s(ui)te,
# "ios" matched k(ios)k / stud(ios) / B(IOS), and "react" matched (react)or --
# filing all of them as design, mobile or web roles.
CATEGORY_RULES = (
    # Leads because its vocabulary is distinctive and would otherwise be
    # swallowed by Network ("Network Security Engineer") or QA
    # ("Penetration Tester").
    ("Cybersecurity", (
        r"cyber\s*-?security", r"\bsecurity\b", r"\binfosec\b", r"\bsoc\b",
        r"penetration test", r"\bpentest", r"vulnerability", r"\bforensic",
        r"threat intel", r"incident response", r"\bgrc\b",
    )),
    ("AI/ML Engineer", (
        r"data scientist", r"data science", r"machine learning", r"\bml\s+engineer",
        r"\bai\b", r"artificial intelligence", r"deep learning", r"\bnlp\b",
        r"computer vision", r"\bllm\b", r"generative ai",
    )),
    ("Database Administrator", (
        r"\bdatabase\b", r"\bdba\b", r"\boracle\s+(?:dba|administrator)",
        r"\bsql\s+(?:dba|administrator)",
    )),
    ("Data Analyst", (
        r"\bdata\s+(?:analyst|analytics|engineer|architect|warehouse)",
        r"business analyst", r"business intelligence", r"\bbi\s+(?:developer|analyst)",
        r"\banalytics\b", r"\betl\b", r"reporting analyst",
    )),
    ("DevOps Engineer", (
        r"\bdevops\b", r"site reliability", r"\bsre\b", r"cloud engineer",
        r"cloud architect", r"cloud solution", r"platform engineer",
        r"\bci/?cd\b", r"kubernetes", r"\baws\b", r"\bazure\b",
    )),
    ("Network Engineer", (
        r"\bnetwork\b", r"\bnoc\b", r"\btelecom", r"\brouting\b",
        r"\bcisco\b", r"\bvoip\b",
    )),
    ("QA Tester", (
        r"\bqa\b", r"quality assurance", r"quality engineer", r"\btester\b",
        r"test engineer", r"test analyst", r"\bsdet\b", r"automation test",
        r"test automation",
    )),
    # Before Web: "React Native Mobile Developer" is a mobile role, and the
    # old ordering tested "react" first and filed it under Web.
    ("Mobile App Developer", (
        r"\bmobile\b", r"\bandroid\b", r"\bios\b", r"\bflutter\b",
        r"react native", r"\bswift\b", r"\bkotlin\b",
    )),
    # Before Web: a title carrying "designer", "UI" or "UX" is a design role
    # even when it also says web.
    ("UI/UX Designer", (
        r"\bui\b", r"\bux\b", r"\bui/ux\b", r"user interface", r"user experience",
        r"\bdesigner\b", r"\bfigma\b", r"product design",
    )),
    ("Web Developer", (
        r"\bfront\s*-?end\b", r"\breact\b", r"\bangular\b", r"\bvue\b",
        r"web developer", r"web application", r"full\s*-?stack", r"\bphp\b",
        r"\blaravel\b", r"\bwordpress\b", r"\bwebmaster\b",
    )),
    # Last real rule, and deliberately specific rather than a catch-all: a
    # title has to actually name software work to land here.
    ("Software Engineer", (
        r"software\s+(?:engineer|developer|architect|specialist)",
        r"\bprogrammer\b", r"\bback\s*-?end\b", r"application developer",
        r"\bdeveloper\b", r"\.net\b", r"\bjava\s+developer\b",
        r"\bpython\s+developer\b", r"\bc\+\+", r"\bgolang\b", r"\bembedded\b",
    )),
)

COMPILED_CATEGORY_RULES = tuple(
    (category_name, tuple(re.compile(pattern, re.IGNORECASE) for pattern in patterns))
    for category_name, patterns in CATEGORY_RULES
)

CATEGORY_NAMES = tuple(name for name, _ in CATEGORY_RULES) + (UNCATEGORIZED_CATEGORY,)


def classify_job_category(job_title):
    """Assign a raw employer title to one of the JobCategory names.

    The title is noise-stripped first, the same way the Market Role
    classifier treats it -- previously this was the only classifier reading
    the raw title, so recruiter marketing appended to a title could decide the
    category.
    """
    if not job_title:
        return UNCATEGORIZED_CATEGORY

    cleaned = strip_recruiter_noise(job_title) or job_title
    for category_name, patterns in COMPILED_CATEGORY_RULES:
        if any(pattern.search(cleaned) for pattern in patterns):
            return category_name
    return UNCATEGORIZED_CATEGORY


def get_or_create_job_category(category_name):
    job_category, _ = JobCategory.objects.get_or_create(category_name=category_name)
    return job_category


def get_or_create_job_title(title_name, job_category, market_role=None):
    """Preserve a market title and record the Market Role it names."""
    from .models import JobTitle

    job_title, created = JobTitle.objects.get_or_create(
        title_name=title_name,
        defaults={
            "category": job_category,
            "market_role": market_role,
            "career_level": extract_career_level(title_name),
        },
    )
    update_fields = []
    if not created and job_title.category_id is None and job_category is not None:
        job_title.category = job_category
        update_fields.append("category")
    # Filled only when missing, like category above: a Market Role corrected by
    # hand must not be undone by the next scrape. classify_market_roles
    # overwrites deliberately.
    if not created and job_title.market_role_id is None and market_role is not None:
        job_title.market_role = market_role
        update_fields.append("market_role")
    if not created and not job_title.career_level:
        job_title.career_level = extract_career_level(title_name)
        update_fields.append("career_level")
    if update_fields:
        job_title.save(update_fields=update_fields)
    return job_title



def clean_decimal(value):
    if value in [None, ""]:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def canonical_source_url(url):
    """Reduce a JobStreet advert URL to the part that identifies the posting.

    JobStreet appends per-session tracking to every link -- a "#sol=" hash and
    ?type/?ref/?origin parameters that change on each page load. Keying dedup
    on the raw URL therefore never matches, and the same advert is stored
    again on every scrape. Measured 2026-08-19, that had made 40% of the
    scraped table duplicates.

    "https://my.jobstreet.com/job/92352106?type=standard&ref=x#sol=abc"
    becomes "https://my.jobstreet.com/job/92352106", which is also a working
    link for the student's "View on JobStreet" button.
    """
    if not url:
        return ""
    parsed = urlparse(url.strip())
    if not parsed.scheme or not parsed.netloc:
        return url.strip()
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", "", ""))


@transaction.atomic
def classify_market_role(job_title, description, index=None):
    """Classify one advert, building the Market Role index if needed."""
    from .market_role_classifier import build_index, classify_listing

    return classify_listing(job_title, description, index or build_index())


def save_scraped_job(job_data, index=None):
    """Save one scraped job (into JobListing) and its matched skills.

    Scraped jobs are stored in JobListing with source_type='SCRAPED' and no
    company FK. Deduplicated on source_url. Returns (instance, created).

    ``index`` is the Market Role lookup, passed in by the bulk caller so a
    scrape of 300 adverts builds it once rather than 300 times.
    """
    # Imported here to avoid a circular import (job_listings imports scrape_jobs).
    from job_listings.models import JobListing, JobSkill

    job_title = job_data.get("job_title", "").strip()
    source_url = canonical_source_url(job_data.get("source_url", ""))

    if not job_title or not source_url:
        return None, False

    category_name = classify_job_category(job_title)
    job_category = get_or_create_job_category(category_name)

    # Classified on the way in, so a newly scraped advert is immediately
    # usable for skill demand instead of waiting for a separate pass.
    description = job_data.get("description", "")
    classification = classify_market_role(job_title, description, index=index)
    job_title_ref = get_or_create_job_title(job_title, job_category,
                                            classification.market_role)

    listing, created = JobListing.objects.update_or_create(
        source_url=source_url,
        defaults={
            "category":      job_category,
            "job_title":     job_title,
            "job_title_ref": job_title_ref,
            "normalized_job_title":    normalize_title(job_title),
            "market_role":             classification.market_role,
            "career_level":            extract_career_level(job_title),
            "classification_method":   classification.method,
            "matched_alias":           classification.matched_alias[:250],
            "classification_evidence": classification.evidence,
            "classified_time":         timezone.now(),
            "company_name":  job_data.get("company_name", ""),
            "location":      job_data.get("location", ""),
            "description":   description,
            "salary_text":   job_data.get("salary_text", ""),
            "salary_min":    clean_decimal(job_data.get("salary_min")),
            "salary_max":    clean_decimal(job_data.get("salary_max")),
            "job_type":      job_data.get("job_type", ""),
            "posted_date":   job_data.get("posted_date"),
            "source_portal": job_data.get("source_portal", "JobStreet"),
            "source_type":   "SCRAPED",
            "company":       None,
            "status":        "ACTIVE",
        },
    )

    # Synchronised, not merely added to. get_or_create alone never removed a
    # skill the employer had dropped from an updated advert, so extracted
    # skills only ever accumulated -- corrupting match scores, skill-demand
    # percentages, the skill gap and the resources recommended from it.
    #
    # required_level is preserved for skills that survive the refresh: it is a
    # reviewed judgement on company listings, and re-extraction is not a
    # reason to reset it to the default.
    matched_skills = extract_skills_from_text(
        f"{job_title} {job_data.get('description', '')}"
    )
    matched_ids = {skill.id for skill in matched_skills}

    existing = {
        relation.skill_id: relation
        for relation in JobSkill.objects.filter(job=listing)
    }
    stale_ids = set(existing) - matched_ids
    if stale_ids:
        JobSkill.objects.filter(job=listing, skill_id__in=stale_ids).delete()

    for skill in matched_skills:
        if skill.id not in existing:
            JobSkill.objects.create(
                job=listing, skill=skill, importance_level="MEDIUM")

    return listing, created


def save_scraped_jobs(jobs):
    """Bulk-save a list of scraped job dicts. Returns (created_count, updated_count)."""
    from .market_role_classifier import build_index

    created_count = 0
    updated_count = 0
    index = build_index()

    for job_data in jobs:
        _, created = save_scraped_job(job_data, index=index)
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
