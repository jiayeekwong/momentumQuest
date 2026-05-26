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


class ScrapedJob(models.Model):
    job_category = models.ForeignKey(
        JobCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="scraped_jobs",
    )

    job_title = models.CharField(max_length=255)
    company_name = models.CharField(max_length=255, blank=True)
    location = models.CharField(max_length=255, blank=True)
    description = models.TextField(blank=True)
    salary_text = models.CharField(max_length=100, blank=True)

    salary_min = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )
    salary_max = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )

    job_type = models.CharField(max_length=100, blank=True)
    posted_date = models.DateField(null=True, blank=True)

    source_portal = models.CharField(max_length=100, default="JobStreet")
    source_url = models.URLField(unique=True)
    scraped_time = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-scraped_time"]

    def __str__(self):
        return f"{self.job_title} @ {self.company_name}"


class ScrapedJobSkill(models.Model):
    scraped_job = models.ForeignKey(
        ScrapedJob,
        on_delete=models.CASCADE,
        related_name="scraped_job_skills",
    )
    skill = models.ForeignKey(
        Skill,
        on_delete=models.CASCADE,
        related_name="scraped_job_skills",
    )
    extraction_method = models.CharField(max_length=50, default="keyword")

    class Meta:
        unique_together = ("scraped_job", "skill")

    def __str__(self):
        return f"{self.scraped_job.job_title} — {self.skill.skill_name}"


class LearningResource(models.Model):
    skill    = models.ForeignKey(
        Skill,
        on_delete=models.CASCADE,
        related_name="learning_resources",
    )
    title      = models.CharField(max_length=255)
    platform   = models.CharField(max_length=100)
    url        = models.URLField()
    type       = models.CharField(max_length=100)
    is_active  = models.BooleanField(default=True)
    scraped_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("skill", "url")
        ordering = ["platform", "title"]

    def __str__(self):
        return f"{self.title} [{self.platform}] — {self.skill.skill_name}"


class ScrapeLog(models.Model):
    class Status(models.TextChoices):
        SUCCESS = "SUCCESS", "Success"
        BLOCKED = "BLOCKED", "Blocked by Anti-Bot"
        PARTIAL = "PARTIAL", "Partial (some pages blocked)"
        FAILED  = "FAILED",  "Failed"

    started_at     = models.DateTimeField(auto_now_add=True)
    finished_at    = models.DateTimeField(null=True, blank=True)
    status         = models.CharField(max_length=20, choices=Status.choices, default=Status.FAILED)
    roles_scraped  = models.JSONField(default=list)
    pages_attempted = models.IntegerField(default=0)
    jobs_scraped   = models.IntegerField(default=0)
    jobs_created   = models.IntegerField(default=0)
    jobs_updated   = models.IntegerField(default=0)
    blocked_count  = models.IntegerField(default=0)
    error_message  = models.TextField(blank=True)

    class Meta:
        ordering = ["-started_at"]

    def __str__(self):
        finished = self.finished_at.strftime("%H:%M") if self.finished_at else "running"
        return f"[{self.status}] {self.started_at.strftime('%Y-%m-%d %H:%M')} → {finished} | +{self.jobs_created} new"
