from django.contrib import admin
from django.utils.html import format_html

from .models import JobApplication, JobListing, JobSkill, ScrapeLog


@admin.register(JobListing)
class JobListingAdmin(admin.ModelAdmin):
    list_display   = ("job_title", "company", "category", "status", "work_mode",
                      "experience_level", "closing_date", "posted_time")
    list_filter    = ("status", "work_mode", "experience_level", "category")
    search_fields  = ("job_title", "company__company_name", "description")
    readonly_fields = ("posted_time",)


@admin.register(JobSkill)
class JobSkillAdmin(admin.ModelAdmin):
    list_display  = ("job", "skill", "importance_level")
    list_filter   = ("importance_level", "skill__skill_category")
    search_fields = ("job__job_title", "skill__skill_name")


@admin.register(JobApplication)
class JobApplicationAdmin(admin.ModelAdmin):
    list_display   = ("student", "job", "status", "applied_time", "is_read")
    list_filter    = ("status", "is_read")
    search_fields  = ("student__student_name", "job__job_title")
    readonly_fields = ("applied_time",)


@admin.register(ScrapeLog)
class ScrapeLogAdmin(admin.ModelAdmin):
    list_display = (
        "started_at", "finished_at", "status_badge",
        "jobs_scraped", "jobs_created", "jobs_updated", "blocked_count",
    )
    list_filter = ("status",)
    readonly_fields = (
        "started_at", "finished_at", "status", "roles_scraped",
        "pages_attempted", "jobs_scraped", "jobs_created",
        "jobs_updated", "blocked_count", "error_message",
    )

    def status_badge(self, obj):
        colours = {
            "SUCCESS": "green",
            "PARTIAL": "orange",
            "BLOCKED": "red",
            "FAILED":  "red",
        }
        colour = colours.get(obj.status, "grey")
        return format_html(
            '<span style="color:white;background:{};padding:2px 8px;border-radius:4px;font-weight:bold">{}</span>',
            colour, obj.status,
        )
    status_badge.short_description = "Status"

    def has_add_permission(self, request):
        return False  # logs are created by the scraper only
