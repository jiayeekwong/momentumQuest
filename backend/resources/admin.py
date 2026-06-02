from django.contrib import admin

from .models import Certificate, Course, LearningResource, ResourceScrapeLog, TrainingProgramme


@admin.register(LearningResource)
class LearningResourceAdmin(admin.ModelAdmin):
    list_display  = ("title", "platform", "type", "skill", "is_active", "scraped_at")
    search_fields = ("title", "platform", "url")
    list_filter   = ("platform", "type", "is_active", "skill__skill_category")
    readonly_fields = ("scraped_at",)


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display  = ("title", "skill", "department", "admin", "updated_at")
    search_fields = ("title", "department")
    list_filter   = ("department", "skill__skill_category")
    readonly_fields = ("updated_at",)


@admin.register(Certificate)
class CertificateAdmin(admin.ModelAdmin):
    list_display  = ("student", "skill", "source", "verified_status", "uploaded_time")
    search_fields = ("student__student_name", "skill__skill_name", "source")
    list_filter   = ("verified_status", "skill__skill_category")
    readonly_fields = ("uploaded_time",)


@admin.register(TrainingProgramme)
class TrainingProgrammeAdmin(admin.ModelAdmin):
    list_display  = ("title", "company", "skill", "approval_status", "submission_time")
    search_fields = ("title", "company__company_name")
    list_filter   = ("approval_status",)
    readonly_fields = ("submission_time",)


@admin.register(ResourceScrapeLog)
class ResourceScrapeLogAdmin(admin.ModelAdmin):
    list_display   = ("started_at", "status", "platforms_scraped", "resources_created",
                      "resources_updated", "resources_deactivated", "finished_at")
    list_filter    = ("status",)
    readonly_fields = ("started_at", "finished_at", "platforms_scraped", "resources_scraped",
                       "resources_created", "resources_updated", "resources_deactivated",
                       "error_message")
