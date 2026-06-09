from django.db import models
from django.utils import timezone


class JobCategory(models.Model):
    category_name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)

    class Meta:
        verbose_name_plural = "Job categories"

    def __str__(self):
        return self.category_name


class Skill(models.Model):
    skill_name = models.CharField(max_length=100, unique=True)
    skill_category = models.CharField(max_length=100, blank=True)

    def __str__(self):
        return self.skill_name


class SkillAlias(models.Model):
    """Alternate names for a skill (e.g. 'JS' -> JavaScript, 'k8s' -> Kubernetes).

    Used by the skill extractor so scraped job descriptions match the canonical
    Skill even when they use a shorthand.
    """
    skill = models.ForeignKey(Skill, on_delete=models.CASCADE, related_name="aliases")
    alias_name = models.CharField(max_length=100, unique=True)

    class Meta:
        verbose_name_plural = "Skill aliases"
        ordering = ["alias_name"]

    def __str__(self):
        return f"{self.alias_name} -> {self.skill.skill_name}"


class JobTitle(models.Model):
    """Normalised job title (e.g. 'Junior React Developer'), grouped under a
    JobCategory. JobListing references this via job_title_ref, and students
    pick target titles from here (accounts.StudentTargetJob).
    """
    title_name = models.CharField(max_length=255, unique=True)
    category = models.ForeignKey(
        JobCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="job_titles",
    )

    class Meta:
        ordering = ["title_name"]

    def __str__(self):
        return self.title_name


# Scraped jobs were merged into job_listings.JobListing (source_type='SCRAPED').
# See job_listings/migrations/0003_migrate_scraped_jobs.py for the data move.
# ScrapeLog now lives in the job_listings app (job_listings.models.ScrapeLog).
