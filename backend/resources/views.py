import logging
import os
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.files.storage import default_storage
from django.db import transaction
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import filters, generics, serializers, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.audit import record_privacy_event
from accounts.models import PrivacyAuditLog, UserConsent
from accounts.permissions import (
    IsAdminUserRole, IsCompany, IsStudent, is_platform_admin,
)
from accounts.privacy_notice import CURRENT_VERSION
from .file_validation import MAX_BYTES as MAX_UPLOAD_BYTES
from .pagination import ResourceCataloguePagination
from . import private_storage
from .file_validation import InvalidUpload, validate_document
from .models import (
    Certificate,
    CertificateSkillEvidence,
    TranscriptSkillEvidence,
    Course,
    LearningResource,
    TrainingProgramme,
    TranscriptUpload,
)
from .serializers import (
    CertificateAdminSerializer,
    CertificateEndorseSerializer,
    CertificateSerializer,
    CertificateUploadSerializer,
    CourseSerializer,
    CourseWriteSerializer,
    LearningResourceSerializer,
    TrainingProgrammeReviewSerializer,
    TrainingProgrammeSerializer,
    TranscriptUploadSerializer,
)
from .skill_evidence import recalculate_student_skills
from .skill_recognition import apply_skills, resolve_skills
from .transcript_classifier import classify_transcript
from .transcript_parser import extract_text_from_pdf, parse_transcript_text

