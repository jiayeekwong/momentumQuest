from rest_framework import serializers

from .models import JobCategory, ScrapedJob, ScrapeLog


class JobCategorySerializer(serializers.ModelSerializer):
    job_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = JobCategory
        fields = ["id", "category_name", "description", "job_count"]


class ScrapedJobListSerializer(serializers.ModelSerializer):
    job_category = serializers.StringRelatedField()
    skills = serializers.SerializerMethodField()

    class Meta:
        model = ScrapedJob
        fields = [
            "id", "job_title", "company_name", "location",
            "salary_text", "salary_min", "salary_max",
            "job_type", "posted_date", "source_url",
            "source_portal", "scraped_time", "job_category", "skills",
        ]

    def get_skills(self, obj):
        return [
            rel.skill.skill_name
            for rel in obj.scraped_job_skills.select_related("skill").all()
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
