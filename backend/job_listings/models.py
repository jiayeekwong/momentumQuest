from django.db import models

from accounts.models import Company, Student
from scrape_jobs.models import JobCategory, JobTitle, Skill


class JobListing(models.Model):
    class Status(models.TextChoices):
        ACTIVE = 'ACTIVE', 'Active'
        CLOSED = 'CLOSED', 'Closed'
        DRAFT  = 'DRAFT',  'Draft'

    class SourceType(models.TextChoices):
        COMPANY = 'COMPANY', 'Company-posted'
        SCRAPED = 'SCRAPED', 'Scraped'

    # company is null for scraped jobs (they have no MomentumQuest account)
    company          = models.ForeignKey(Company, on_delete=models.CASCADE,
                                         null=True, blank=True,
                                         related_name='job_listings')
    category         = models.ForeignKey(JobCategory, on_delete=models.SET_NULL,
                                         null=True, blank=True,
                                         related_name='job_listings')
    job_title        = models.CharField(max_length=255)
    job_title_ref    = models.ForeignKey(JobTitle, on_delete=models.SET_NULL,
                                         null=True, blank=True,
                                         related_name='job_listings')
    description      = models.TextField(blank=True)
    salary_min       = models.DecimalField(max_digits=10, decimal_places=2,
                                           null=True, blank=True)
    salary_max       = models.DecimalField(max_digits=10, decimal_places=2,
                                           null=True, blank=True)
    work_mode        = models.CharField(max_length=50, blank=True)
    experience_level = models.CharField(max_length=50, blank=True)
    closing_date     = models.DateField(null=True, blank=True)
    status           = models.CharField(max_length=10, choices=Status.choices,
                                        default=Status.ACTIVE)
    posted_time      = models.DateTimeField(auto_now_add=True)

    # Source discrimination + scraped-job fields (merged from ScrapedJob)
    source_type      = models.CharField(max_length=10, choices=SourceType.choices,
                                        default=SourceType.COMPANY)
    source_url       = models.URLField(null=True, blank=True, unique=True)
    source_portal    = models.CharField(max_length=100, blank=True)
    company_name     = models.CharField(max_length=255, blank=True)
    location         = models.CharField(max_length=255, blank=True)
    job_type         = models.CharField(max_length=100, blank=True)
    salary_text      = models.CharField(max_length=100, blank=True)
    posted_date      = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ['-posted_time']

    def __str__(self):
        employer = self.company.company_name if self.company else (self.company_name or "External")
        return f"{self.job_title} @ {employer}"


class JobSkill(models.Model):
    class ImportanceLevel(models.TextChoices):
        HIGH   = 'HIGH',   'High'
        MEDIUM = 'MEDIUM', 'Medium'
        LOW    = 'LOW',    'Low'

    job              = models.ForeignKey(JobListing, on_delete=models.CASCADE,
                                         related_name='job_skills')
    skill            = models.ForeignKey(Skill, on_delete=models.CASCADE,
                                         related_name='job_skills')
    importance_level = models.CharField(max_length=10,
                                        choices=ImportanceLevel.choices,
                                        default=ImportanceLevel.MEDIUM)

    class Meta:
        unique_together = ('job', 'skill')

    def __str__(self):
        return f"{self.job.job_title} — {self.skill.skill_name} ({self.importance_level})"


class JobApplication(models.Model):
    class Status(models.TextChoices):
        PENDING     = 'PENDING',     'Pending'
        REVIEWED    = 'REVIEWED',    'Reviewed'
        SHORTLISTED = 'SHORTLISTED', 'Shortlisted'
        ACCEPTED    = 'ACCEPTED',    'Accepted'
        REJECTED    = 'REJECTED',    'Rejected'

    student      = models.ForeignKey(Student, on_delete=models.CASCADE,
                                     related_name='job_applications')
    job          = models.ForeignKey(JobListing, on_delete=models.CASCADE,
                                     related_name='applications')
    cv_url       = models.URLField(blank=True)
    status       = models.CharField(max_length=15, choices=Status.choices,
                                    default=Status.PENDING)
    applied_time = models.DateTimeField(auto_now_add=True)
    is_read      = models.BooleanField(default=False)

    # Application-form answers (company-posted jobs)
    needs_work_permit = models.BooleanField(null=True, blank=True)
    available_from    = models.DateField(null=True, blank=True)
    phone             = models.CharField(max_length=30, blank=True)
    cover_note        = models.TextField(blank=True)

    class Meta:
        unique_together = ('student', 'job')
        ordering = ['-applied_time']

    def __str__(self):
        return f"{self.student.student_name} → {self.job.job_title} ({self.status})"


class ScrapeLog(models.Model):
    """Audit record of a job-scraping run (moved here from the scrape_jobs app)."""
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
