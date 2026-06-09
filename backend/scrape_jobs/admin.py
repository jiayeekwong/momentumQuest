from django.contrib import admin

from .models import JobCategory, JobTitle, Skill, SkillAlias


@admin.register(JobCategory)
class JobCategoryAdmin(admin.ModelAdmin):
    list_display = ("category_name", "job_count")
    search_fields = ("category_name",)

    def job_count(self, obj):
        # Scraped jobs now live in JobListing (source_type='SCRAPED').
        return obj.job_listings.filter(source_type="SCRAPED").count()
    job_count.short_description = "Scraped jobs"


@admin.register(Skill)
class SkillAdmin(admin.ModelAdmin):
    list_display = ("skill_name", "skill_category")
    search_fields = ("skill_name", "skill_category")
    list_filter = ("skill_category",)


@admin.register(SkillAlias)
class SkillAliasAdmin(admin.ModelAdmin):
    list_display = ("alias_name", "skill")
    search_fields = ("alias_name", "skill__skill_name")


@admin.register(JobTitle)
class JobTitleAdmin(admin.ModelAdmin):
    list_display = ("title_name", "category")
    search_fields = ("title_name",)
    list_filter = ("category",)


# ScrapeLog admin moved to job_listings/admin.py (model now lives in job_listings).
