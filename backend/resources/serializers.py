import json

from rest_framework import serializers

from accounts.departments import COURSE_DEPARTMENTS, validate_department
from accounts.models import StudentSkill
from scrape_jobs.models import Skill
from .models import (
    Certificate,
    CertificateSkillEvidence,
    Course,
    LearningResource,
    TrainingProgramme,
    TranscriptUpload,
)


class LearningResourceSerializer(serializers.ModelSerializer):
    skill = serializers.StringRelatedField()

    class Meta:
        model  = LearningResource
        fields = ["id", "skill", "title", "platform", "url", "type", "is_active", "scraped_at"]


def resolve_or_quarantine_skill(skill_name):
    """An existing catalogue skill by name, or a new one held for review.

    A name typed into a course or training-programme form used to land as a
    fully active, ACTIVE_INTERNAL skill -- indistinguishable from a curated
    one. That put a company's typo or vague phrase into the global vocabulary,
    where the extractor then matched it against every scraped advert.

    The same quarantine the employer job form uses: the course or programme
    still links to the skill, because those read the FK directly, but it
    cannot join the extractor's term list or any picker until a reviewer
    promotes it.
    """
    name = (skill_name or "").strip()
    if not name:
        return None
    skill = Skill.objects.filter(skill_name__iexact=name).first()
    if skill is None:
        skill = Skill.objects.create(
            skill_name=name,
            is_active=False,
            catalogue_status=Skill.CatalogueStatus.REVIEW_REQUIRED,
        )
    return skill


class CourseSerializer(serializers.ModelSerializer):
    skill = serializers.StringRelatedField()
    admin = serializers.StringRelatedField()

    class Meta:
        model  = Course
        fields = ["id", "admin", "skill", "title", "course_url", "department", "updated_at"]


class CourseWriteSerializer(serializers.ModelSerializer):
    skill_name = serializers.CharField(write_only=True, required=True)

    class Meta:
        model  = Course
        fields = ["id", "title", "department", "course_url", "skill_name", "updated_at"]
        read_only_fields = ["id", "updated_at"]

    def validate_department(self, value):
        # A course may also be "Compulsory", which is not something a student
        # can belong to -- hence the wider list.
        validate_department(value, allowed=COURSE_DEPARTMENTS)
        return value

    def create(self, validated_data):
        skill = resolve_or_quarantine_skill(
            validated_data.pop("skill_name", ""))
        return Course.objects.create(skill=skill, **validated_data)

    def update(self, instance, validated_data):
        skill = resolve_or_quarantine_skill(
            validated_data.pop("skill_name", ""))
        if skill is not None:
            instance.skill = skill
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance


class CertificateSkillEvidenceSerializer(serializers.ModelSerializer):
    """One skill claim on a certificate, as read back."""

    skill      = serializers.CharField(source="skill.skill_name", read_only=True)
    skill_id   = serializers.IntegerField(read_only=True)
    # What the student actually has for this skill after review -- the level
    # the administrator certified, or nothing while it is still pending.
    granted_level = serializers.SerializerMethodField()

    class Meta:
        model  = CertificateSkillEvidence
        fields = ["id", "skill", "skill_id", "claimed_level", "approved_level",
                  "granted_level", "review_status", "review_note", "reviewed_at"]

    def get_granted_level(self, obj):
        return obj.approved_level if obj.is_live else None


class ClaimedSkillSerializer(serializers.Serializer):
    """One entry in the ``skills`` list a student submits with a certificate."""

    # selectable(), not all(): the picker endpoint already hid retired and
    # unreviewed skills, but this accepted any primary key, so the rule held
    # only for callers who used the form.
    skill_id      = serializers.PrimaryKeyRelatedField(
        queryset=Skill.objects.selectable(), source="skill")
    claimed_level = serializers.ChoiceField(
        choices=StudentSkill.SkillLevel.choices,
        default=StudentSkill.SkillLevel.INTERMEDIATE)


class ApprovedSkillSerializer(serializers.Serializer):
    """One entry in the ``skills`` list an administrator returns."""

    skill_id       = serializers.PrimaryKeyRelatedField(
        queryset=Skill.objects.selectable(), source="skill")
    approved_level = serializers.ChoiceField(
        choices=StudentSkill.SkillLevel.choices)
    review_note    = serializers.CharField(required=False, allow_blank=True,
                                           max_length=255)


