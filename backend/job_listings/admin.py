from django.contrib import admin
from django.utils import timezone
from django.utils.html import format_html

from .models import (
    JobApplication, JobListing, JobSkill, MarketRoleCandidate, ScrapeLog,
)


@admin.register(JobListing)
class JobListingAdmin(admin.ModelAdmin):
    list_display   = (
        "job_title", "market_role", "classification_method", "career_level",
        "company", "category", "status", "posted_time",
    )
    list_filter    = (
        "classification_method", "market_role__broad_area", "market_role",
        "career_level", "status", "work_mode", "experience_level", "category",
    )
    search_fields  = (
        "job_title", "normalized_job_title", "market_role__name",
        "company__company_name", "description",
    )
    readonly_fields = (
        "posted_time", "normalized_job_title", "classified_time",
    )

    def save_model(self, request, obj, form, change):
        """An administrator setting the Market Role by hand is the strongest
        evidence there is, so it is recorded as a human decision rather than
        left looking like a classifier result."""
        if "market_role" in form.changed_data:
            obj.classification_method = "HUMAN_REVIEW"
            obj.classification_evidence = (
                "Set by %s in the admin." % request.user.get_username()
            )
            obj.classified_time = timezone.now()
        super().save_model(request, obj, form, change)


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


@admin.register(MarketRoleCandidate)
class MarketRoleCandidateAdmin(admin.ModelAdmin):
    """The review queue for evidence that may not classify on its own.

    A title naming two careers, and any similarity-ranked suggestion, land
    here rather than writing JobListing.market_role -- see the model
    docstring. Approving is what promotes a candidate into a classification,
    and the excerpt is shown in the list so a reviewer can judge without
    opening each advert.
    """
    list_display  = (
        "listing_title", "market_role", "source", "status",
        "confidence", "excerpt", "created_time",
    )
    list_filter   = ("status", "source", "market_role__broad_area", "market_role")
    search_fields = ("listing__job_title", "market_role__name", "evidence_excerpt")
    readonly_fields = (
        "listing", "market_role", "source", "confidence",
        "evidence_excerpt", "created_time", "reviewed_time",
    )
    actions = ("approve_candidates", "reject_candidates")

    @admin.display(description="Listing")
    def listing_title(self, obj):
        return obj.listing.job_title

    @admin.display(description="Evidence")
    def excerpt(self, obj):
        text = obj.evidence_excerpt or ""
        return format_html("<span title={}>{}</span>",
                           text, text[:90] + ("..." if len(text) > 90 else ""))

    @admin.action(description="Approve: assign this Market Role to the listing")
    def approve_candidates(self, request, queryset):
        promoted = 0
        for candidate in queryset.select_related("listing", "market_role"):
            listing = candidate.listing
            listing.market_role = candidate.market_role
            # HUMAN_REVIEW, not the candidate's own source: a person decided
            # this, and the provenance should say so rather than crediting the
            # signal that merely proposed it.
            listing.classification_method = "HUMAN_REVIEW_%s" % candidate.source
            listing.classification_evidence = candidate.evidence_excerpt
            listing.classified_time = timezone.now()
            listing.save(update_fields=[
                "market_role", "classification_method",
                "classification_evidence", "classified_time",
            ])
            candidate.status = MarketRoleCandidate.Status.APPROVED
            candidate.reviewed_time = timezone.now()
            candidate.save(update_fields=["status", "reviewed_time"])
            promoted += 1
        self.message_user(request, "%d candidate(s) promoted to a Market Role." % promoted)

    @admin.action(description="Reject: this evidence does not identify the role")
    def reject_candidates(self, request, queryset):
        rejected = queryset.update(
            status=MarketRoleCandidate.Status.REJECTED,
            reviewed_time=timezone.now(),
        )
        self.message_user(request, "%d candidate(s) rejected." % rejected)
