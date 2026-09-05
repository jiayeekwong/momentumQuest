from django.utils import timezone
from rest_framework import serializers

from accounts.models import StudentSkill, UserConsent
from . import cv_receipt
from resources.models import Certificate
from scrape_jobs.models import Skill
from .matching import (
    MatchScoreMixin, match_score, snapshot_skill_levels, student_skill_levels,
)
from .models import JobApplication, JobListing, JobSkill


class RequiredSkillField(serializers.Field):
    """One entry of ``required_skills``.

    Accepts either ``"Python"`` or ``{"name": "Python", "level": "ADVANCED"}``.
    The bare-string form is what the post-job form has always sent and is kept
    working; it means INTERMEDIATE, the same default a scraped listing gets.
    """

    default_level = StudentSkill.SkillLevel.INTERMEDIATE

    def to_internal_value(self, data):
        if isinstance(data, str):
            name, level = data, self.default_level
        elif isinstance(data, dict):
            name = data.get('name', '')
            level = data.get('level') or self.default_level
        else:
            raise serializers.ValidationError(
                'Expected a skill name or {"name": ..., "level": ...}.')

        name = str(name).strip()
        if not name:
            raise serializers.ValidationError('Skill name is required.')
        if level not in StudentSkill.SkillLevel.values:
            raise serializers.ValidationError(
                f'Unknown proficiency level: {level}. '
                f'Expected one of {", ".join(StudentSkill.SkillLevel.values)}.')
        return {
            'name': name[:100],
            'level': level,
            # Distinguishes "Advanced, explicitly" from "level not stated".
            # _sync_skills preserves an existing level in the latter case.
            'level_specified': isinstance(data, dict) and bool(data.get('level')),
        }

    def to_representation(self, value):
        return value