class CertificateSerializer(serializers.ModelSerializer):
    """What a student may see about their own certificate.

    ``verification_notes`` is absent by design -- an admin's internal note
    about a submission is not written for the submitter to read. The student
    gets ``rejection_message`` instead, which explains the outcome in plain
    language.
    """
    skill_evidence = CertificateSkillEvidenceSerializer(many=True, read_only=True)
    student      = serializers.StringRelatedField()
    student_name = serializers.SerializerMethodField()
    has_file     = serializers.BooleanField(read_only=True)
    rejection_message = serializers.CharField(read_only=True)

    class Meta:
        model  = Certificate
        fields = [
            "id", "student", "student_name", "skill_evidence", "cert_url",
            "source", "certificate_type", "certificate_name", "original_name",
            "has_file", "uploaded_time", "verified_status", "verified_at",
            "rejection_reason", "rejection_message",
        ]

    def get_student_name(self, obj):
        return obj.student.student_name if obj.student else None


class CertificateAdminSerializer(CertificateSerializer):
    """The verification view, for authorised administrators only.

    Adds the context an admin needs to decide -- who submitted it, and their
    matric number so the right student's record is being reviewed -- plus the
    internal notes. Never reachable from a student or company route.

    There is deliberately no identity-number field to show: MomentumQuest
    stores none, so the name on the document is compared against the
    registered name and nothing else.
    """
    student_email  = serializers.EmailField(source="student.user.email", read_only=True)
    matric_number  = serializers.CharField(source="student.matric_number", read_only=True)
    department     = serializers.CharField(source="student.department", read_only=True)
    reviewed_by    = serializers.SerializerMethodField()
    consent_recorded_at = serializers.DateTimeField(
        source="upload_consent.accepted_at", read_only=True, default=None,
    )

    class Meta(CertificateSerializer.Meta):
        fields = CertificateSerializer.Meta.fields + [
            "student_email", "matric_number", "department", "mime_type",
            "verification_notes", "reviewed_by", "consent_recorded_at",
        ]

    def get_reviewed_by(self, obj):
        return obj.admin.admin_name if obj.admin else None


class CertificateUploadSerializer(serializers.ModelSerializer):
    """Validates the metadata a student submits with a certificate.

    The uploaded file itself is handled by the view, not here: it is written
    to PRIVATE_MEDIA_ROOT rather than to a model FileField, matching how
    TranscriptUpload stores its PDF.
    """

    # Spec D: the student acknowledges, per upload, that the document may
    # contain identity information which an administrator will read. Required
    # on every submission rather than inherited from the signup consent,
    # because consent to *this* document being processed is the point.
    document_consent_ack = serializers.BooleanField(write_only=True)

    # The skills this document is offered as proof of. A list, because one
    # certificate routinely evidences several -- a data analytics programme is
    # proof of Python, SQL and data visualisation at once -- and requiring one
    # upload per skill made students store the same file repeatedly.
    skills = ClaimedSkillSerializer(many=True, write_only=True)

    class Meta:
        model  = Certificate
        fields = ["cert_url", "source", "certificate_type",
                  "certificate_name", "document_consent_ack", "skills"]

    def to_internal_value(self, data):
        """Accept ``skills`` as a JSON string as well as a list.

        The upload is multipart, because it carries a file, and multipart has
        no representation for a list of objects. Rather than invent a
        ``skills[0][skill_id]`` convention, the client sends one JSON string
        and it is parsed here; a JSON request body keeps working unchanged.
        """
        raw = data.get("skills") if hasattr(data, "get") else None
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
            except ValueError:
                raise serializers.ValidationError({
                    "skills": ["Send the claimed skills as a JSON list, "
                               "e.g. [{\"skill_id\": 12, "
                               "\"claimed_level\": \"INTERMEDIATE\"}]."]
                })
            # A plain dict, not a QueryDict copy: DRF treats a QueryDict as
            # HTML form input and would try to read the nested list back with
            # bracket-notation keys that multipart never sent.
            data = {key: data.get(key) for key in data}
            data["skills"] = parsed
        return super().to_internal_value(data)

    def validate_skills(self, value):
        if not value:
            raise serializers.ValidationError(
                "Select at least one skill this certificate is proof of."
            )
        if len(value) > CertificateSkillEvidence.MAX_SKILLS_PER_CERTIFICATE:
            raise serializers.ValidationError(
                f"A certificate may claim at most "
                f"{CertificateSkillEvidence.MAX_SKILLS_PER_CERTIFICATE} skills."
            )
        # Rejected rather than silently collapsed: two entries for one skill at
        # two levels is a client that does not know what it is claiming, and
        # quietly keeping the higher one would grant the student a level they
        # may not have meant to ask for.
        seen = set()
        for entry in value:
            skill = entry["skill"]
            if skill.id in seen:
                raise serializers.ValidationError(
                    f"'{skill.skill_name}' is listed more than once."
                )
            seen.add(skill.id)
        return value

    def validate_document_consent_ack(self, value):
        if not value:
            raise serializers.ValidationError(
                "You must acknowledge the Certificate Verification Notice before "
                "uploading a document."
            )
        return value

    def validate(self, attrs):
        # Proof is the whole point of the record, so a certificate with
        # neither a link nor a file is rejected rather than stored as an
        # unendorsable placeholder.
        has_file = bool(self.context.get("uploaded_file"))
        if not attrs.get("cert_url") and not has_file:
            raise serializers.ValidationError(
                "Attach the certificate file or paste its credential URL."
            )
        return attrs


