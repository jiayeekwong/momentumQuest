from rest_framework import serializers

from .models import Certificate, Course, LearningResource


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