class JobListingWriteSerializer(serializers.ModelSerializer):
    required_skills = serializers.ListField(
        child=RequiredSkillField(),
        write_only=True,
        required=False,
        default=list,
    )

    class Meta:
        model = JobListing
        fields = [
            'id', 'job_title', 'category', 'description',
            'salary_min', 'salary_max', 'work_mode',
            'experience_level', 'closing_date', 'status',
            'required_skills',
        ]

    def _sync_skills(self, job, skill_specs):
        # Requirements are rebuilt from scratch on every edit, so a level the
        # payload does not state has to be carried across explicitly.
        # Otherwise a client that sends names only -- which the edit form
        # still does -- would silently reset every Advanced requirement to the
        # Intermediate default, changing who matches the job.
        previous_levels = {
            row.skill_id: row.required_level
            for row in JobSkill.objects.filter(job=job)
        }
        JobSkill.objects.filter(job=job).delete()

        for spec in skill_specs:
            skill = Skill.objects.filter(skill_name__iexact=spec['name']).first()
            if not skill:
                # Quarantined, not published. A name typed into an employer's
                # job form used to land as is_active=True / ACTIVE_INTERNAL --
                # indistinguishable from a curated skill -- so a typo like
                # "Pyhton" or a vague "good communication" entered the global
                # vocabulary and the extractor then matched it against every
                # scraped advert from then on.
                #
                # The job still links to it: matching reads job.job_skills
                # directly and does not consult is_active, so this employer's
                # own listing is unaffected. What it cannot do is join the
                # extractor's term list, which filters on is_active, until a
                # reviewer promotes it.
                skill = Skill.objects.create(
                    skill_name=spec['name'],
                    is_active=False,
                    catalogue_status=Skill.CatalogueStatus.REVIEW_REQUIRED,
                )

            level = spec['level']
            if not spec['level_specified'] and skill.id in previous_levels:
                level = previous_levels[skill.id]

            JobSkill.objects.get_or_create(
                job=job,
                skill=skill,
                defaults={'required_level': level},
            )

    def create(self, validated_data):
        skill_names = validated_data.pop('required_skills', [])
        job = JobListing.objects.create(**validated_data)
        from scrape_jobs.services import get_or_create_job_title
        job.job_title_ref = get_or_create_job_title(job.job_title, job.category)
        job.save(update_fields=['job_title_ref'])
        self._sync_skills(job, skill_names)
        return job

    def update(self, instance, validated_data):
        skill_names = validated_data.pop('required_skills', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if 'job_title' in validated_data or 'category' in validated_data:
            from scrape_jobs.services import get_or_create_job_title
            instance.job_title_ref = get_or_create_job_title(instance.job_title, instance.category)
            instance.save(update_fields=['job_title_ref'])
        if skill_names is not None:
            self._sync_skills(instance, skill_names)
        return instance


class JobListingReadSerializer(MatchScoreMixin, serializers.ModelSerializer):
    required_skills    = serializers.SerializerMethodField()
    applicants_count   = serializers.SerializerMethodField()
    # Null for anonymous visitors and company accounts — see MatchScoreMixin.
    match_score        = serializers.SerializerMethodField()
    required_skill_levels = serializers.SerializerMethodField()
    category_name      = serializers.CharField(source='category.category_name',
                                               read_only=True, default=None)
    company            = serializers.SerializerMethodField()

    class Meta:
        model = JobListing
        fields = [
            'id', 'job_title', 'category', 'category_name', 'company', 'description',
            'salary_min', 'salary_max', 'work_mode', 'experience_level',
            'closing_date', 'status', 'posted_time',
            'required_skills', 'required_skill_levels',
            'applicants_count', 'match_score',
        ]

    def get_required_skills(self, obj):
        # Iterated in Python rather than re-queried so the prefetch on the
        # queryset is actually used and match_score adds no queries.
        return [row.skill.skill_name for row in obj.job_skills.all()]

    def get_required_skill_levels(self, obj):
        # Kept separate from required_skills so the existing name-only shape
        # that the frontend consumes is unchanged.
        return [
            {'skill': row.skill.skill_name, 'required_level': row.required_level}
            for row in obj.job_skills.all()
        ]

    def get_applicants_count(self, obj):
        return obj.applications.count()

    def get_company(self, obj):
        return {
            'id': obj.company.company_id,
            'company_name': obj.company.company_name,
        } if obj.company else None


class JobListingSummarySerializer(serializers.ModelSerializer):
    applicants_count = serializers.SerializerMethodField()
    category_name    = serializers.CharField(source='category.category_name',
                                              read_only=True, default=None)

    class Meta:
        model = JobListing
        fields = [
            'id', 'job_title', 'category_name', 'status',
            'closing_date', 'posted_time', 'applicants_count',
            'work_mode', 'experience_level',
        ]

    def get_applicants_count(self, obj):
        return obj.applications.count()


def verified_skill_ids(student):
    """Skill ids this student has administrator-checked evidence for.

    Two routes lead here and both count. A certificate an administrator
    approved, and a transcript an administrator verified -- the transcript
    route was added later, and reading only certificates meant a student whose
    skill came from a reviewed transcript was reported to employers as
    unverified, which is the opposite of what the review established.

    Evidence resting on a withdrawn consent does not count: the student has
    revoked the permission that made it usable.
    """
    from resources.models import (
        Certificate, CertificateSkillEvidence, TranscriptSkillEvidence,
        TranscriptUpload,
    )

    # Read per claim, not per document: an approved certificate can carry
    # claims the administrator refused, and reporting those as verified would
    # tell an employer a skill was checked when it was checked and rejected.
    from_certificates = set(
        CertificateSkillEvidence.objects
        .filter(certificate__student=student,
                review_status=CertificateSkillEvidence.ReviewStatus.APPROVED,
                certificate__verified_status=Certificate.VerifiedStatus.APPROVED)
        .exclude(certificate__upload_consent__withdrawn_at__isnull=False)
        .values_list("skill_id", flat=True)
    )

    from_transcripts = set(
        TranscriptSkillEvidence.objects
        .filter(
            transcript__student=student,
            transcript__verification_status__in=(
                TranscriptUpload.VerificationStatus.AUTO_VERIFIED,
                TranscriptUpload.VerificationStatus.MANUALLY_VERIFIED,
            ),
        )
        .exclude(transcript__upload_consent__withdrawn_at__isnull=False)
        .values_list("skill_id", flat=True)
    )

    return from_certificates | from_transcripts


class ApplicantSnapshotSerializer(serializers.Serializer):
    """What the student confirmed after their CV was read.

    Bounded on every axis. The values arrive from a client that can send
    anything, and the result is written to a JSONField -- which will store
    whatever it is given, including a megabyte of nested junk, without
    complaint. Every limit here exists because the model layer has none.
    """

    MAX_ENTRIES = 40
    MAX_ENTRY_LENGTH = 200

    skills = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        required=False, allow_empty=True, max_length=200,
    )
    education = serializers.ListField(
        child=serializers.CharField(max_length=MAX_ENTRY_LENGTH,
                                    allow_blank=True, trim_whitespace=True),
        required=False, allow_empty=True, max_length=MAX_ENTRIES,
    )
    experience = serializers.ListField(
        child=serializers.CharField(max_length=MAX_ENTRY_LENGTH,
                                    allow_blank=True, trim_whitespace=True),
        required=False, allow_empty=True, max_length=MAX_ENTRIES,
    )

    def to_internal_value(self, data):
        # A list, a string or null here would otherwise reach ListField and
        # raise something shaped like a 500 rather than a field error.
        if not isinstance(data, dict):
            raise serializers.ValidationError(
                "Confirmed CV information must be an object.")

        # The parser proposes skills as objects; the student's client may send
        # them back unchanged. Accept either shape and keep only the id -- the
        # name and level are re-read from the database, never trusted.
        skills = data.get("skills")
        if isinstance(skills, list):
            data = dict(data)
            data["skills"] = [
                entry.get("skill_id") if isinstance(entry, dict) else entry
                for entry in skills
            ]
        return super().to_internal_value(data)

    def validate_skills(self, value):
        """Reject unknown skill ids rather than silently dropping them.

        Dropping them would let a student submit an application they believe
        lists five skills while the employer sees two.
        """
        ids = set(value)
        if not ids:
            return []
        known = set(Skill.objects.filter(id__in=ids).values_list("id", flat=True))
        unknown = ids - known
        if unknown:
            raise serializers.ValidationError(
                f"Unknown skill id(s): {sorted(unknown)}.")
        return list(ids)

    @staticmethod
    def _clean_lines(values):
        return [line.strip() for line in (values or []) if line and line.strip()]

    def build(self, student, confirmed):
        """Freeze the confirmed data into the stored snapshot.

        ``confirmed`` is this field's already-validated output, handed in by
        the parent. A nested serializer used as a field never populates its own
        ``validated_data`` -- the parent's holds the result -- so reading it
        here would raise instead of returning the data.

        Skill levels and verified status are read from the database here, not
        from the client: a CV says which skills are claimed, the profile says
        how good the student is at them, and an administrator's decision says
        whether that is backed by evidence. Letting a client assert any of the
        three would let anyone score 100% on any advert and appear verified
        doing it.
        """
        skill_ids = confirmed.get("skills", [])

        held_levels = {
            row.skill_id: row.skill_level
            for row in student.student_skills.all()
        }
        # Captured now, and never recomputed. An employer looking at this
        # application in six weeks must see what was true when it was sent,
        # not what has become true since.
        verified_ids = verified_skill_ids(student)

        skills = [
            {
                "skill_id": skill.id,
                "skill_name": skill.skill_name,
                # None when the skill is claimed but never validated; the
                # match score treats that as unproven.
                "skill_level": held_levels.get(skill.id),
                "verified": skill.id in verified_ids,
            }
            for skill in Skill.objects.filter(id__in=skill_ids)
        ]

        return {
            "skills": skills,
            "education": self._clean_lines(confirmed.get("education")),
            "experience": self._clean_lines(confirmed.get("experience")),
            "captured_at": timezone.now().isoformat(),
        }


