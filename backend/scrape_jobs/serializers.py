from rest_framework import serializers

from job_listings.models import JobListing, ScrapeLog
from .models import JobCategory, JobTitle


class JobCategorySerializer(serializers.ModelSerializer):
    job_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = JobCategory
        fields = ["id", "category_name", "description", "job_count"]


class JobTitleSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.category_name", default=None, read_only=True)

    class Meta:
        model = JobTitle
        fields = ["id", "title_name", "category_name"]


class ScrapedJobListSerializer(serializers.ModelSerializer):
    """Scraped jobs now live in JobListing (source_type='SCRAPED').

    Field names are kept identical to the old ScrapedJob API so the frontend
    needs no changes: `category` is exposed as `job_category`, and
    `posted_time` as `scraped_time`.
    """
    job_category = serializers.StringRelatedField(source="category")
    scraped_time = serializers.DateTimeField(source="posted_time", read_only=True)
    skills = serializers.SerializerMethodField()

    class Meta:
        model = JobListing
        fields = [
            "id", "job_title", "company_name", "location",
            "salary_text", "salary_min", "salary_max",
            "job_type", "posted_date", "source_url",
            "source_portal", "scraped_time", "job_category", "skills",
        ]

    def get_skills(self, obj):
        return [
            rel.skill.skill_name
            for rel in obj.job_skills.select_related("skill").all()
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
