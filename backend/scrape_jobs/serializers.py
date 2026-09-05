from rest_framework import serializers

from job_listings.matching import MatchScoreMixin
from job_listings.models import JobListing, ScrapeLog
from .models import JobCategory, JobTitle, MarketRole






class JobCategorySerializer(serializers.ModelSerializer):
    job_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = JobCategory
        fields = ["id", "category_name", "description", "job_count"]


class JobTitleSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.category_name",
                                          default=None, read_only=True)
    market_role = serializers.CharField(source="market_role.name",
                                        default=None, read_only=True)

    class Meta:
        model = JobTitle
        fields = [
            "id", "title_name", "category_name", "career_level", "market_role",
        ]


class MarketRoleSerializer(serializers.ModelSerializer):
    """A standardized career group, as offered to a student."""

    advert_count = serializers.IntegerField(read_only=True, default=0)
    analysable = serializers.BooleanField(read_only=True, default=False)

    class Meta:
        model = MarketRole
        fields = ["id", "name", "broad_area", "description",
                  "advert_count", "analysable"]


class ScrapedJobListSerializer(MatchScoreMixin, serializers.ModelSerializer):
    """Scraped jobs now live in JobListing (source_type='SCRAPED').

    Field names are kept identical to the old ScrapedJob API so the frontend
    needs no changes: `category` is exposed as `job_category`, and
    `posted_time` as `scraped_time`.
    """
    job_category = serializers.StringRelatedField(source="category")
    scraped_time = serializers.DateTimeField(source="posted_time", read_only=True)
    skills = serializers.SerializerMethodField()
    # The proficiency each skill is wanted at, so the student page can show a
    # per-skill verdict that agrees with match_score instead of a name-only
    # tick. Kept separate from `skills` so the existing shape is unchanged.
    required_skill_levels = serializers.SerializerMethodField()
    # Proficiency-weighted, computed server-side against the logged-in
    # student. Null for anonymous visitors — see MatchScoreMixin.
    match_score = serializers.SerializerMethodField()
    # Whether the logged-in student has bookmarked this listing, so the save
    # button renders in the right state on first paint instead of flickering
    # after a second request.
    is_saved = serializers.SerializerMethodField()
    # Reported rather than filtered on: a saved listing that has since lapsed
    # still belongs in the student's list, labelled closed.
    status = serializers.CharField(read_only=True)

    class Meta:
        model = JobListing
        fields = [
            "id", "job_title", "company_name", "location",
            "salary_text", "salary_min", "salary_max",
            "job_type", "posted_date", "source_url",
            "source_portal", "scraped_time", "job_category", "skills",
            "required_skill_levels", "match_score", "is_saved", "status",
        ]

    def get_is_saved(self, obj):
        saved_ids = self.context.get("saved_job_ids")
        if saved_ids is None:
            return False
        return obj.id in saved_ids

    def get_skills(self, obj):
        # .all() rather than .select_related(): the queryset already
        # prefetches job_skills__skill, and re-filtering here would discard
        # that prefetch and re-query once per listing.
        return [rel.skill.skill_name for rel in obj.job_skills.all()]

    def get_required_skill_levels(self, obj):
        # Same prefetched rows as get_skills, so this adds no queries.
        return [
            {"skill": rel.skill.skill_name, "required_level": rel.required_level}
            for rel in obj.job_skills.all()
        ]


class ScrapedJobDetailSerializer(ScrapedJobListSerializer):
    """Same as list but includes full description."""
    class Meta(ScrapedJobListSerializer.Meta):
        fields = ScrapedJobListSerializer.Meta.fields + ["description"]



class ScrapeLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = ScrapeLog
        fields = [
            "id", "started_at", "finished_at", "status",
            "roles_scraped", "pages_attempted", "jobs_scraped",
            "jobs_created", "jobs_updated", "blocked_count", "error_message",
        ]