class JobApplicationCreateSerializer(serializers.Serializer):
    """Validates a submission before anything is written.

    Replaces reading ``request.data`` key by key in the view. That older
    approach coerced with ``bool(...)``, which turns the string "false" -- what
    a form-encoded client sends for an unchecked box -- into True, and silently
    accepted any shape for the snapshot. Malformed input must produce a 400
    naming the field, never a 500 and never a wrong answer recorded as fact.
    """

    job = serializers.PrimaryKeyRelatedField(queryset=JobListing.objects.none())
    cv_parse_receipt = serializers.CharField(max_length=2048)
    applicant_snapshot = ApplicantSnapshotSerializer()
    # No default: an unanswered work-permit question must be an error, not a
    # guess in either direction.
    needs_work_permit = serializers.BooleanField()
    available_from = serializers.DateField(required=False, allow_null=True)
    phone = serializers.CharField(max_length=30, required=False, allow_blank=True)
    cover_note = serializers.CharField(max_length=5000, required=False, allow_blank=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Students apply internally to company-posted adverts only. Scoping the
        # queryset means an id outside that set is a field error rather than a
        # 404 for a job the student can see listed.
        self.fields["job"].queryset = JobListing.objects.filter(
            status="ACTIVE", source_type="COMPANY")

    def validate_job(self, job):
        if job.closing_date and job.closing_date < timezone.localdate():
            raise serializers.ValidationError(
                "Applications for this job have closed.")
        return job

    def validate_cv_parse_receipt(self, token):
        """Check the receipt was issued by us, to this student, recently."""
        try:
            payload = cv_receipt.verify(token, self.context["request"].user.id)
        except cv_receipt.InvalidReceipt as exc:
            raise serializers.ValidationError(str(exc))

        # The signature proves this server issued the receipt, not that the
        # row it names is still there -- a receipt outliving its database
        # (a dev reset, say) would otherwise reach the FK and surface as an
        # IntegrityError the submit view reports as "already applied".
        consent = UserConsent.objects.filter(
            pk=payload.get("consent_id"),
            user=self.context["request"].user,
            consent_type=UserConsent.ConsentType.CV_PROCESSING_CONSENT,
        ).first()
        if consent is None:
            raise serializers.ValidationError(
                "Your CV was read too long ago. Please upload it again.")

        # A withdrawn consent authorises nothing further. Without this the
        # receipt would outlive the permission it represents: a student could
        # withdraw and still submit an application built on the parse it
        # allowed.
        if not consent.is_live:
            raise serializers.ValidationError(
                "The consent for this CV has been withdrawn. Please upload your "
                "CV again to continue.")

        self._receipt_payload = payload
        return token

    def validate(self, attrs):
        student = self.context["student"]
        job = attrs["job"]

        if JobApplication.objects.filter(student=student, job=job).exists():
            raise serializers.ValidationError(
                {"job": "You have already applied to this job."})

        snapshot = self.fields["applicant_snapshot"].build(
            student, attrs["applicant_snapshot"])
        if not any((snapshot["skills"], snapshot["education"],
                    snapshot["experience"])):
            raise serializers.ValidationError(
                {"applicant_snapshot":
                    "Please upload and confirm your CV before applying."})

        attrs["built_snapshot"] = snapshot
        return attrs

    @property
    def cv_consent_id(self):
        return getattr(self, "_receipt_payload", {}).get("consent_id")


class JobApplicationSerializer(serializers.ModelSerializer):
    student_name   = serializers.CharField(source='student.student_name', read_only=True)
    student_email  = serializers.CharField(source='student.user.email', read_only=True)
    student_skills = serializers.SerializerMethodField()
    match_score    = serializers.SerializerMethodField()
    job_title      = serializers.CharField(source='job.job_title', read_only=True)

    class Meta:
        model = JobApplication
        fields = [
            'id', 'student_name', 'student_email', 'student_skills',
            'match_score', 'job_title', 'job',
            'applicant_snapshot', 'status', 'applied_time', 'is_read',
            'needs_work_permit', 'available_from', 'phone', 'cover_note',
        ]

    def get_student_skills(self, obj):
        """The skills as submitted, each flagged with its verified status.

        This is the whole of what an employer learns about an applicant's
        evidence. A skill backed by an administrator-approved certificate comes
        through as ``verified: true`` -- the certificate itself, the document,
        and any identification number printed on it stay out of this payload
        and off every company-reachable route.

        Read from the frozen snapshot, never from the live profile. An employer
        reviewing an application weeks later must see what was submitted: if
        the student has since added skills, withdrawn a certificate, or had one
        revoked, none of that may rewrite an application already sent.

        A snapshot with an empty skill list stays empty. Falling back to the
        live profile there would quietly show the employer skills the student
        chose not to submit.
        """
        snapshot = obj.applicant_snapshot or {}

        if "skills" in snapshot:
            return [
                {
                    "skill_name": entry.get("skill_name"),
                    "skill_level": entry.get("skill_level"),
                    # Older snapshots predate the verified flag. Absent means
                    # unknown, and unknown must not be presented as verified.
                    "verified": bool(entry.get("verified", False)),
                }
                for entry in (snapshot.get("skills") or [])
            ]

        # Legacy rows only: applications stored before snapshots existed have
        # no skills key at all, and the live profile is the best answer
        # available for them. It is the wrong answer for any new application,
        # which is why the branch is keyed on the key being absent rather than
        # on the list being empty.
        verified = verified_skill_ids(obj.student)
        return [
            {
                'skill_name': row.skill.skill_name,
                'skill_level': row.skill_level,
                'verified': row.skill_id in verified,
            }
            for row in obj.student.student_skills.select_related('skill')
        ]

    def get_match_score(self, obj):
        """Proficiency-weighted match against the submitted snapshot.

        Scored on what the applicant presented, not on their profile today:
        an employer must see the application as sent, and a student editing
        their skills must not silently re-score applications already made.
        """
        return match_score(obj.job, snapshot_skill_levels(obj))


class JobApplicationStatusSerializer(serializers.ModelSerializer):
    class Meta:
        model = JobApplication
        fields = ['status']


class StudentApplicationSerializer(serializers.ModelSerializer):
    """A student's own view of an application they submitted.

    Deliberately separate from JobApplicationSerializer: that one is the
    employer's screening view and exposes match_score and the applicant's full
    skill list. What a student needs back is the advert they applied to and
    where the application stands, not the numbers they are being screened by.

    ``job_title`` is the raw employer title, which is what the student
    clicked Apply on.
    """
    job_title      = serializers.CharField(source='job.job_title', read_only=True)
    company_name   = serializers.SerializerMethodField()
    work_mode      = serializers.CharField(source='job.work_mode', read_only=True)
    category_name  = serializers.CharField(source='job.category.category_name',
                                           read_only=True, default=None)
    job_status     = serializers.CharField(source='job.status', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = JobApplication
        fields = [
            'id', 'job', 'job_title', 'company_name', 'work_mode',
            'category_name', 'job_status', 'status', 'status_display',
            'applied_time', 'applicant_snapshot', 'needs_work_permit', 'available_from',
            'phone', 'cover_note',
        ]

    def get_company_name(self, obj):
        if obj.job.company:
            return obj.job.company.company_name
        return obj.job.company_name or 'External employer'
