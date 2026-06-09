import os
import uuid

from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from django.conf import settings
from django.core.files.storage import default_storage
from django.shortcuts import get_object_or_404

from accounts.permissions import IsCompany
from accounts.models import Student
from .models import JobApplication, JobListing
from .serializers import (
    JobApplicationSerializer,
    JobApplicationStatusSerializer,
    JobListingReadSerializer,
    JobListingSummarySerializer,
    JobListingWriteSerializer,
)


class CompanyJobListingView(APIView):
    permission_classes = [IsCompany]

    def get(self, request):
        company = request.user.company_profile
        listings = JobListing.objects.filter(company=company).prefetch_related('job_skills__skill', 'applications')
        serializer = JobListingSummarySerializer(listings, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = JobListingWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(company=request.user.company_profile)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class CompanyJobDetailView(APIView):
    permission_classes = [IsCompany]

    def _get_own_listing(self, pk, request):
        try:
            listing = JobListing.objects.select_related('category', 'company').prefetch_related('job_skills__skill', 'applications').get(pk=pk)
        except JobListing.DoesNotExist:
            return None, Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        if listing.company != request.user.company_profile:
            return None, Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        return listing, None

    def get(self, request, pk):
        listing, err = self._get_own_listing(pk, request)
        if err:
            return err
        return Response(JobListingReadSerializer(listing).data)

    def patch(self, request, pk):
        listing, err = self._get_own_listing(pk, request)
        if err:
            return err
        serializer = JobListingWriteSerializer(listing, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def delete(self, request, pk):
        listing, err = self._get_own_listing(pk, request)
        if err:
            return err
        listing.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class CompanyApplicationListView(APIView):
    permission_classes = [IsCompany]

    def get(self, request):
        company = request.user.company_profile
        apps = (
            JobApplication.objects
            .filter(job__company=company)
            .select_related('student__user', 'job')
            .prefetch_related('student__student_skills__skill', 'job__job_skills__skill')
        )
        serializer = JobApplicationSerializer(apps, many=True)
        return Response(serializer.data)


class CompanyApplicationStatusView(APIView):
    permission_classes = [IsCompany]

    def patch(self, request, pk):
        company = request.user.company_profile
        try:
            application = JobApplication.objects.get(pk=pk, job__company=company)
        except JobApplication.DoesNotExist:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        serializer = JobApplicationStatusSerializer(application, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class PublicJobListingView(generics.ListAPIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = JobListingReadSerializer

    def get_queryset(self):
        # Only company-posted jobs are applied to internally; scraped jobs are
        # served separately via /api/scrape-jobs/scraped/ (external redirect).
        return (
            JobListing.objects
            .filter(status='ACTIVE', source_type='COMPANY')
            .select_related('category', 'company')
            .prefetch_related('job_skills__skill', 'applications')
        )


class StudentJobApplicationView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        """
        POST /api/job-listings/applications/
        Student submits a job application.
        Body: { "job": <int job_id> }
        """
        student = get_object_or_404(Student, user=request.user)
        job_id = request.data.get('job')

        if not job_id:
            return Response({'detail': 'Job ID is required.'}, status=status.HTTP_400_BAD_REQUEST)

        # Students can only apply internally to company-posted jobs.
        job = get_object_or_404(JobListing, pk=job_id, status='ACTIVE', source_type='COMPANY')

        # Check if already applied
        if JobApplication.objects.filter(student=student, job=job).exists():
            return Response({'detail': 'You have already applied to this job.'}, status=status.HTTP_400_BAD_REQUEST)

        # Required application-form fields
        cv_url = request.data.get('cv_url', '').strip()
        if not cv_url:
            return Response({'detail': 'Please attach your CV.'}, status=status.HTTP_400_BAD_REQUEST)

        needs_work_permit = request.data.get('needs_work_permit', None)
        if needs_work_permit is None:
            return Response({'detail': 'Please answer the work-permit question.'},
                            status=status.HTTP_400_BAD_REQUEST)

        application = JobApplication.objects.create(
            student=student,
            job=job,
            cv_url=cv_url,
            needs_work_permit=bool(needs_work_permit),
            available_from=request.data.get('available_from') or None,
            phone=request.data.get('phone', ''),
            cover_note=request.data.get('cover_note', ''),
        )
        serializer = JobApplicationSerializer(application)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class CVUploadView(APIView):
    """
    POST /api/job-listings/cv/upload/
    Student uploads a CV file (PDF/Word). Returns the absolute URL to store in
    JobApplication.cv_url — mirrors the training-programme upload pattern so
    cv_url stays a URLField.
    """
    permission_classes = [permissions.IsAuthenticated]

    ALLOWED_EXTENSIONS = ('.pdf', '.doc', '.docx')

    def post(self, request):
        file = request.FILES.get('file')
        if not file:
            return Response({'detail': 'No file provided.'}, status=status.HTTP_400_BAD_REQUEST)

        ext = os.path.splitext(file.name)[1].lower()
        if ext not in self.ALLOWED_EXTENSIONS:
            return Response({'detail': 'CV must be a PDF or Word document.'},
                            status=status.HTTP_400_BAD_REQUEST)

        name = f"cv/{uuid.uuid4().hex}{ext}"
        saved_path = default_storage.save(name, file)
        url = request.build_absolute_uri(settings.MEDIA_URL + saved_path)
        return Response({'url': url}, status=status.HTTP_201_CREATED)
