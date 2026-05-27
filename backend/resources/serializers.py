from rest_framework import serializers

from scrape_jobs.models import Skill
from .models import Certificate, Course, LearningResource, TrainingProgramme


class LearningResourceSerializer(serializers.ModelSerializer):
    skill = serializers.StringRelatedField()

    class Meta:
        model  = LearningResource
        fields = ["id", "skill", "title", "platform", "url", "type", "is_active", "scraped_at"]


class CourseSerializer(serializers.ModelSerializer):
    skill = serializers.StringRelatedField()
    admin = serializers.StringRelatedField()

    class Meta:
        model  = Course
        fields = ["id", "admin", "skill", "title", "course_url", "department", "updated_at"]


class CertificateSerializer(serializers.ModelSerializer):
    skill   = serializers.StringRelatedField()
    student = serializers.StringRelatedField()

    class Meta:
        model  = Certificate
        fields = [
            "id", "student", "skill", "cert_url", "source",
            "uploaded_time", "verified_status",
        ]


class CertificateUploadSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Certificate
        fields = ["skill", "cert_url", "source"]


class TrainingProgrammeSerializer(serializers.ModelSerializer):
    skill_name = serializers.CharField(write_only=True, required=False, allow_blank=True)
    skill      = serializers.StringRelatedField(read_only=True)
    company    = serializers.StringRelatedField(read_only=True)

    class Meta:
        model  = TrainingProgramme
        fields = [
            "id", "company", "skill", "skill_name",
            "title", "description", "programme_duration",
            "approval_status", "submission_time",
        ]
        read_only_fields = ["id", "company", "skill", "approval_status", "submission_time"]

    def create(self, validated_data):
        skill_name = validated_data.pop("skill_name", "").strip()
        skill = None
        if skill_name:
            skill = Skill.objects.filter(skill_name__iexact=skill_name).first()
            if not skill:
                skill = Skill.objects.create(skill_name=skill_name)
        return TrainingProgramme.objects.create(skill=skill, **validated_data)
