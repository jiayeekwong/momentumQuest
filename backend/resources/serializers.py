import json

from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import URLValidator
from django.db import IntegrityError, transaction
from rest_framework import serializers

from accounts.departments import COURSE_DEPARTMENTS, validate_department
from accounts.models import Department, StudentSkill, User
from scrape_jobs.models import Skill
from . import private_storage
from .attachments import (
    TRAINING_ATTACHMENT_DIR,
    InvalidAttachmentReceipt,
    build_attachment_url,
    managed_attachment_name,
    verify_attachment_receipt,
)
from .models import (
    CourseSkill,
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
    skill_names = serializers.SerializerMethodField()

    class Meta:
        model  = Course
        fields = ["id", "admin", "skill", "skill_names", "course_code", "title",
                  "course_url", "departments", "updated_at"]

    def get_skill_names(self, obj):
        """Every skill the course teaches, the headline one first."""
        return [link.skill.skill_name
                for link in obj.skill_links.select_related("skill")
                .order_by("-is_primary", "skill__skill_name")]


class CourseWriteSerializer(serializers.ModelSerializer):
    #: Several, because a course teaches several things. The first is the
    #: headline one, kept on Course.skill because every existing caller reads
    #: it; the rest go to CourseSkill, which is the table that exists for this.
    skill_names = serializers.ListField(
        child=serializers.CharField(allow_blank=False),
        write_only=True, required=True, allow_empty=False)
    #: Several, because a module is commonly shared -- "Compulsory" for one
    #: cohort and a named department's elective for another -- and one value
    #: made an administrator pick one of them and be wrong for everybody else.
    departments = serializers.ListField(
        child=serializers.CharField(allow_blank=False),
        required=False, allow_empty=True)
    # Optional, and blank is stored as NULL. The courses already in the table
    # predate the field, and PostgreSQL counts every empty string as equal --
    # so blanks would collide under the unique constraint where NULLs do not.
    course_code = serializers.CharField(max_length=20, required=False,
                                        allow_blank=True, allow_null=True)

    class Meta:
        model  = Course
        fields = ["id", "course_code", "title", "departments", "course_url",
                  "skill_names", "updated_at"]
        read_only_fields = ["id", "updated_at"]

    def to_representation(self, instance):
        """Return the complete course after a create or update.

        ``skill_names`` is write-only here because it is not a model field.
        Without an explicit read representation, successful mutations omitted
        the saved skills and the admin page kept rendering its stale local
        copy until the next full page load.
        """
        return CourseSerializer(instance, context=self.context).data

    def validate_course_code(self, value):
        """Normalise, then check it is free -- in that order.

        Declaring the field explicitly drops the uniqueness validator a
        ModelSerializer would have added, and that validator would not have
        been enough anyway: it runs before this method, on the value as typed,
        so "wix1001" passed it and then collided with WIX1001 at the database
        constraint -- an IntegrityError, which is a 500 rather than a message
        naming the course already using the code.
        """
        code = (value or "").strip().upper() or None
        if code is None:
            return None

        taken = Course.objects.filter(course_code=code)
        if self.instance is not None:
            taken = taken.exclude(pk=self.instance.pk)
        if taken.exists():
            raise serializers.ValidationError(
                f"{code} is already used by {taken.first().title}.")
        return code

    def validate_departments(self, value):
        """Each one has to be a department, and each one only once.

        A course may also be "Compulsory", which is not something a student
        can belong to -- hence the wider list.
        """
        seen = []
        for name in value:
            validate_department(name, allowed=COURSE_DEPARTMENTS)
            if name not in seen:
                seen.append(name)
        return seen

    def validate_skill_names(self, value):
        """Trimmed, de-duplicated, order kept: the first is the headline one."""
        seen = []
        for name in value:
            cleaned = name.strip()
            if cleaned and cleaned not in seen:
                seen.append(cleaned)
        if not seen:
            raise serializers.ValidationError("At least one skill is required.")
        return seen

    @staticmethod
    def _resolve(names):
        """The names as catalogue skills, in the order they were given.

        Course.skill is not nullable, so this runs before the row is created
        rather than after: creating first and attaching second violated the
        constraint on the insert.
        """
        skills = []
        for name in names:
            skill = resolve_or_quarantine_skill(name)
            if skill is not None and skill not in skills:
                skills.append(skill)
        if not skills:
            raise serializers.ValidationError(
                {"skill_names": ["None of these could be read as a skill."]})
        return skills

    @staticmethod
    def _link(course, skills):
        """Rewrite the course's skill links to exactly these.

        Replaces rather than adds: a skill the administrator removed has to
        actually go, or an edit could only ever widen what a course claims to
        teach. The first is the headline one, which Course.skill keeps because
        every existing caller reads it.
        """
        CourseSkill.objects.filter(course=course).exclude(
            skill__in=skills).delete()
        for position, skill in enumerate(skills):
            CourseSkill.objects.update_or_create(
                course=course, skill=skill,
                defaults={"is_primary": position == 0})

    def create(self, validated_data):
        skills = self._resolve(validated_data.pop("skill_names", []))
        course = Course.objects.create(skill=skills[0], **validated_data)
        self._link(course, skills)
        return course

    def update(self, instance, validated_data):
        names = validated_data.pop("skill_names", None)
        skills = self._resolve(names) if names is not None else None

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if skills:
            instance.skill = skills[0]
        instance.save()

        if skills:
            self._link(instance, skills)
        return instance


class CertificateSkillEvidenceSerializer(serializers.ModelSerializer):
    """One skill claim on a certificate, as read back."""

    skill      = serializers.CharField(source="skill.skill_name", read_only=True)
    skill_id   = serializers.IntegerField(read_only=True)
    # What this claim currently contributes to the student's skill profile.
    granted_level = serializers.SerializerMethodField()

    class Meta:
        model  = CertificateSkillEvidence
        fields = ["id", "skill", "skill_id", "claimed_level", "approved_level",
                  "granted_level", "review_status", "review_note", "reviewed_at"]

    def get_granted_level(self, obj):
        return obj.effective_level


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


class CertificateUploadSerializer(serializers.ModelSerializer):
    """Validates the metadata a student submits with a certificate.

    The uploaded file itself is handled by the view, not here: it is written
    to PRIVATE_MEDIA_ROOT rather than to a model FileField, matching how
    TranscriptUpload stores its PDF.
    """

    # The student acknowledges, per upload, that the private document may
    # contain identity information. It is owner-only and is not reviewed by an
    # administrator, but consent to store this specific file is still needed.
    document_consent_ack = serializers.BooleanField(write_only=True)

    # The skills the student declares from this document. One certificate may
    # cover several, and requiring one upload per skill would store duplicates.
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
                "You must acknowledge the certificate upload notice before "
                "uploading a document."
            )
        return value

    def validate(self, attrs):
        # Keep a source behind each declaration: either the private document or
        # a credential URL supplied by the student.
        has_file = bool(self.context.get("uploaded_file"))
        if not attrs.get("cert_url") and not has_file:
            raise serializers.ValidationError(
                "Attach the certificate file or paste its credential URL."
            )
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
    attachment_receipt = serializers.CharField(
        write_only=True, required=False, allow_blank=True, max_length=2048)
    # A receipt-bearing URL is generated by this API and may use testserver or
    # localhost, which Django's URLField validator rejects before the receipt
    # can be checked. External links still receive normal URL validation.
    supporting_doc = serializers.CharField(
        required=False, allow_blank=True, allow_null=True, max_length=200)
    department = serializers.SlugRelatedField(
        slug_field="name", required=False,
        queryset=Department.objects.filter(is_active=True))

    class Meta:
        model  = TrainingProgramme
        fields = [
            "id", "company", "company_name", "skill", "skill_name",
            "title", "description", "programme_duration", "supporting_doc",
            "attachment_receipt", "department", "approval_status",
            "visibility", "rejection_reason", "reviewed_at", "submission_time",
        ]
        read_only_fields = [
            "id", "company", "skill", "approval_status", "visibility",
            "rejection_reason", "reviewed_at", "submission_time",
        ]

    def get_company_name(self, obj):
        return obj.company.company_name if obj.company else None

    def validate_supporting_doc(self, value):
        if not value or managed_attachment_name(value, TRAINING_ATTACHMENT_DIR):
            return value
        try:
            URLValidator()(value)
        except DjangoValidationError:
            raise serializers.ValidationError("Enter a valid URL.")
        return value

    def validate(self, attrs):
        request = self.context.get("request")
        if (request is not None and request.user.role == User.Role.COMPANY
                and self.instance is None and not attrs.get("department")):
            raise serializers.ValidationError({
                "department": "Select the department that should review this programme."
            })

        receipt = attrs.pop("attachment_receipt", "")
        requested_url = attrs.get(
            "supporting_doc",
            self.instance.supporting_doc if self.instance else None,
        )
        existing_unchanged = bool(
            self.instance and requested_url == self.instance.supporting_doc)

        if receipt:
            request = self.context.get("request")
            if request is None:
                raise serializers.ValidationError({
                    "attachment_receipt": "The upload could not be verified."
                })
            try:
                path, name = verify_attachment_receipt(
                    receipt, request.user.id, TRAINING_ATTACHMENT_DIR)
            except InvalidAttachmentReceipt as exc:
                raise serializers.ValidationError(
                    {"attachment_receipt": str(exc)})

            used = TrainingProgramme.objects.filter(attachment_path=path)
            if self.instance:
                used = used.exclude(pk=self.instance.pk)
            if used.exists():
                raise serializers.ValidationError({
                    "attachment_receipt":
                        "This upload has already been attached to a programme."
                })
            attrs["supporting_doc"] = build_attachment_url(
                request, TRAINING_ATTACHMENT_DIR, name)
            self._attachment_path_update = path
        elif managed_attachment_name(requested_url, TRAINING_ATTACHMENT_DIR):
            if not existing_unchanged:
                raise serializers.ValidationError({
                    "attachment_receipt":
                        "Upload the attachment again before saving this programme."
                })
        elif (self.instance is not None and "supporting_doc" in attrs
              and not existing_unchanged):
            # Cleared or replaced with an external link.
            self._attachment_path_update = None

        return attrs

    def create(self, validated_data):
        skill = resolve_or_quarantine_skill(
            validated_data.pop("skill_name", ""))
        if hasattr(self, "_attachment_path_update"):
            validated_data["attachment_path"] = self._attachment_path_update
        try:
            with transaction.atomic():
                return TrainingProgramme.objects.create(
                    skill=skill, **validated_data)
        except IntegrityError:
            path = validated_data.get("attachment_path")
            if path and TrainingProgramme.objects.filter(
                    attachment_path=path).exists():
                raise serializers.ValidationError({
                    "attachment_receipt":
                        "This upload has already been attached to a programme."
                })
            raise

    def update(self, instance, validated_data):
        if "skill_name" in validated_data:
            instance.skill = resolve_or_quarantine_skill(
                validated_data.pop("skill_name"))

        old_path = instance.attachment_path
        if hasattr(self, "_attachment_path_update"):
            validated_data["attachment_path"] = self._attachment_path_update
        try:
            with transaction.atomic():
                updated = super().update(instance, validated_data)
                new_path = updated.attachment_path
                if old_path and old_path != new_path:
                    transaction.on_commit(
                        lambda path=old_path: private_storage.delete(path))
                return updated
        except IntegrityError:
            path = validated_data.get("attachment_path")
            if path and TrainingProgramme.objects.filter(
                    attachment_path=path).exclude(pk=instance.pk).exists():
                raise serializers.ValidationError({
                    "attachment_receipt":
                        "This upload has already been attached to a programme."
                })
            raise


