from django.db.models import Count, Q
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User, Student, Company
from accounts.permissions import IsStudent, IsCompany, IsAdminUserRole
from jobs.models import JobCategory, Skill, ScrapedJob, ScrapeLog
from jobs.serializers import ScrapeLogSerializer
from resources.models import Certificate  # used in admin dashboard only

from .models import Announcement
from .serializers import AnnouncementSerializer


class AnnouncementListView(generics.ListAPIView):
    """
    GET /api/dashboard/announcements/
    Latest announcements visible to authenticated students and admins.
    """
    queryset = Announcement.objects.select_related('admin').all()
    serializer_class = AnnouncementSerializer
    permission_classes = [IsAuthenticated]


class AnnouncementCreateView(generics.CreateAPIView):
    """
    POST /api/dashboard/announcements/create/
    Admin only — creates a new announcement.
    """
    serializer_class = AnnouncementSerializer
    permission_classes = [IsAdminUserRole]

    def perform_create(self, serializer):
        serializer.save(admin=self.request.user.admin_profile)


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
                'scraped_job_skills',
                filter=Q(scraped_job_skills__scraped_job__isnull=False),
            ))
            .filter(demand_count__gt=0)
            .order_by('-demand_count')[:5]
        )

        top_categories = (
            JobCategory.objects
            .annotate(job_count=Count('scraped_jobs'))
            .filter(job_count__gt=0)
            .order_by('-job_count')[:5]
        )

        return Response({
            'skills_count': skills_count,
            'announcements': AnnouncementSerializer(announcements, many=True).data,
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
            'total_scraped_jobs': ScrapedJob.objects.count(),
            'total_skills': Skill.objects.count(),
        }

        recent_logs = ScrapeLog.objects.all()[:5]
        recent_announcements = Announcement.objects.select_related('admin').all()[:5]

        return Response({
            'stats': stats,
            'recent_scrape_logs': ScrapeLogSerializer(recent_logs, many=True).data,
            'recent_announcements': AnnouncementSerializer(recent_announcements, many=True).data,
        })


class CompanyDashboardView(APIView):
    """
    GET /api/dashboard/company/
    Company dashboard with real hiring-pipeline stats.
    """
    permission_classes = [IsCompany]

    def get(self, request):
        from listings.models import JobListing, JobApplication

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
