from django.contrib import admin

from .models import JobApplication, JobListing, JobSkill


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
