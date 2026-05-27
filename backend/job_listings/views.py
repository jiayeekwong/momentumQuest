from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsCompany
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
            listing = JobListing.objects.get(pk=pk)
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
