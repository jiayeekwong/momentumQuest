import os
import uuid

from django.conf import settings
from django.core.files.storage import default_storage
from django.db.models import Count, Q
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User, Student, Company
from accounts.permissions import IsStudent, IsCompany, IsAdminUserRole
from scrape_jobs.models import JobCategory, Skill
from job_listings.models import JobListing, ScrapeLog
from scrape_jobs.serializers import ScrapeLogSerializer
from resources.models import Certificate  # used in admin dashboard only

from .models import Announcement
from .serializers import AnnouncementSerializer


class AnnouncementListView(generics.ListAPIView):
    """
    GET /api/dashboard/announcements/
    Returns announcements filtered by the caller's role:
      STUDENT  → EVERYONE + STUDENTS
      COMPANY  → EVERYONE + COMPANIES
      ADMIN    → all
    """
    serializer_class   = AnnouncementSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        role = self.request.user.role
        if role == 'STUDENT':
            return Announcement.objects.filter(
                audience__in=['EVERYONE', 'STUDENTS']
            ).select_related('admin')
        if role == 'COMPANY':
            return Announcement.objects.filter(
                audience__in=['EVERYONE', 'COMPANIES']
            ).select_related('admin')
        return Announcement.objects.select_related('admin').all()


class AnnouncementCreateView(generics.CreateAPIView):
    """
    POST /api/dashboard/announcements/create/
    Admin only — creates a new announcement.
    """
    serializer_class = AnnouncementSerializer
    permission_classes = [IsAdminUserRole]

    def perform_create(self, serializer):
        serializer.save(admin=self.request.user.admin_profile)


class AnnouncementFileUploadView(APIView):
    """
    POST /api/dashboard/announcements/upload/
    Admin uploads a file (poster, document). Returns the absolute URL to store
    in supporting_doc — keeps the Announcement model a plain URLField per ERD.
    """
    permission_classes = [IsAdminUserRole]

    def post(self, request):
        file = request.FILES.get('file')
        if not file:
            return Response({'detail': 'No file provided.'}, status=status.HTTP_400_BAD_REQUEST)

        ext  = os.path.splitext(file.name)[1].lower()
        name = f"announcements/{uuid.uuid4().hex}{ext}"
        saved_path = default_storage.save(name, file)
        url = request.build_absolute_uri(settings.MEDIA_URL + saved_path)
        return Response({'url': url}, status=status.HTTP_201_CREATED)


class AnnouncementDeleteView(generics.DestroyAPIView):
    """
    DELETE /api/dashboard/announcements/<id>/
    Admin only — deletes an announcement.
    """
    queryset           = Announcement.objects.all()
    serializer_class   = AnnouncementSerializer
    permission_classes = [IsAdminUserRole]


class StudentDashboardView(APIView):
    """
    GET /api/dashboard/student/
    Aggregated dashboard data for the logged-in student.
    Returns: latest announcements, job demand trends, certificate summary.
    """
    permission_classes = [IsStudent]

    def get(self, request):
        student = request.user.student_profile
        skills_count = student.student_skills.count()

        announcements = Announcement.objects.select_related('admin').all()[:3]

        top_skills = (
            Skill.objects
            .annotate(demand_count=Count(
                'job_skills',
                filter=Q(job_skills__job__source_type='SCRAPED'),
            ))
            .filter(demand_count__gt=0)
            .order_by('-demand_count')[:5]
        )

        top_categories = (
            JobCategory.objects
            .annotate(job_count=Count(
                'job_listings',
                filter=Q(job_listings__source_type='SCRAPED'),
            ))
            .filter(job_count__gt=0)
            .order_by('-job_count')[:5]
        )

        return Response({
            'skills_count': skills_count,
            'announcements': AnnouncementSerializer(announcements, many=True, context={'request': request}).data,
            'job_demand_trends': {
                'top_skills': [
                    {
                        'skill': s.skill_name,
                        'category': s.skill_category,
                        'demand_count': s.demand_count,
                    }
                    for s in top_skills
                ],
                'top_categories': [
                    {
                        'category_name': c.category_name,
                        'job_count': c.job_count,
                    }
                    for c in top_categories
                ],
            },
        })


class AdminDashboardView(APIView):
    """
    GET /api/dashboard/admin/
    System-wide KPIs for the admin: user counts, pending certs,
    scraped job stats, and recent scrape logs.
    """
    permission_classes = [IsAdminUserRole]

    def get(self, request):
        stats = {
            'total_users': User.objects.count(),
            'total_students': Student.objects.count(),
            'total_companies': Company.objects.count(),
            'pending_certificates': Certificate.objects.filter(verified_status='PENDING').count(),
            'total_scraped_jobs': JobListing.objects.filter(source_type='SCRAPED').count(),
            'total_skills': Skill.objects.count(),
        }

        recent_logs = ScrapeLog.objects.all()[:5]
        recent_announcements = Announcement.objects.select_related('admin').all()[:5]

        return Response({
            'stats': stats,
            'recent_scrape_logs': ScrapeLogSerializer(recent_logs, many=True).data,
            'recent_announcements': AnnouncementSerializer(recent_announcements, many=True, context={'request': request}).data,
        })


class CompanyDashboardView(APIView):
    """
    GET /api/dashboard/company/
    Company dashboard with real hiring-pipeline stats.
    """
    permission_classes = [IsCompany]

    def get(self, request):
        from job_listings.models import JobListing, JobApplication

        company = request.user.company_profile

        active_listings    = JobListing.objects.filter(company=company, status='ACTIVE').count()
        total_applications = JobApplication.objects.filter(job__company=company).count()
        shortlisted        = JobApplication.objects.filter(job__company=company, status='SHORTLISTED').count()

        return Response({
            'company_name':       company.company_name,
            'active_listings':    active_listings,
            'total_applications': total_applications,
            'shortlisted':        shortlisted,
        })
