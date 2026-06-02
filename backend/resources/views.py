import os
import uuid

from django.conf import settings
from django.core.files.storage import default_storage
from rest_framework import filters, generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsAdminUserRole, IsCompany
from .models import Certificate, Course, LearningResource, TrainingProgramme
from .serializers import (
    CertificateSerializer,
    CertificateUploadSerializer,
    CourseSerializer,
    CourseWriteSerializer,
    LearningResourceSerializer,
    TrainingProgrammeReviewSerializer,
    TrainingProgrammeSerializer,
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


class CourseListView(generics.ListCreateAPIView):
    """
    GET  /api/resources/courses/ — list all university courses (public)
    POST /api/resources/courses/ — admin creates a new course
    """
    filter_backends = [filters.SearchFilter]
    search_fields   = ["title", "department"]

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsAdminUserRole()]
        return [AllowAny()]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return CourseWriteSerializer
        return CourseSerializer

    def get_queryset(self):
        qs         = Course.objects.select_related("skill", "admin")
        skill      = self.request.query_params.get("skill")
        department = self.request.query_params.get("department")

        if skill:
            qs = qs.filter(skill__skill_name__icontains=skill)
        if department:
            qs = qs.filter(department__icontains=department)

        return qs

    def perform_create(self, serializer):
        serializer.save(admin=self.request.user.admin_profile)


class CourseDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET/PATCH/DELETE /api/resources/courses/<id>/
    Admin manages individual university course records.
    """
    queryset           = Course.objects.select_related("skill", "admin")
    permission_classes = [IsAdminUserRole]

    def get_serializer_class(self):
        if self.request.method in ("PUT", "PATCH"):
            return CourseWriteSerializer
        return CourseSerializer


class CertificateListCreateView(generics.ListCreateAPIView):
    """
    GET  /api/resources/certificates/  — student views own certs; admin sees all
    POST /api/resources/certificates/  — student uploads a certificate
    """
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return CertificateUploadSerializer
        return CertificateSerializer

    def get_queryset(self):
        if self.request.user.role == "ADMIN":
            return Certificate.objects.select_related("skill", "student").order_by("-uploaded_time")
        return Certificate.objects.filter(
            student__user=self.request.user
        ).select_related("skill", "student")

    def perform_create(self, serializer):
        serializer.save(student=self.request.user.student_profile)


class CertificateEndorseView(generics.UpdateAPIView):
    """
    PATCH /api/resources/certificates/<id>/endorse/
    Admin endorses or rejects a student certificate.
    """
    queryset           = Certificate.objects.all()
    serializer_class   = CertificateSerializer
    permission_classes = [IsAdminUserRole]

    def perform_update(self, serializer):
        serializer.save(admin=self.request.user.admin_profile)


class CompanyTrainingView(APIView):
    """
    GET  /api/resources/training/  — company lists their own submitted programmes
    POST /api/resources/training/  — company submits a new training programme
    """
    permission_classes = [IsCompany]

    def get(self, request):
        company = request.user.company_profile
        qs = TrainingProgramme.objects.filter(company=company).select_related('skill')
        serializer = TrainingProgrammeSerializer(qs, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = TrainingProgrammeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(company=request.user.company_profile)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class TrainingFileUploadView(APIView):
    """
    POST /api/resources/training/upload/
    Company uploads a file (brochure, syllabus, poster). Returns the absolute URL
    to store in supporting_doc — keeps TrainingProgramme.supporting_doc a URLField.
    """
    permission_classes = [IsCompany]

    def post(self, request):
        file = request.FILES.get('file')
        if not file:
            return Response({'detail': 'No file provided.'}, status=status.HTTP_400_BAD_REQUEST)

        ext  = os.path.splitext(file.name)[1].lower()
        name = f"training/{uuid.uuid4().hex}{ext}"
        saved_path = default_storage.save(name, file)
        url = request.build_absolute_uri(settings.MEDIA_URL + saved_path)
        return Response({'url': url}, status=status.HTTP_201_CREATED)


class AdminTrainingListView(generics.ListAPIView):
    """
    GET /api/resources/training/admin/
    Admin sees all training programme submissions across all companies,
    newest first. Optional filter: ?status=PENDING|APPROVED|REJECTED.
    """
    serializer_class   = TrainingProgrammeSerializer
    permission_classes = [IsAdminUserRole]

    def get_queryset(self):
        qs = TrainingProgramme.objects.select_related(
            'skill', 'company'
        ).order_by('-submission_time')

        status_param = self.request.query_params.get('status')
        if status_param:
            qs = qs.filter(approval_status=status_param.upper())
        return qs


class AdminTrainingReviewView(generics.UpdateAPIView):
    """
    PATCH /api/resources/training/admin/<int:pk>/review/
    Admin approves or rejects a training programme submission.
    Stamps the reviewing admin on save.
    """
    queryset           = TrainingProgramme.objects.all()
    serializer_class   = TrainingProgrammeReviewSerializer
    permission_classes = [IsAdminUserRole]
    http_method_names  = ['patch', 'options', 'head']

    def perform_update(self, serializer):
        serializer.save(admin=self.request.user.admin_profile)


class ApprovedTrainingListView(generics.ListAPIView):
    """
    GET /api/resources/training/approved/
    Any authenticated user (students) sees only APPROVED programmes,
    with skill + company shown.
    """
    serializer_class   = TrainingProgrammeSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return TrainingProgramme.objects.filter(
            approval_status=TrainingProgramme.ApprovalStatus.APPROVED
        ).select_related('skill', 'company').order_by('-submission_time')
