from django.contrib import admin
from django.db.models import Count

from .models import (
    JobCategory,
    JobTitle,
    MarketRole,
    MarketRoleAlias,
    Skill,
    SkillAlias,
    SkillRelationship,
    SkillSource,
)








@admin.register(JobCategory)
class JobCategoryAdmin(admin.ModelAdmin):
    list_display = ("category_name", "job_count")
    search_fields = ("category_name",)

    def job_count(self, obj):
        # Scraped jobs now live in JobListing (source_type='SCRAPED').
        return obj.job_listings.filter(source_type="SCRAPED").count()
    job_count.short_description = "Scraped jobs"


class SkillSourceInline(admin.TabularInline):
    """Which catalogues vouch for this skill. Read-only: provenance is a record
    of where a name came from, and a hand-edited record proves nothing."""
    model = SkillSource
    extra = 0
    can_delete = False
    readonly_fields = ("source", "external_id", "external_label",
                       "source_version", "source_url", "source_type",
                       "created_at")

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Skill)
class SkillAdmin(admin.ModelAdmin):
    """The review queue as much as a browser.

    The MTO merge added 1,853 skills, ten of which it refused to switch on by
    itself. Filtering on catalogue_status and is_active is how those get
    worked through, so both are editable in the list.
    """
    list_display = ("skill_name", "skill_category", "skill_type",
                    "technical_domain", "catalogue_status", "is_active",
                    "job_link_count")
    list_editable = ("skill_category", "is_active")
    list_filter = ("catalogue_status", "is_active", "skill_category",
                   "skill_type")
    search_fields = ("skill_name", "skill_category", "technical_domain")
    list_per_page = 50
    inlines = [SkillSourceInline]
    actions = ("activate_skills", "deactivate_skills")

    def get_queryset(self, request):
        return (super().get_queryset(request)
                .annotate(_job_links=Count("job_skills")))

    @admin.display(description="Job links", ordering="_job_links")
    def job_link_count(self, obj):
        return obj._job_links

    @admin.action(description="Activate selected skills")
    def activate_skills(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, "%d skill(s) activated." % updated)

    @admin.action(description="Deactivate selected skills")
    def deactivate_skills(self, request, queryset):
        # Deactivating never deletes: existing job links and student skills
        # survive untouched, the name simply stops matching new text.
        updated = queryset.update(is_active=False)
        self.message_user(request, "%d skill(s) deactivated. Existing links "
                                   "are unaffected." % updated)


@admin.register(SkillAlias)
class SkillAliasAdmin(admin.ModelAdmin):
    list_display = ("alias_name", "skill", "source", "is_active",
                    "requires_context")
    list_editable = ("is_active", "requires_context")
    list_filter = ("source", "is_active", "requires_context")
    search_fields = ("alias_name", "skill__skill_name")
    list_per_page = 50
    autocomplete_fields = ("skill",)


@admin.register(SkillSource)
class SkillSourceAdmin(admin.ModelAdmin):
    list_display = ("skill", "source", "external_label", "source_version")
    list_filter = ("source",)
    search_fields = ("skill__skill_name", "external_label")
    autocomplete_fields = ("skill",)


@admin.register(SkillRelationship)
class SkillRelationshipAdmin(admin.ModelAdmin):
    """Recorded, and deliberately not acted on.

    "Svelte implies knowing JavaScript" is a prerequisite, not an equivalence.
    Nothing in extraction or matching reads this table today; it is here for a
    future recommender to use on purpose.
    """
    list_display = ("from_skill", "relationship_type", "to_skill", "source")
    list_filter = ("relationship_type", "source")
    search_fields = ("from_skill__skill_name", "to_skill__skill_name")
    autocomplete_fields = ("from_skill", "to_skill")


@admin.register(JobTitle)
class JobTitleAdmin(admin.ModelAdmin):
    list_display = ("title_name", "market_role", "career_level", "category")
    search_fields = ("title_name",)
    list_filter = ("market_role", "career_level", "category")


# ScrapeLog admin moved to job_listings/admin.py (model now lives in job_listings).


@admin.register(MarketRole)
class MarketRoleAdmin(admin.ModelAdmin):
    """The standardized career groups students choose between.

    Roles are loaded from data/market_roles.csv, which stays the source of
    truth -- editing here is for inspection and for taking a role out of
    circulation, not for growing the taxonomy.
    """
    list_display = ("name", "broad_area", "advert_count", "alias_count", "is_active")
    list_filter = ("broad_area", "is_active")
    search_fields = ("name", "normalized_name", "description")
    readonly_fields = ("normalized_name",)

    @admin.display(description="Adverts")
    def advert_count(self, obj):
        return obj.job_listings.filter(source_type="SCRAPED").count()

    @admin.display(description="Reviewed aliases")
    def alias_count(self, obj):
        return obj.aliases.count()


@admin.register(MarketRoleAlias)
class MarketRoleAliasAdmin(admin.ModelAdmin):
    """Reviewed market wording for a Market Role.

    The title is normalized on save, so it can be typed exactly as it reads on
    the advert. An alias states that a title is a genuine naming variation of
    a role -- never that it merely resembles one.
    """
    list_display = ("normalized_title", "market_role", "mapping_type",
                    "reviewed", "notes")
    list_filter = ("mapping_type", "reviewed", "market_role__broad_area")
    search_fields = ("normalized_title", "market_role__name", "notes")
    readonly_fields = ("created_time",)
