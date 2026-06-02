from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
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
        return (
            JobListing.objects
            .filter(status='ACTIVE')
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

        job = get_object_or_404(JobListing, pk=job_id, status='ACTIVE')

        # Check if already applied
        if JobApplication.objects.filter(student=student, job=job).exists():
            return Response({'detail': 'You have already applied to this job.'}, status=status.HTTP_400_BAD_REQUEST)

        application = JobApplication.objects.create(student=student, job=job)
        serializer = JobApplicationSerializer(application)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