class CertificateEndorseSerializer(serializers.ModelSerializer):
    """An administrator's verification decision.

    Only the decision fields are writable. verified_at and the reviewing admin
    are stamped by the view, not accepted from the request, so the record of
    who decided and when cannot be forged by the client.
    """

    # The per-skill decisions. Omitting a claimed skill rejects it: an
    # administrator approving two of three claims should not have to spell out
    # the refusal, and defaulting the other way would approve claims nobody
    # looked at.
    skills = ApprovedSkillSerializer(many=True, write_only=True, required=False)

    class Meta:
        model  = Certificate
        fields = ["id", "verified_status", "rejection_reason",
                  "verification_notes", "skills"]

    def validate_skills(self, value):
        seen = set()
        for entry in value:
            skill = entry["skill"]
            if skill.id in seen:
                raise serializers.ValidationError(
                    f"'{skill.skill_name}' is listed more than once."
                )
            seen.add(skill.id)
        return value

    def validate_verified_status(self, value):
        allowed = {
            Certificate.VerifiedStatus.APPROVED,
            Certificate.VerifiedStatus.REJECTED,
        }
        if value not in allowed:
            raise serializers.ValidationError(
                "verified_status must be either 'APPROVED' or 'REJECTED'."
            )
        return value

    def validate(self, attrs):
        # PATCH makes every field optional, so a request could otherwise arrive
        # with only notes -- which used to be accepted, stamping verified_at on
        # a still-PENDING certificate and writing a CERTIFICATE_REJECTED audit
        # row for a rejection that never happened. This endpoint records a
        # decision; a request that states no decision is not one.
        if "verified_status" not in attrs:
            raise serializers.ValidationError({
                "verified_status": ["State the decision: 'APPROVED' or 'REJECTED'."]
            })

        status_value = attrs["verified_status"]
        reason = attrs.get("rejection_reason", "")

        # A rejection the student cannot act on is worse than no rejection, and
        # the reason is what generates their explanation.
        if status_value == Certificate.VerifiedStatus.REJECTED and not reason:
            raise serializers.ValidationError({
                "rejection_reason": ["Select a reason when rejecting a submission."]
            })

        if status_value == Certificate.VerifiedStatus.APPROVED and reason:
            raise serializers.ValidationError({
                "rejection_reason": ["An approved submission cannot carry a rejection reason."]
            })

        # Only a pending submission can be decided.
        #
        # Approving grants a skill; rejecting an already-approved certificate
        # did not take it back, so the certificate read REJECTED while the
        # skill it produced stayed on the student's profile and kept being
        # reported to employers. Revoking a granted skill needs a defined
        # policy -- what happens to applications already sent citing it, in
        # particular -- and there is none, so the reversal is refused rather
        # than half-performed.
        instance = self.instance
        if instance is not None and instance.verified_status != Certificate.VerifiedStatus.PENDING:
            raise serializers.ValidationError({
                "verified_status": [
                    f"This submission was already {instance.get_verified_status_display().lower()}. "
                    "A decision cannot be changed here."
                ]
            })

        # Every approved skill must be one the student actually claimed. An
        # administrator granting a skill the document was never submitted for
        # would be creating evidence rather than reviewing it.
        approved = attrs.get("skills") or []
        if approved and instance is not None:
            claimed = set(
                instance.skill_evidence.values_list("skill_id", flat=True))
            unexpected = [entry["skill"].skill_name for entry in approved
                          if entry["skill"].id not in claimed]
            if unexpected:
                raise serializers.ValidationError({
                    "skills": [
                        "This certificate was not submitted as proof of: "
                        + ", ".join(sorted(unexpected))
                    ]
                })

        # Approving the document while approving none of its claims records a
        # verified certificate that grants nothing, which is a rejection
        # written in the wrong field.
        if (status_value == Certificate.VerifiedStatus.APPROVED
                and instance is not None and not approved):
            raise serializers.ValidationError({
                "skills": [
                    "Approve at least one claimed skill, or reject the "
                    "submission."
                ]
            })

        return attrs


