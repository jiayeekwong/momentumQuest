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
