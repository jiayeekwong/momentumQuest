from django.db import models
from django.utils import timezone

from accounts.models import AdminProfile, Student
from jobs.models import Skill


class LearningResource(models.Model):
    """
    Scraped from third-party platforms (freeCodeCamp, Coursera, Microsoft Learn, etc.).
    Students are redirected to the external URL — they do not enrol through MomentumQuest.
    """
    skill      = models.ForeignKey(Skill, on_delete=models.CASCADE,
                                   related_name="learning_resources")
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


class Course(models.Model):
    """
    University's own internal courses, managed by admin (UC-27).
    Different from LearningResource — these are not scraped from external platforms.
    """
    admin      = models.ForeignKey(AdminProfile, on_delete=models.SET_NULL,
                                   null=True, related_name="courses")
    skill      = models.ForeignKey(Skill, on_delete=models.CASCADE,
                                   related_name="courses")
    title      = models.CharField(max_length=255)
    course_url = models.URLField(blank=True)
    department = models.CharField(max_length=100, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["title"]

    def __str__(self):
        return self.title


class Certificate(models.Model):
    """
    Proof of completion uploaded by student after finishing an external course.
    Admin endorses (UC-25) to validate the skill.
    """
    class VerifiedStatus(models.TextChoices):
        PENDING  = "PENDING",  "Pending"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"

    student         = models.ForeignKey(Student, on_delete=models.CASCADE,
                                        related_name="certificates")
    skill           = models.ForeignKey(Skill, on_delete=models.CASCADE,
                                        related_name="certificates")
    admin           = models.ForeignKey(AdminProfile, on_delete=models.SET_NULL,
                                        null=True, blank=True,
                                        related_name="endorsed_certificates")
    cert_url        = models.URLField(blank=True)
    source          = models.CharField(max_length=100, blank=True)
    uploaded_time   = models.DateTimeField(auto_now_add=True)
    verified_status = models.CharField(
        max_length=20,
        choices=VerifiedStatus.choices,
        default=VerifiedStatus.PENDING,
    )

    class Meta:
        ordering = ["-uploaded_time"]

    def __str__(self):
        return f"{self.student} — {self.skill.skill_name} ({self.verified_status})"


class ResourceScrapeLog(models.Model):
    class Status(models.TextChoices):
        SUCCESS = "SUCCESS", "Success"
        PARTIAL = "PARTIAL", "Partial (some platforms failed)"
        FAILED  = "FAILED",  "Failed"

    started_at              = models.DateTimeField(auto_now_add=True)
    finished_at             = models.DateTimeField(null=True, blank=True)
    status                  = models.CharField(max_length=20, choices=Status.choices, default=Status.FAILED)
    platforms_scraped       = models.JSONField(default=list)
    resources_scraped       = models.IntegerField(default=0)
    resources_created       = models.IntegerField(default=0)
    resources_updated       = models.IntegerField(default=0)
    resources_deactivated   = models.IntegerField(default=0)
    error_message           = models.TextField(blank=True)

    class Meta:
        ordering = ["-started_at"]

    def __str__(self):
        finished = self.finished_at.strftime("%H:%M") if self.finished_at else "running"
        return f"[{self.status}] {self.started_at.strftime('%Y-%m-%d %H:%M')} → {finished} | +{self.resources_created} new"
