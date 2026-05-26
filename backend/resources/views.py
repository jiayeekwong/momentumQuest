from rest_framework import filters, generics
from rest_framework.permissions import AllowAny, IsAuthenticated

from .models import Certificate, Course, LearningResource
from .serializers import (
    CertificateSerializer,
    CertificateUploadSerializer,
    CourseSerializer,
    LearningResourceSerializer,
)


class LearningResourceListView(generics.ListAPIView):
    """
    GET /api/resources/
    List active scraped learning resources from external platforms.

    Query params:
      ?skill=      — filter by skill name
      ?platform=   — filter by platform (freeCodeCamp, Coursera, etc.)
      ?type=       — filter by type (Certification, Badge, etc.)
      ?search=     — search title
    """
    serializer_class   = LearningResourceSerializer
    permission_classes = [AllowAny]
    filter_backends    = [filters.SearchFilter, filters.OrderingFilter]
    search_fields      = ["title", "platform"]
    ordering_fields    = ["platform", "scraped_at"]
    ordering           = ["platform", "title"]

    def get_queryset(self):
        qs       = LearningResource.objects.filter(is_active=True).select_related("skill")
        skill    = self.request.query_params.get("skill")
        platform = self.request.query_params.get("platform")
        rtype    = self.request.query_params.get("type")

        if skill:
            qs = qs.filter(skill__skill_name__icontains=skill)
        if platform:
            qs = qs.filter(platform__icontains=platform)
        if rtype:
            qs = qs.filter(type__icontains=rtype)

        return qs


class CourseListView(generics.ListAPIView):
    """
    GET /api/resources/courses/
    List university courses managed by admin (UC-27).
    """
    serializer_class   = CourseSerializer
    permission_classes = [AllowAny]
    filter_backends    = [filters.SearchFilter]
    search_fields      = ["title", "department"]

    def get_queryset(self):
        qs         = Course.objects.select_related("skill", "admin")
        skill      = self.request.query_params.get("skill")
        department = self.request.query_params.get("department")

        if skill:
            qs = qs.filter(skill__skill_name__icontains=skill)
        if department:
            qs = qs.filter(department__icontains=department)

        return qs


class CourseDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET/PUT/DELETE /api/resources/courses/<id>/
    Admin manages individual university course records (UC-27).
    """
    queryset           = Course.objects.select_related("skill", "admin")
    serializer_class   = CourseSerializer
    permission_classes = [IsAuthenticated]


class CertificateListCreateView(generics.ListCreateAPIView):
    """
    GET  /api/resources/certificates/  — student views their own certificates
    POST /api/resources/certificates/  — student uploads a certificate (UC-10)
    """
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return CertificateUploadSerializer
        return CertificateSerializer

    def get_queryset(self):
        return Certificate.objects.filter(
            student__user=self.request.user
        ).select_related("skill", "student")

    def perform_create(self, serializer):
        serializer.save(student=self.request.user.student_profile)


class CertificateEndorseView(generics.UpdateAPIView):
    """
    PATCH /api/resources/certificates/<id>/endorse/
    Admin endorses or rejects a student certificate (UC-25).
    """
    queryset           = Certificate.objects.all()
    serializer_class   = CertificateSerializer
    permission_classes = [IsAuthenticated]

    def perform_update(self, serializer):
        serializer.save(admin=self.request.user.admin_profile)
