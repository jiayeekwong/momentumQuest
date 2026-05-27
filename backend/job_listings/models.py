from django.db import models

from accounts.models import Company, Student
from scrape_jobs.models import JobCategory, Skill


class JobListing(models.Model):
    class Status(models.TextChoices):
        ACTIVE = 'ACTIVE', 'Active'
        CLOSED = 'CLOSED', 'Closed'
        DRAFT  = 'DRAFT',  'Draft'

    company          = models.ForeignKey(Company, on_delete=models.CASCADE,
                                         related_name='job_listings')
    category         = models.ForeignKey(JobCategory, on_delete=models.SET_NULL,
                                         null=True, blank=True,
                                         related_name='job_listings')
    job_title        = models.CharField(max_length=255)
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

    class Meta:
        ordering = ['-posted_time']

    def __str__(self):
        return f"{self.job_title} @ {self.company.company_name}"


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

    class Meta:
        unique_together = ('student', 'job')
        ordering = ['-applied_time']

    def __str__(self):
        return f"{self.student.student_name} → {self.job.job_title} ({self.status})"
