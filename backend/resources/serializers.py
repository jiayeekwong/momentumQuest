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


class CourseWriteSerializer(serializers.ModelSerializer):
    skill_name = serializers.CharField(write_only=True, required=True)

    class Meta:
        model  = Course
        fields = ["id", "title", "department", "course_url", "skill_name", "updated_at"]
        read_only_fields = ["id", "updated_at"]

    def create(self, validated_data):
        skill_name = validated_data.pop("skill_name", "").strip()
        skill = None
        if skill_name:
            skill = Skill.objects.filter(skill_name__iexact=skill_name).first()
            if not skill:
                skill = Skill.objects.create(skill_name=skill_name)
        return Course.objects.create(skill=skill, **validated_data)

    def update(self, instance, validated_data):
        skill_name = validated_data.pop("skill_name", "").strip()
        if skill_name:
            skill = Skill.objects.filter(skill_name__iexact=skill_name).first()
            if not skill:
                skill = Skill.objects.create(skill_name=skill_name)
            instance.skill = skill
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance


class CertificateSerializer(serializers.ModelSerializer):
    skill        = serializers.StringRelatedField()
    student      = serializers.StringRelatedField()
    student_name = serializers.SerializerMethodField()

    class Meta:
        model  = Certificate
        fields = [
            "id", "student", "student_name", "skill", "cert_url", "source",
            "uploaded_time", "verified_status",
        ]

    def get_student_name(self, obj):
        return obj.student.student_name if obj.student else None


class CertificateUploadSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Certificate
        fields = ["skill", "cert_url", "source"]


class TrainingProgrammeSerializer(serializers.ModelSerializer):
    skill_name   = serializers.CharField(write_only=True, required=False, allow_blank=True)
    skill        = serializers.StringRelatedField(read_only=True)
    company      = serializers.StringRelatedField(read_only=True)
    company_name = serializers.SerializerMethodField()

    class Meta:
        model  = TrainingProgramme
        fields = [
            "id", "company", "company_name", "skill", "skill_name",
            "title", "description", "programme_duration", "supporting_doc",
            "approval_status", "submission_time",
        ]
        read_only_fields = ["id", "company", "skill", "approval_status", "submission_time"]

    def get_company_name(self, obj):
        return obj.company.company_name if obj.company else None

    def create(self, validated_data):
        skill_name = validated_data.pop("skill_name", "").strip()
        skill = None
        if skill_name:
            skill = Skill.objects.filter(skill_name__iexact=skill_name).first()
            if not skill:
                skill = Skill.objects.create(skill_name=skill_name)
        return TrainingProgramme.objects.create(skill=skill, **validated_data)


class TrainingProgrammeReviewSerializer(serializers.ModelSerializer):
    """
    Admin review serializer — only `approval_status` is writable.
    The title/company/skill fields are exposed read-only so the admin UI
    can render context without a second request.
    """
    company = serializers.StringRelatedField(read_only=True)
    skill   = serializers.StringRelatedField(read_only=True)

    class Meta:
        model  = TrainingProgramme
        fields = ["id", "title", "company", "skill", "approval_status"]
        read_only_fields = ["id", "title"]

    def validate_approval_status(self, value):
        allowed = {
            TrainingProgramme.ApprovalStatus.APPROVED,
            TrainingProgramme.ApprovalStatus.REJECTED,
        }
        if value not in allowed:
            raise serializers.ValidationError(
                "approval_status must be either 'APPROVED' or 'REJECTED'."
            )
        return value