class TranscriptUploadSerializer(serializers.ModelSerializer):
    """
    Read serializer for a student's own transcripts.

    file_path is deliberately excluded — the PDF is reachable only through
    TranscriptFileView, which checks ownership.
    """
    class Meta:
        model  = TranscriptUpload
        fields = [
            "id", "original_name", "uploaded_time", "status",
            "parsed_subjects", "skills_added", "error_message",
            # Verification is a separate state from parsing, and the student
            # needs to see it: "parsed" must never read as "skills added".
            "document_type_status", "verification_status",
            "detected_institution", "rejection_reason", "skills_applied_at",
        ]


class TrainingProgrammeSerializer(serializers.ModelSerializer):
    skill_name   = serializers.CharField(write_only=True, required=False, allow_blank=True)
    skill        = serializers.StringRelatedField(read_only=True)
    company      = serializers.StringRelatedField(read_only=True)
    company_name = serializers.SerializerMethodField()

    class Meta:
        model  = TrainingProgramme
        fields = [
            "id", "company", "company_name", "skill", "skill_name",
            "title", "description", "programme_duration", "supporting_doc",
            "approval_status", "submission_time",
        ]
        read_only_fields = ["id", "company", "skill", "approval_status", "submission_time"]

    def get_company_name(self, obj):
        return obj.company.company_name if obj.company else None

    def create(self, validated_data):
        skill = resolve_or_quarantine_skill(
            validated_data.pop("skill_name", ""))
        return TrainingProgramme.objects.create(skill=skill, **validated_data)


class TrainingProgrammeReviewSerializer(serializers.ModelSerializer):
    """
    Admin review serializer — only `approval_status` is writable.
    The title/company/skill fields are exposed read-only so the admin UI
    can render context without a second request.
    """
    company = serializers.StringRelatedField(read_only=True)
    skill   = serializers.StringRelatedField(read_only=True)

    class Meta:
        model  = TrainingProgramme
        fields = ["id", "title", "company", "skill", "approval_status"]
        read_only_fields = ["id", "title"]

    def validate_approval_status(self, value):
        allowed = {
            TrainingProgramme.ApprovalStatus.APPROVED,
            TrainingProgramme.ApprovalStatus.REJECTED,
        }
        if value not in allowed:
            raise serializers.ValidationError(
                "approval_status must be either 'APPROVED' or 'REJECTED'."
            )
        return value


class AdminTranscriptReviewSerializer(serializers.ModelSerializer):
    """Everything a reviewer needs, and nothing that identifies by NRIC.

    classification_reasons is included deliberately: a reviewer handed a bare
    score cannot tell a document that scored 75 on real arithmetic from one
    that scored 75 on a convincing letterhead.
    """
    student_name   = serializers.CharField(source="student.student_name", read_only=True)
    matric_number  = serializers.CharField(source="student.matric_number", read_only=True)
    student_email  = serializers.CharField(source="student.user.email", read_only=True)
    reviewed_by_name = serializers.CharField(
        source="reviewed_by.admin_name", read_only=True, default=None)
    subjects_found = serializers.SerializerMethodField()

    class Meta:
        model  = TranscriptUpload
        fields = [
            "id", "student_name", "matric_number", "student_email",
            "original_name", "uploaded_time", "status",
            "document_type_status", "classification_score",
            "classification_reasons", "detected_institution",
            "student_identity_matched",
            "verification_status", "verification_method",
            "reviewed_by_name", "reviewed_at", "rejection_reason",
            "skills_applied_at", "skills_added",
            "parsed_subjects", "subjects_found", "error_message",
        ]

    def get_subjects_found(self, obj):
        return len(obj.parsed_subjects or [])
