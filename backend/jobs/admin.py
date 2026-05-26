from django.contrib import admin
from django.utils.html import format_html

from .models import JobCategory, Skill, ScrapedJob, ScrapedJobSkill, ScrapeLog


@admin.register(JobCategory)
class JobCategoryAdmin(admin.ModelAdmin):
    list_display = ("category_name", "job_count")
    search_fields = ("category_name",)

    def job_count(self, obj):
        return obj.scraped_jobs.count()
    job_count.short_description = "Jobs"


@admin.register(Skill)
class SkillAdmin(admin.ModelAdmin):
    list_display = ("skill_name", "skill_category")
    search_fields = ("skill_name", "skill_category")
    list_filter = ("skill_category",)


@admin.register(ScrapedJob)
class ScrapedJobAdmin(admin.ModelAdmin):
    list_display = (
        "job_title", "company_name", "location",
        "job_category", "job_type", "salary_text",
        "posted_date", "scraped_time",
    )
    search_fields = ("job_title", "company_name", "location", "description")
    list_filter = ("job_category", "job_type", "source_portal", "scraped_time")
    readonly_fields = ("scraped_time", "jobstreet_link")

    def jobstreet_link(self, obj):
        return format_html('<a href="{}" target="_blank">View on JobStreet</a>', obj.source_url)
    jobstreet_link.short_description = "JobStreet URL"


@admin.register(ScrapedJobSkill)
class ScrapedJobSkillAdmin(admin.ModelAdmin):
    list_display = ("scraped_job", "skill", "extraction_method")
    search_fields = ("scraped_job__job_title", "skill__skill_name")
    list_filter = ("extraction_method", "skill__skill_category")



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
