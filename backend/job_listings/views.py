import logging
import os
import uuid

from rest_framework import generics, permissions, serializers as drf_serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView
from django.conf import settings
from django.core.files.storage import default_storage
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone

from accounts.permissions import IsCompany, IsStudent
from resources.file_validation import (
    MAX_BYTES as MAX_UPLOAD_BYTES, InvalidUpload, validate_document,
)
from . import cv_receipt
from .cv_parser import parse_cv
from accounts.models import Student, UserConsent
from accounts.privacy_notice import CURRENT_VERSION
from .models import JobApplication, JobListing

logger = logging.getLogger(__name__)

from .serializers import (
    JobApplicationCreateSerializer,
    JobApplicationSerializer,
    JobApplicationStatusSerializer,
    JobListingReadSerializer,
    JobListingSummarySerializer,
    JobListingWriteSerializer,
    StudentApplicationSerializer,
)


class CompanyJobListingView(APIView):
    permission_classes = [IsCompany]

    def get(self, request):
        company = request.user.company_profile
        listings = JobListing.objects.filter(company=company).select_related(
        ).prefetch_related('job_skills__skill', 'applications')
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
            listing = JobListing.objects.select_related(
                'category', 'company'
            ).prefetch_related('job_skills__skill', 'applications').get(pk=pk)
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
        previous_status = application.status
        serializer = JobApplicationStatusSerializer(application, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        # Stamped only on a real change, so re-saving the same status does not
        # resurface an old decision at the top of the student's notifications.
        if serializer.validated_data.get('status', previous_status) != previous_status:
            serializer.save(status_changed_at=timezone.now())
        else:
            serializer.save()
        return Response(serializer.data)


class PublicJobListingView(generics.ListAPIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = JobListingReadSerializer

    def get_queryset(self):
        # Only company-posted jobs are applied to internally; scraped jobs are
        # served separately via /api/scrape-jobs/scraped/ (external redirect).
        # closing_date is checked as well as status: expire_closed_company_listings
        # runs on a schedule, so between runs a listing can be ACTIVE with its
        # deadline already past. Filtering here means the list is correct even
        # if that job has not run yet.
        return (
            JobListing.objects
            .filter(status='ACTIVE', source_type='COMPANY')
            .exclude(closing_date__lt=timezone.localdate())
            .select_related('category', 'company')
            .prefetch_related('job_skills__skill', 'applications')
        )


class StudentJobApplicationView(APIView):
    permission_classes = [IsStudent]

    def get(self, request):
        """
        GET /api/job-listings/applications/
        The logged-in student's own applications, newest first.

        Scoped to request.user's own profile — a student can only ever read
        their own rows, never another applicant's. The employer-facing
        JobApplicationSerializer is deliberately not reused here; see its
        counterpart in serializers.py for why.
        """
        student = get_object_or_404(Student, user=request.user)
        applications = (
            JobApplication.objects
            .filter(student=student)
            .select_related('job__company', 'job__category')
        )
        serializer = StudentApplicationSerializer(applications, many=True)
        return Response(serializer.data)

    def post(self, request):
        """
        POST /api/job-listings/applications/
        Student submits a job application.

        The disclosure acknowledgement is recorded here rather than collected
        as a separate checkbox. The sentence above the Submit button states
        that the application will be shared with the employer, and pressing
        Submit is the affirmative act -- an extra tick box in front of a button
        the student has already chosen to press adds friction without adding
        information.
        """
        student = get_object_or_404(Student, user=request.user)

        serializer = JobApplicationCreateSerializer(
            data=request.data,
            context={'request': request, 'student': student},
        )
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            # The application and the record of what the student was told
            # about it are created together. An application an employer can
            # read, with no record of the disclosure, is the state this must
            # never be left in -- and so is a disclosure record for an
            # application that failed to save.
            with transaction.atomic():
                disclosure = UserConsent.objects.create(
                    user=request.user,
                    consent_type=(
                        UserConsent.ConsentType
                        .APPLICATION_DISCLOSURE_ACKNOWLEDGEMENT),
                    notice_version=CURRENT_VERSION,
                    accepted=True,
                    accepted_at=timezone.now(),
                    source=UserConsent.Source.JOB_APPLICATION,
                )
                application = JobApplication.objects.create(
                    student=student,
                    job=data['job'],
                    applicant_snapshot=data['built_snapshot'],
                    needs_work_permit=data['needs_work_permit'],
                    available_from=data.get('available_from'),
                    phone=data.get('phone', ''),
                    cover_note=data.get('cover_note', ''),
                    # Which consented parse this application was assembled
                    # from, taken from the signed receipt rather than from a
                    # client-supplied id.
                    cv_processing_consent_id=serializer.cv_consent_id,
                    disclosure_consent=disclosure,
                )
        except IntegrityError:
            # Lost the race against a concurrent submission of the same
            # application. unique_together already rejected it; the student
            # should see the same message as the serializer's check, not a 500.
            return Response({'detail': 'You have already applied to this job.'},
                            status=status.HTTP_400_BAD_REQUEST)

        # The acknowledgement names no company, but the record identifies one:
        # disclosure_consent -> application -> job -> company. The audit trail
        # can answer "who received this student's data" without the interface
        # having to ask the student to read a company name off a checkbox.
        return Response(JobApplicationSerializer(application).data,
                        status=status.HTTP_201_CREATED)


class CVParseView(APIView):
    """
    POST /api/job-listings/cv/parse/
    Reads a CV and returns what it says. **Stores nothing.**

    The file is written to a private temporary path only because the PDF
    reader needs one, parsed, and deleted in a finally block. Nothing about
    it survives the request.

    This replaces an upload endpoint that saved CVs under the public
    MEDIA_ROOT and handed back a directly-reachable URL. A stored CV carries a
    phone number, an address, referees and often a photograph; keeping only
    the few fields the system actually uses avoids serving, protecting and
    deleting all of that.

    The response is a proposal, not a record. The student corrects it and the
    confirmed version is attached to an application.
    """
    permission_classes = [IsStudent]

    # PDF only. A .docx parser needs a dependency this project does not have,
    # and a Word file's ZIP signature is indistinguishable from any other
    # archive at validation time, so accepting one would mean accepting
    # anything zipped.
    ALLOWED_EXTENSIONS = {'.pdf': {'application/pdf'}}

    def post(self, request):
        upload = request.FILES.get('file')
        if not upload:
            return Response({'detail': 'No file provided.'},
                            status=status.HTTP_400_BAD_REQUEST)

        # Consent is checked before the file is read, not after. Reading first
        # and asking later would be the processing the acknowledgement exists
        # to authorise.
        if not drf_serializers.BooleanField().to_internal_value(
            request.data.get('cv_processing_ack', False)
        ):
            return Response(
                {'cv_processing_ack':
                    'Please agree to MomentumQuest reading this CV before uploading it.'},
                status=status.HTTP_400_BAD_REQUEST)

        # Size, extension and magic bytes, read from the file's own contents --
        # the same validator the certificate and transcript uploads use, so the
        # three cannot drift to different rules.
        try:
            validate_document(
                upload,
                allowed_extensions=self.ALLOWED_EXTENSIONS,
                max_bytes=MAX_UPLOAD_BYTES,
            )
        except InvalidUpload as exc:
            message = str(exc).replace('A certificate must be a PDF file.',
                                       'Your CV must be a PDF.')
            return Response({'detail': message}, status=status.HTTP_400_BAD_REQUEST)

        # Recorded before parsing, so the record exists even if reading the
        # file then fails: the CV was processed either way, and that is what
        # the consent accounts for.
        consent = UserConsent.objects.create(
            user=request.user,
            consent_type=UserConsent.ConsentType.CV_PROCESSING_CONSENT,
            notice_version=CURRENT_VERSION,
            accepted=True,
            accepted_at=timezone.now(),
            source=UserConsent.Source.CV_PARSE,
        )

        try:
            parsed = parse_cv(upload)
        except Exception:
            logger.exception('CV parsing failed')
            return Response(
                {'detail': 'We could not read that PDF. Please try exporting '
                           'your CV again.'},
                status=status.HTTP_400_BAD_REQUEST)

        if not parsed['readable']:
            return Response({'detail': parsed['detail']},
                            status=status.HTTP_400_BAD_REQUEST)

        # The receipt ties this consented parse to the application the student
        # is about to submit, without the client naming a consent row itself.
        # It attests that consented processing happened -- not that anything
        # the parser extracted is accurate or verified.
        parsed['cv_parse_receipt'] = cv_receipt.issue(request.user.id, consent.id)
        return Response(parsed, status=status.HTTP_200_OK)


class SkillExtractionView(APIView):
    """
    POST /api/job-listings/skills/extract/   {"text": "..."}

    Reads a draft job description and returns the skills it mentions, so a
    company can fill the required-skills list from what they have already
    written instead of retyping it.

    A suggestion, not a decision. The response is loaded into an editable list
    that the company then corrects, for one reason the extractor cannot solve:
    it recognises that a skill is wanted but never at what level, and the
    level is what candidates are scored against. Replacing the field outright
    would silently score every company listing at the Intermediate default.

    Uses the same extractor as the scraper, so a company listing and a scraped
    one are read by identical rules.
    """
    permission_classes = [IsCompany]

    #: Long enough that the extractor has something to work with, short enough
    #: that a paragraph still counts.
    MINIMUM_LENGTH = 40

    def post(self, request):
        text = str(request.data.get("text") or "").strip()
        if len(text) < self.MINIMUM_LENGTH:
            return Response(
                {"detail": "Write the job description first, then read the "
                           "skills from it."},
                status=status.HTTP_400_BAD_REQUEST)

        from scrape_jobs.skill_extractor import extract_skills_from_text

        skills = extract_skills_from_text(text)
        return Response({
            "skills": [
                {"skill_id": skill.id,
                 "skill_name": skill.skill_name,
                 "skill_category": skill.skill_category}
                for skill in sorted(skills, key=lambda s: s.skill_name)
            ],
        })
