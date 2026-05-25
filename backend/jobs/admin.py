from django.contrib import admin

from .models import JobCategory, Skill, ScrapedJob, ScrapedJobSkill


@admin.register(JobCategory)
class JobCategoryAdmin(admin.ModelAdmin):
    list_display = ("category_name",)
    search_fields = ("category_name",)


@admin.register(Skill)
class SkillAdmin(admin.ModelAdmin):
    list_display = ("skill_name", "skill_category")
    search_fields = ("skill_name", "skill_category")
    list_filter = ("skill_category",)


@admin.register(ScrapedJob)
class ScrapedJobAdmin(admin.ModelAdmin):
    list_display = (
        "job_title",
        "job_category",
        "source_portal",
        "salary_min",
        "salary_max",
        "scraped_time",
    )

    search_fields = (
        "job_title",
        "description",
        "source_portal",
        "source_url",
    )

    list_filter = (
        "job_category",
        "source_portal",
        "scraped_time",
    )


@admin.register(ScrapedJobSkill)
class ScrapedJobSkillAdmin(admin.ModelAdmin):
    list_display = (
        "scraped_job",
        "skill",
        "extraction_method",
    )

    search_fields = (
        "scraped_job__job_title",
        "skill__skill_name",
    )

    list_filter = (
        "extraction_method",
        "skill",
    )