logger = logging.getLogger(__name__)


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
    # 20,430 active rows serialised to 5.4MB in one response before this, and
    # the page then rendered every one of them. See resources.pagination for
    # why this is set per-view instead of globally.
    pagination_class   = ResourceCataloguePagination

    def list(self, request, *args, **kwargs):
        """One page, plus the platform names the filter tabs are built from.

        The tabs need every platform, which a single page cannot show -- and
        downloading the whole table to derive five strings is what this change
        exists to remove. One DISTINCT on an indexed column is the cheaper
        answer, and it is deliberately unfiltered so selecting a platform does
        not make the other tabs disappear.
        """
        response = super().list(request, *args, **kwargs)
        if isinstance(response.data, dict):
            response.data["platforms"] = sorted(
                LearningResource.objects
                .filter(is_active=True)
                # order_by("platform") is load-bearing: the model's default
                # ordering is ("platform", "title"), and an ORDER BY column
                # joins the SELECT, so DISTINCT would apply to the pair and
                # return one entry per course -- 20,430 strings, which is most
                # of a payload this change exists to shrink.
                .order_by("platform")
                .values_list("platform", flat=True)
                .distinct()
            )
        return response

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
    POST /api/resources/certificates/  — student uploads a certificate, either
         as a file (multipart ``file``) or as a credential URL.
    """

    def get_permissions(self):
        # Only a student can submit: POST reaches user.student_profile, which a
        # company account does not have. Companies are excluded from reading
        # too -- certificates are private documents and no company workflow
        # goes through this route.
        if self.request.method == "POST":
            return [IsStudent()]
        # DRF's | operator is defined on the permission metaclass, so it
        # composes classes, not instances.
        return [(IsStudent | IsAdminUserRole)()]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return CertificateUploadSerializer
        if is_platform_admin(self.request.user):
            return CertificateAdminSerializer
        return CertificateSerializer

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["uploaded_file"] = self.request.FILES.get("file")
        return context

    def get_queryset(self):
        if is_platform_admin(self.request.user):
            return (Certificate.objects
                    .select_related("student", "student__user", "admin",
                                    "upload_consent")
                    .prefetch_related("skill_evidence__skill")
                    .order_by("-uploaded_time"))
        return Certificate.objects.filter(
            student__user=self.request.user
        ).select_related("student").prefetch_related("skill_evidence__skill")


    @staticmethod
    def _refuse_if_withdrawn(user):
        """Withdrawal must actually stop future verification.

        The notice says withdrawing disables document-verification functions.
        Without this check it disabled nothing: the next upload simply wrote a
        fresh consent row and carried on, which would make the promise false.

        Keyed on ``withdrawn_at``, not on ``is_live``. Those are not the same
        question, and treating them as one locked every pre-notice account out
        of uploading permanently, while telling them they had withdrawn a
        consent they were never asked for:

          * a genuine withdrawal is ``accepted=True`` with ``withdrawn_at``
            set -- the student had the permission and took it back, so
            refusing is the whole point;
          * a BACKFILL_PRE_NOTICE row is ``accepted=False`` with no
            ``withdrawn_at`` -- the account simply predates the notice.
            Nothing was withdrawn because nothing was ever given, and the
            acknowledgement on this very upload is how it is given. Refusing
            here made that unreachable: the checkbox could never be read,
            because the request died before the serializer ran.

        Checked against the most recent row rather than any row, because
        consent is append-only -- a student who withdrew and later re-consented
        is consenting now.
        """
        latest = (
            UserConsent.objects
            .filter(user=user,
                    consent_type=UserConsent.ConsentType.DOCUMENT_VERIFICATION_CONSENT)
            .order_by("-created_at")
            .first()
        )
        # No row at all means an account that predates the consent table; the
        # per-upload acknowledgement below still applies to them.
        if latest is not None and latest.withdrawn_at is not None:
            raise ValidationError({
                "detail": (
                    "You have withdrawn consent for document verification. "
                    "Restore it in Settings to submit documents again."
                )
            })

    def create(self, request, *args, **kwargs):
        self._refuse_if_withdrawn(request.user)

        upload = request.FILES.get("file")
        if upload:
            try:
                # Validated from the file's own bytes, so a renamed executable
                # or a mislabelled image never reaches storage or, later, an
                # administrator's browser.
                self.upload_extension, self.upload_mime = validate_document(upload)
            except InvalidUpload as exc:
                return Response({"file": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        certificate = self.perform_create(serializer)

        record_privacy_event(
            PrivacyAuditLog.Action.CERTIFICATE_UPLOADED,
            actor=request.user,
            target=request.user,
            resource_id=certificate.pk,
            request=request,
        )

        return Response(
            CertificateSerializer(certificate).data,
            status=status.HTTP_201_CREATED,
        )

    def perform_create(self, serializer):
        upload = self.request.FILES.get("file")
        serializer.validated_data.pop("document_consent_ack", None)
        # Popped before save(): these are rows in another table, not fields on
        # Certificate.
        claimed_skills = serializer.validated_data.pop("skills", [])
        extra = {}
        # The stored (relative) path, kept so a failed save can remove the
        # bytes. Relative, not absolute: private_storage.delete resolves it
        # itself and refuses anything that does not sit under the private root.
        written_relative_path = None

        if upload:
            # Written outside MEDIA_ROOT for the same reason as transcripts:
            # config/urls.py serves MEDIA_ROOT with no authentication.
            directory = os.path.join(settings.PRIVATE_MEDIA_ROOT, "certificates")
            os.makedirs(directory, exist_ok=True)
            # A random name, never the student's: an uploaded file called
            # "040910101234_SPM.pdf" would otherwise put an identification
            # number on disk and into every path that touches it.
            relative_path = private_storage.build_relative_path(
                "certificates", f"cert_{uuid.uuid4().hex}{self.upload_extension}"
            )
            written_relative_path = relative_path
            with open(private_storage.resolve(relative_path), "wb") as destination:
                for chunk in upload.chunks():
                    destination.write(chunk)
            extra = {
                "file_path": relative_path,
                "original_name": upload.name[:255],
                "mime_type": self.upload_mime,
            }

        try:
            # The document and the consent that permitted it are written
            # together, so a stored document with no recorded consent is not a
            # reachable state.
            with transaction.atomic():
                consent = UserConsent.objects.create(
                    user=self.request.user,
                    consent_type=UserConsent.ConsentType.DOCUMENT_VERIFICATION_CONSENT,
                    notice_version=CURRENT_VERSION,
                    accepted=True,
                    accepted_at=timezone.now(),
                    source=UserConsent.Source.CERTIFICATE_UPLOAD,
                )
                certificate = serializer.save(
                    student=self.request.user.student_profile,
                    upload_consent=consent,
                    **extra,
                )
                # Inside the same transaction as the document: a certificate
                # with no claims is unreviewable, and one whose claims failed
                # to write would silently become one.
                CertificateSkillEvidence.objects.bulk_create([
                    CertificateSkillEvidence(
                        certificate=certificate,
                        skill=entry["skill"],
                        claimed_level=entry["claimed_level"],
                    )
                    for entry in claimed_skills
                ])
                return certificate
        except Exception:
            # A rollback undoes the rows but not the bytes already on disk.
            # An identity-bearing file with nothing pointing at it would never
            # be reached by the retention receiver, so it is removed here
            # rather than left to accumulate unnoticed.
            if written_relative_path:
                private_storage.delete(written_relative_path)
            raise


class CertificateDetailView(generics.RetrieveDestroyAPIView):
    """
    GET    /api/resources/certificates/<pk>/  — owner or admin
    DELETE /api/resources/certificates/<pk>/  — owner, while still PENDING

    Authorisation is decided here on the server for every method. The frontend
    hides buttons it should not offer, but that is presentation; this is the
    control.
    """
    permission_classes = [IsAuthenticated]
    queryset = Certificate.objects.select_related(
        "student", "student__user", "admin", "upload_consent"
    ).prefetch_related("skill_evidence__skill")

    def get_serializer_class(self):
        if is_platform_admin(self.request.user):
            return CertificateAdminSerializer
        return CertificateSerializer

    def get_object(self):
        certificate = get_object_or_404(self.get_queryset(), pk=self.kwargs["pk"])

        is_owner = certificate.student.user_id == self.request.user.id
        if not is_owner and not is_platform_admin(self.request.user):
            raise PermissionDenied("You may only open your own certificate.")

        return certificate

    def perform_destroy(self, instance):
        if instance.student.user_id != self.request.user.id:
            raise PermissionDenied("You may only delete your own certificate.")

        # An approved certificate is the evidence behind a skill the student
        # already holds. Removing it would leave the granted skill standing
        # with nothing supporting it, so deletion stops at PENDING.
        if instance.verified_status != Certificate.VerifiedStatus.PENDING:
            raise ValidationError(
                "A certificate that has already been reviewed cannot be deleted. "
                "Contact your administrator if the result is wrong."
            )

        certificate_id = instance.pk
        student = instance.student
        # Read before the delete: the evidence rows cascade with the document,
        # so afterwards there is nothing left to say which skills it covered.
        # Naming them explicitly is what lets the recalculation below drop a
        # skill this certificate was the last support for.
        covered = [row.skill for row in
                   instance.skill_evidence.select_related("skill")]

        # The post_delete receiver removes the stored file.
        instance.delete()

        # No-op for a pending certificate, which granted nothing -- and the
        # correct behaviour if the pending-only rule above is ever relaxed.
        recalculate_student_skills(student, skills=covered)

        record_privacy_event(
            PrivacyAuditLog.Action.CERTIFICATE_DELETED,
            actor=self.request.user,
            target=self.request.user,
            resource_id=certificate_id,
            request=self.request,
        )


class CertificateFileView(APIView):
    """
    GET /api/resources/certificates/<pk>/file/
    Streams an uploaded certificate back to its owner, or to an admin who has
    to look at it before endorsing.
    """
    permission_classes = [IsAuthenticated]

    CONTENT_TYPES = {
        ".pdf": "application/pdf",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
    }

    def get(self, request, pk):
        certificate = get_object_or_404(Certificate, pk=pk)

        is_owner = certificate.student.user_id == request.user.id
        if not is_owner and not is_platform_admin(request.user):
            raise PermissionDenied("You may only open your own certificate.")

        if not certificate.file_path:
            raise Http404("This certificate was submitted as a link, not a file.")

        absolute_path = private_storage.resolve(certificate.file_path)
        if absolute_path is None or not os.path.exists(absolute_path):
            raise Http404("Certificate file is missing from storage.")

        # An admin opening someone else's document is the moment worth
        # recording; a student opening their own is not an access event.
        if not is_owner:
            record_privacy_event(
                PrivacyAuditLog.Action.CERTIFICATE_VIEWED_BY_ADMIN,
                actor=request.user,
                target=certificate.student.user,
                resource_id=certificate.pk,
                request=request,
            )

        extension = os.path.splitext(certificate.file_path)[1].lower()
        response = FileResponse(
            open(absolute_path, "rb"),
            content_type=self.CONTENT_TYPES.get(extension, "application/octet-stream"),
            # The stored name, not the student's. original_name is for display
            # in the UI; putting it in Content-Disposition would write whatever
            # the student called the file into headers and download folders.
            filename=private_storage.stored_filename(certificate.file_path),
        )
        # The document is personal data on a possibly shared machine, and it
        # must never be indexed or cached by an intermediary.
        response["Cache-Control"] = "private, no-store, max-age=0"
        response["X-Robots-Tag"] = "noindex, nofollow"
        return response


class CertificateEndorseView(generics.UpdateAPIView):
    """
    PATCH /api/resources/certificates/<id>/endorse/
    Admin endorses or rejects a student certificate.

    Approving is what actually grants the skill. Until an admin approves, a
    certificate is only a claim; the transcript route writes StudentSkill
    directly because an examination result is its own proof, whereas an
    external course certificate needs a human to vouch for it first.

    The decision is per skill as well as per document. An administrator may
    approve every claim, approve only the ones the certificate genuinely
    supports, lower an exaggerated claimed level, or reject the document
    outright -- so an approved certificate can legitimately carry both
    approved and rejected claims.

    Rejecting a previously approved certificate does NOT revoke the skill it
    granted. Silently changing a student's standing on a re-review needs a
    defined project policy, and there is none; the record of the reversal is
    kept in the audit log for a human to act on.
    """
    queryset           = Certificate.objects.all()
    serializer_class   = CertificateEndorseSerializer
    permission_classes = [IsAdminUserRole]

    def perform_update(self, serializer):
        approved = serializer.validated_data.pop("skills", [])

        decided_at = timezone.now()
        approved_by_skill = {entry["skill"].id: entry for entry in approved}
        touched = []

        # The verdict on the document and the skills it grants commit together
        # or not at all. serializer.save() used to run before this block, so a
        # failure while applying the evidence left the certificate APPROVED
        # with none of its skills granted -- and nothing reconciles that later,
        # because the certificate already looks decided.
        with transaction.atomic():
            # Who decided, and when, is stamped here rather than accepted from
            # the request body, so it cannot be supplied by the client.
            certificate = serializer.save(
                admin=self.request.user.admin_profile,
                verified_at=timezone.now(),
            )

            for evidence in certificate.skill_evidence.select_related("skill"):
                decision = approved_by_skill.get(evidence.skill_id)
                if (decision is not None
                        and certificate.verified_status ==
                        Certificate.VerifiedStatus.APPROVED):
                    evidence.review_status = (
                        CertificateSkillEvidence.ReviewStatus.APPROVED)
                    evidence.approved_level = decision["approved_level"]
                    evidence.review_note = decision.get("review_note", "")
                else:
                    # A claim the administrator did not approve is refused,
                    # including every claim on a rejected document. Leaving it
                    # PENDING would keep it in the queue forever with the
                    # document already decided.
                    evidence.review_status = (
                        CertificateSkillEvidence.ReviewStatus.REJECTED)
                    evidence.approved_level = ""
                evidence.reviewed_at = decided_at
                evidence.save(update_fields=["review_status", "approved_level",
                                             "review_note", "reviewed_at"])
                touched.append(evidence.skill)

            # Authoritative, not an upgrade-only apply: the student's level for
            # each touched skill is re-derived from every piece of live
            # evidence they hold. That is what makes an approval at BEGINNER
            # unable to pull down an existing ADVANCED, and what makes a
            # withdrawal actually take a level away.
            recalculate_student_skills(certificate.student, skills=touched)

        if certificate.verified_status == Certificate.VerifiedStatus.APPROVED:
            action = PrivacyAuditLog.Action.CERTIFICATE_VERIFIED
        else:
            action = PrivacyAuditLog.Action.CERTIFICATE_REJECTED

        record_privacy_event(
            action,
            actor=self.request.user,
            target=certificate.student.user,
            resource_id=certificate.pk,
            request=self.request,
        )

    def update(self, request, *args, **kwargs):
        super().update(request, *args, **kwargs)
        # Respond with the admin view so the queue can re-render the decided
        # row without a second request.
        certificate = self.get_object()
        return Response(CertificateAdminSerializer(certificate).data)


class TranscriptListCreateView(APIView):
    """
    GET  /api/resources/skill-validation/transcripts/
         Student lists their own uploaded transcripts.
    POST /api/resources/skill-validation/transcripts/
         Student uploads a transcript PDF. It is parsed, mapped to skills and
         written straight to StudentSkill — no admin endorsement, because the
         examination result is itself the proof.
    """
    permission_classes = [IsStudent]

    # A transcript is an examination result and is the document most likely to
    # display an NRIC, so it is held to the same rules as a certificate:
    # acknowledged before upload, validated from its own bytes, and logged.
    ALLOWED_EXTENSIONS = {".pdf": {"application/pdf"}}
    # The ceiling itself lives in file_validation so certificates and
    # transcripts cannot drift to different limits.
    MAX_BYTES = MAX_UPLOAD_BYTES

    def get(self, request):
        transcripts = TranscriptUpload.objects.filter(student=request.user.student_profile)
        return Response(TranscriptUploadSerializer(transcripts, many=True).data)

    @staticmethod
    def _refuse(transcript, message):
        """Discard a rejected upload entirely and return only the reason.

        A document that is not this student's transcript is not a record worth
        keeping. There is no administrator to escalate it to, nothing was
        extracted from it, and the file is already gone -- so the row would be
        a filename and an error message sitting in the student's list looking
        like a submission they have to deal with.

        The UserConsent row it was created under is deliberately left standing.
        Consent is append-only evidence: the student did agree, and the
        document was processed under that agreement. Deleting the record of a
        permission that was genuinely exercised would be rewriting history to
        look tidier.
        """
        transcript.delete()
        return Response({"detail": message},
                        status=status.HTTP_400_BAD_REQUEST)

    def post(self, request):
        upload = request.FILES.get("file")
        if not upload:
            return Response({"detail": "No file provided."},
                            status=status.HTTP_400_BAD_REQUEST)

        if not serializers.BooleanField().to_internal_value(
            request.data.get("document_consent_ack", False)
        ):
            return Response(
                {"document_consent_ack":
                    "You must acknowledge the Certificate Verification Notice before "
                    "uploading a document."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            validate_document(
                upload,
                allowed_extensions=self.ALLOWED_EXTENSIONS,
                max_bytes=self.MAX_BYTES,
            )
        except InvalidUpload as exc:
            # validate_document phrases its messages for certificates; a
            # transcript accepts only PDF, so say that plainly.
            message = str(exc).replace("A certificate must be a PDF file.",
                                       "Transcript must be a PDF.")
            return Response({"detail": message}, status=status.HTTP_400_BAD_REQUEST)

        CertificateListCreateView._refuse_if_withdrawn(request.user)

        student = request.user.student_profile

        # Stored under PRIVATE_MEDIA_ROOT, never MEDIA_ROOT — the file carries
        # the student's NRIC and must not be publicly served.
        directory = os.path.join(settings.PRIVATE_MEDIA_ROOT, "transcripts")
        os.makedirs(directory, exist_ok=True)

        relative_path = private_storage.build_relative_path(
            "transcripts", f"{uuid.uuid4().hex}.pdf"
        )
        absolute_path = private_storage.resolve(relative_path)

        # The file and the two rows that account for it are created together.
        # If any step fails the file is removed, so no stored document can
        # exist without the consent that permitted it.
        try:
            with open(absolute_path, "wb") as destination:
                for chunk in upload.chunks():
                    destination.write(chunk)

            with transaction.atomic():
                consent = UserConsent.objects.create(
                    user=request.user,
                    consent_type=UserConsent.ConsentType.DOCUMENT_VERIFICATION_CONSENT,
                    notice_version=CURRENT_VERSION,
                    accepted=True,
                    accepted_at=timezone.now(),
                    source=UserConsent.Source.TRANSCRIPT_UPLOAD,
                )
                transcript = TranscriptUpload.objects.create(
                    student=student,
                    file_path=relative_path,
                    original_name=upload.name[:255],
                    upload_consent=consent,
                )
        except Exception:
            private_storage.delete(relative_path)
            logger.exception("Transcript upload failed for student %s", student.pk)
            return Response(
                {"detail": "Your transcript could not be saved. Please try again."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        record_privacy_event(
            PrivacyAuditLog.Action.TRANSCRIPT_UPLOADED,
            actor=request.user,
            target=request.user,
            resource_id=transcript.pk,
            resource_type=PrivacyAuditLog.ResourceType.TRANSCRIPT,
            request=request,
        )

        # The file exists only long enough to be read.
        #
        # Read first, delete second, branch third -- in that order and before
        # any early return, so there is exactly one place the document is
        # discarded and no error path can leave it behind. Everything below
        # works from ``text``; nothing reopens the PDF, because by then there
        # is no PDF.
        read_error = None
        try:
            text = extract_text_from_pdf(absolute_path)
        except Exception as exc:  # malformed or unreadable PDF
            text, read_error = "", exc

        private_storage.delete(relative_path)
        transcript.file_path = ""

        if read_error is not None:
            logger.info("Unreadable transcript PDF from student %s: %s",
                        student.pk, read_error)
            return self._refuse(
                transcript,
                "This PDF could not be read. Please upload the official "
                "digital transcript issued by your university.")

        try:
            subjects, warnings = parse_transcript_text(text)
        except Exception as exc:
            logger.info("Unparseable transcript from student %s: %s",
                        student.pk, exc)
            return self._refuse(
                transcript,
                "The subjects and grades in this PDF could not be read. "
                "Please upload the official transcript issued by your "
                "university.")

        if not text or not text.strip():
            # No text layer at all: almost always a scan or a photograph.
            # There is no OCR, so say so rather than guessing.
            return self._refuse(
                transcript,
                "This PDF contains no readable text, so it is most likely a "
                "scan or a photograph. Scanned transcripts are not supported "
                "yet — please upload the official digital PDF issued by your "
                "university.")

        classification = classify_transcript(text, student, subjects)
        transcript.parsed_subjects = subjects
        transcript.document_type_status = classification.document_type
        transcript.classification_score = classification.score
        transcript.classification_reasons = classification.reasons
        transcript.detected_institution = classification.institution
        transcript.student_identity_matched = classification.identity_matched
        transcript.error_message = "\n".join(warnings)

        # A document that is not a transcript, or is somebody else's, is
        # refused and discarded.
        #
        # The two reasons are tested in that order deliberately. A holiday
        # booking is not a transcript *and* carries no matching matric number,
        # and telling the student "the identity on this document does not
        # match your account" would accuse them of using someone else's
        # results when they had simply picked the wrong file. Identity is only
        # mentioned when the document really is a transcript.
        if (classification.identity_matched is False
                and classification.looks_like_transcript):
            # A real transcript, just not theirs. Identity is the honest
            # reason and the only one that helps them.
            return self._refuse(
                transcript,
                "The name or matric number on this transcript does not match "
                "your account.")

        if classification.document_type == "NOT_TRANSCRIPT":
            return self._refuse(
                transcript,
                "This document was not recognised as an academic transcript. "
                "Please upload the official transcript issued by your "
                "university.")

        transcript.status = TranscriptUpload.Status.PARSED

        # Skills are written now, on the strength of the automatic gates
        # alone: the document parsed, it classified as a transcript, and its
        # matric number matches this student.
        #
        # There is no administrator step. That is a deliberate project
        # decision and it has a consequence worth naming: a forgery with
        # consistent arithmetic and the student's own matric number passes
        # every gate that remains, and nobody looks at the document
        # afterwards -- it no longer exists to look at. The classification
        # score and reasons are kept so the basis of the decision is still on
        # record even though the evidence is not.
        transcript.verification_status = (
            TranscriptUpload.VerificationStatus.AUTO_VERIFIED)
        transcript.verification_method = (
            TranscriptUpload.VerificationMethod.CLASSIFICATION)
        transcript.reviewed_at = timezone.now()

        skill_levels = resolve_skills(subjects)
        added, _upgraded = apply_skills(student, skill_levels)
        for skill, level in skill_levels.items():
            TranscriptSkillEvidence.objects.update_or_create(
                transcript=transcript, skill=skill,
                defaults={"skill_level": level},
            )
        transcript.skills_added = added
        transcript.skills_applied_at = timezone.now()
        transcript.parsed_subjects = subjects
        transcript.save()

        # Authoritative pass: each touched skill settles at the highest level
        # all the student's live evidence supports.
        if skill_levels:
            recalculate_student_skills(student, skills=list(skill_levels))

        payload = TranscriptUploadSerializer(transcript).data
        payload["subjects_found"] = len(subjects)
        payload["skills_added"] = added
        payload["detail"] = (
            f"{len(subjects)} subject(s) were read and {added} skill(s) added "
            "to your profile. The PDF has been deleted -- only the subjects, "
            "grades and skills are kept."
        )
        return Response(payload, status=status.HTTP_201_CREATED)


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

    A poster or brochure is public: it is written into MEDIA_ROOT, which is
    served without authentication. That makes the file type the whole of the
    security boundary -- an .html or .svg accepted here would be served from
    the application's own origin and could run script against anyone who
    opened it. The extension is therefore never taken from the client's
    filename; the type is read from the file's own bytes and the stored name
    is generated.
    """
    permission_classes = [IsCompany]

    def post(self, request):
        file = request.FILES.get('file')
        if not file:
            return Response({'detail': 'No file provided.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            extension, _ = validate_document(file)
        except InvalidUpload as exc:
            message = str(exc).replace("A certificate must be",
                                       "A supporting document must be")
            return Response({'detail': message}, status=status.HTTP_400_BAD_REQUEST)

        name = f"training/{uuid.uuid4().hex}{extension}"
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
