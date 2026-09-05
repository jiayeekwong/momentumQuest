from django.contrib import admin

from .models import (
    Certificate,
    CertificateSkillEvidence,
    Course,
    LearningResource,
    ResourceScrapeLog,
    SubjectSkillMapping,
    TrainingProgramme,
    TranscriptSkillEvidence,
    TranscriptUpload,
)


@admin.register(SubjectSkillMapping)
class SubjectSkillMappingAdmin(admin.ModelAdmin):
    list_display  = ("subject_code", "subject_name", "skill", "is_active")
    search_fields = ("subject_code", "subject_name", "skill__skill_name")
    list_filter   = ("is_active", "skill__skill_category")


@admin.register(TranscriptUpload)
class TranscriptUploadAdmin(admin.ModelAdmin):
    """A record of a transcript that was read. Nothing here is decidable.

    Transcripts are processed automatically: the upload reads the subjects,
    applies the skills and deletes the PDF before it responds. There is no
    administrator step, and there is no document left to review even if there
    were -- so the Approve and Reject actions that used to live here are gone
    rather than left as buttons that would contradict the pipeline.

    Everything is read-only for the same reason it always was: typing
    MANUALLY_VERIFIED into the form would flip the status without applying
    skills, without writing TranscriptSkillEvidence and without an audit
    entry -- a transcript claiming to be verified that granted nothing.
    """
    list_display  = ("student", "original_name", "document_type_status",
                     "classification_score", "verification_status",
                     "skills_added", "uploaded_time")
    search_fields = ("student__student_name", "original_name",
                     "detected_institution")
    list_filter   = ("verification_status", "document_type_status", "status")

    readonly_fields = (
        "student", "uploaded_time", "parsed_subjects", "skills_added",
        "file_path", "original_name", "error_message", "upload_consent",
        "status", "document_type_status", "classification_score",
        "classification_reasons", "detected_institution",
        "student_identity_matched", "verification_status",
        "verification_method", "reviewed_by", "reviewed_at",
        "rejection_reason", "skills_applied_at",
    )

    def has_add_permission(self, request):
        # A transcript exists because a student uploaded a file. One created
        # here would have no subjects behind it and no consent record.
        return False


@admin.register(TranscriptSkillEvidence)
class TranscriptSkillEvidenceAdmin(admin.ModelAdmin):
    """Which transcript granted which skill. Read-only: it is a record."""
    list_display  = ("transcript", "skill", "skill_level", "applied_at")
    search_fields = ("transcript__student__student_name", "skill__skill_name")
    list_filter   = ("skill_level",)
    readonly_fields = ("transcript", "skill", "skill_level", "applied_at")

    def has_add_permission(self, request):
        return False


@admin.register(LearningResource)
class LearningResourceAdmin(admin.ModelAdmin):
    list_display  = ("title", "platform", "type", "skill", "is_active", "scraped_at")
    search_fields = ("title", "platform", "url")
    list_filter   = ("platform", "type", "is_active", "skill__skill_category")
    readonly_fields = ("scraped_at",)


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display  = ("title", "skill", "department", "admin", "updated_at")
    search_fields = ("title", "department")
    list_filter   = ("department", "skill__skill_category")
    readonly_fields = ("updated_at",)


class CertificateSkillEvidenceInline(admin.TabularInline):
    """The claims on one certificate. Shown, never edited.

    Approving a claim here would set review_status and approved_level and
    stop there: no StudentSkill written, the highest-evidence rule not
    applied, skill gaps not refreshed, and no audit row naming who decided.
    The endorsement endpoint does all four, so it is the only way in.
    """
    model = CertificateSkillEvidence
    extra = 0
    fields = ("skill", "claimed_level", "approved_level", "review_status",
              "review_note", "reviewed_at")
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Certificate)
class CertificateAdmin(admin.ModelAdmin):
    list_display  = ("student", "claimed_skills", "source", "verified_status",
                     "uploaded_time", "verified_at", "admin")
    search_fields = ("student__student_name", "certificate_name",
                     "skill_evidence__skill__skill_name", "source")
    list_filter   = ("verified_status", "certificate_type", "rejection_reason",
                     "skill_evidence__review_status")
    inlines       = (CertificateSkillEvidenceInline,)
    # Read-only throughout, not merely for the pipeline-written fields.
    #
    # verified_status was editable here, so an administrator could set a
    # certificate to APPROVED from this form. That writes the status and
    # nothing else: no StudentSkill, no highest-evidence recalculation, no
    # skill-gap refresh, no PrivacyAuditLog row. The certificate would read
    # "approved" on the student's profile while granting them nothing, and
    # there would be no record of who approved it.
    #
    # POST /api/resources/certificates/<pk>/endorse/ does all of that as one
    # transaction, so it is the only path to a decision. This page stays for
    # looking things up.
    readonly_fields = ("student", "certificate_name", "certificate_type",
                       "source", "cert_url", "uploaded_time", "file_path",
                       "original_name", "mime_type", "verified_status",
                       "verified_at", "admin", "rejection_reason",
                       "verification_notes", "upload_consent")

    def has_add_permission(self, request):
        # A certificate exists because a student uploaded one, under a consent
        # record. One created here would have neither.
        return False

    def has_change_permission(self, request, obj=None):
        # Django still renders the form when every field is read-only; saying
        # so explicitly is what removes the Save buttons.
        return False

    @admin.display(description="Skills claimed")
    def claimed_skills(self, obj):
        # One document, several claims -- listing the document once with its
        # skills beside it is the whole point of the evidence table.
        return ", ".join(
            row.skill.skill_name for row in obj.skill_evidence.all()) or "—"


@admin.register(TrainingProgramme)
class TrainingProgrammeAdmin(admin.ModelAdmin):
    list_display  = ("title", "company", "skill", "approval_status", "submission_time")
    search_fields = ("title", "company__company_name")
    list_filter   = ("approval_status",)
    readonly_fields = ("submission_time",)


@admin.register(ResourceScrapeLog)
class ResourceScrapeLogAdmin(admin.ModelAdmin):
    list_display   = ("started_at", "status", "platforms_scraped", "resources_created",
                      "resources_updated", "resources_deactivated", "finished_at")
    list_filter    = ("status",)
    readonly_fields = ("started_at", "finished_at", "platforms_scraped", "resources_scraped",
                       "resources_created", "resources_updated", "resources_deactivated",
                       "error_message")
