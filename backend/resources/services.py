import logging

from django.utils import timezone

from scrape_jobs.models import Skill
from .models import LearningResource, ResourceScrapeLog

logger = logging.getLogger(__name__)


def save_learning_resource(resource_data):
    """Save one learning resource linked to a Skill. Returns (instance, created)."""
    skill_name = resource_data.get("skill_name", "").strip()
    url        = resource_data.get("url", "").strip()
    title      = resource_data.get("title", "").strip()

    title = title[:255]

    if not skill_name or not url or not title:
        return None, False

    try:
        skill = Skill.objects.get(skill_name__iexact=skill_name)
    except Skill.DoesNotExist:
        logger.warning("Skill not found in DB, skipping resource: %s", skill_name)
        return None, False

    instance, created = LearningResource.objects.update_or_create(
        skill=skill,
        url=url,
        defaults={
            "title":     title,
            "platform":  resource_data.get("platform", ""),
            "type":      resource_data.get("type", "Course"),
            "is_active": True,
        },
    )
    return instance, created


def save_learning_resources(resources):
    """Bulk-save resource dicts. Returns (created_count, updated_count)."""
    created_count = 0
    updated_count = 0
    for data in resources:
        instance, created = save_learning_resource(data)
        if created:
            created_count += 1
        elif instance is not None:
            updated_count += 1
    return created_count, updated_count


def deactivate_url_skill_conflicts(platform_name, url_skill_map):
    """
    For each URL in the latest scrape, deactivate any existing record for that
    URL that was previously matched to a *different* skill (e.g. a false 'R'
    match from old substring logic). Only operates on is_active=True records.
    Returns count of deactivated records.
    """
    deactivated = 0
    for url, skill_name in url_skill_map.items():
        try:
            skill = Skill.objects.get(skill_name__iexact=skill_name)
        except Skill.DoesNotExist:
            continue
        n = (
            LearningResource.objects
            .filter(platform=platform_name, url=url, is_active=True)
            .exclude(skill=skill)
            .update(is_active=False)
        )
        deactivated += n
    if deactivated:
        logger.info("%s: deactivated %d wrong-skill duplicates.", platform_name, deactivated)
    return deactivated


def deactivate_stale_resources(platform_name, active_urls):
    """
    Mark resources from a platform as inactive if their URL was not in the
    latest scrape. Only call for platforms that scraped successfully.
    Returns count of deactivated records.
    """
    deactivated = (
        LearningResource.objects
        .filter(platform=platform_name, is_active=True)
        .exclude(url__in=active_urls)
        .update(is_active=False)
    )
    if deactivated:
        logger.info("%s: deactivated %d stale resource(s).", platform_name, deactivated)
    return deactivated


def save_course_catalogue(courses):
    """Upsert scraped catalogue rows. Returns (created, updated).

    Nothing here looks at skills. A course is stored because it exists in the
    category, which is the whole point of separating the two passes.
    """
    from resources.models import CourseCatalogue

    created = updated = 0
    for data in courses:
        url = (data.get("url") or "").strip()
        if not url:
            continue
        row, was_created = CourseCatalogue.objects.update_or_create(
            url=url,
            defaults={
                "title":      (data.get("title") or "")[:255],
                "platform":   data.get("platform") or "Coursera",
                "type":       data.get("type") or "Course",
                "categories": data.get("categories") or [],
                "card_text":  data.get("card_text") or "",
                "is_active":  True,
            },
        )
        if was_created:
            created += 1
        else:
            updated += 1
    return created, updated


def map_catalogue_to_skills(platform_name="Coursera", categories=None):
    """Turn catalogue rows into LearningResource rows, one per (skill, course).

    The second of the two passes. It reads only the database, so it can be re-run
    whenever the Skill table grows or the matching improves, without going back
    to the network -- which is the reason the catalogue exists.

    Matching is over the card's text as well as the title. The old scraper
    matched titles alone, so "Google Data Analytics Professional Certificate"
    was discarded despite its card naming SQL, R and Tableau.

    A course matching several skills produces several rows; that is what
    (skill, url) uniqueness is for. A course matching none produces none and
    stays in the catalogue.

    Returns (created, updated, unmapped_course_count).
    """
    from resources.models import CourseCatalogue
    from resources.scraper import skill_matches_title

    rows = CourseCatalogue.objects.filter(platform=platform_name, is_active=True)
    if categories:
        matching = CourseCatalogue.objects.none()
        for category in categories:
            matching = matching | rows.filter(categories__contains=[category])
        rows = matching.distinct()

    # Read once, not once per course: this loop is O(courses x skills) and the
    # Skill table is ~2,100 rows.
    skills = list(Skill.objects.values_list("id", "skill_name"))

    created = updated = unmapped = 0
    for course in rows:
        haystack = f"{course.title} {course.card_text}"
        matched_any = False
        for skill_id, skill_name in skills:
            if not skill_matches_title(skill_name, haystack):
                continue
            matched_any = True
            _, was_created = LearningResource.objects.update_or_create(
                skill_id=skill_id,
                url=course.url,
                defaults={
                    "title":     course.title,
                    "platform":  course.platform,
                    "type":      course.type,
                    "is_active": True,
                },
            )
            if was_created:
                created += 1
            else:
                updated += 1
        if not matched_any:
            unmapped += 1

    logger.info(
        "%s: mapped %d new and %d existing resource(s); %d course(s) matched "
        "no known skill and stay in the catalogue.",
        platform_name, created, updated, unmapped,
    )
    return created, updated, unmapped


def create_resource_scrape_log(platforms):
    return ResourceScrapeLog.objects.create(platforms_scraped=platforms)


def finish_resource_scrape_log(log, status, resources_created, resources_updated,
                                resources_deactivated, error_message=""):
    log.finished_at             = timezone.now()
    log.status                  = status
    log.resources_scraped       = resources_created + resources_updated
    log.resources_created       = resources_created
    log.resources_updated       = resources_updated
    log.resources_deactivated   = resources_deactivated
    log.error_message           = error_message
    log.save()