class TrainingProgrammeReviewSerializer(serializers.ModelSerializer):
    """
    Admin review serializer — only `approval_status` is writable.
    The title/company/skill fields are exposed read-only so the admin UI
    can render context without a second request.
    """
    company = serializers.StringRelatedField(read_only=True)
    skill   = serializers.StringRelatedField(read_only=True)
    department = serializers.SlugRelatedField(
        slug_field="name", read_only=True)

    class Meta:
        model  = TrainingProgramme
        fields = [
            "id", "title", "company", "skill", "department",
            "approval_status", "visibility", "rejection_reason",
        ]
        read_only_fields = ["id", "title", "company", "skill", "department"]

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

    def validate(self, attrs):
        if self.instance.approval_status != TrainingProgramme.ApprovalStatus.PENDING:
            raise serializers.ValidationError({
                "approval_status": "Only a pending programme can be reviewed."
            })
        decision = attrs.get("approval_status")
        if decision == TrainingProgramme.ApprovalStatus.APPROVED:
            if attrs.get("visibility") not in TrainingProgramme.Visibility.values:
                raise serializers.ValidationError({
                    "visibility": "Choose department students or all students."
                })
            attrs["rejection_reason"] = ""
        elif decision == TrainingProgramme.ApprovalStatus.REJECTED:
            if not attrs.get("rejection_reason", "").strip():
                raise serializers.ValidationError({
                    "rejection_reason": "Give the company a reason for rejection."
                })
            attrs["visibility"] = None
        return attrs


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
