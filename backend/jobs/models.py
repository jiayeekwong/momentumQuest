from django.db import models

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
    description = models.TextField(blank=True)

    salary_min = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
    )

    salary_max = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
    )

    source_portal = models.CharField(max_length=100, default="JobStreet")
    source_url = models.URLField(unique=True)

    scraped_time = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-scraped_time"]

    def __str__(self):
        return self.job_title


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

    extraction_method = models.CharField(
        max_length=50,
        default="keyword",
    )

    class Meta:
        unique_together = ("scraped_job", "skill")

    def __str__(self):
        return f"{self.scraped_job.job_title} - {self.skill.skill_name}"
