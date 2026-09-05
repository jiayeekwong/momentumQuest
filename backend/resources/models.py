from django.db import models

from accounts.models import AdminProfile, Company, Student, StudentSkill
from scrape_jobs.models import Skill
from config.sanitization import sanitize_html, sanitize_text


class LearningResource(models.Model):
    """
    Scraped from third-party platforms (freeCodeCamp, Coursera, Microsoft Learn, etc.).
    Students are redirected to the external URL — they do not enrol through MomentumQuest.
    """
    skill      = models.ForeignKey(Skill, on_delete=models.CASCADE,
                                   related_name="learning_resources")
    title      = models.CharField(max_length=255)
    platform   = models.CharField(max_length=100)
    url        = models.URLField()
    type       = models.CharField(max_length=100)
    is_active  = models.BooleanField(default=True)
    scraped_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("skill", "url")
        ordering = ["platform", "title"]

    def __str__(self):
        return f"{self.title} [{self.platform}] — {self.skill.skill_name}"


class CourseCatalogue(models.Model):
    """Every course seen on a platform's category listing, kept whether or not
    a skill could be mapped to it.

    The Coursera scraper used to discard a course unless a Skill name appeared
    literally in its title. That threw away most of what it fetched -- 59 rows
    survived out of a ~145-link ceiling -- and left 418 of the 462 in-demand
    skills with nothing to offer a student.

    Storing the course first and mapping skills second separates two failures
    that were previously one: not finding a course, and not recognising what it
    teaches. Only the first needs the network, so a mapping that improves later
    is re-run over this table rather than re-scraped.

    ``LearningResource`` is unchanged and still keyed by (skill, url); it is now
    generated from these rows instead of written directly by the scraper.
    """
    #: Coursera's own category names, exactly as they appear in its taxonomy.
    COMPUTER_SCIENCE = "Computer Science"
    INFORMATION_TECHNOLOGY = "Information Technology"
    DATA_SCIENCE = "Data Science"

    url        = models.URLField(unique=True)
    title      = models.CharField(max_length=255)
    platform   = models.CharField(max_length=100)
    type       = models.CharField(max_length=100)
    #: Every category the course was found under. A list rather than a column
    #: because Coursera files one course under several -- "Machine Learning"
    #: sits in both Computer Science and Data Science -- and collapsing that to
    #: one value would either duplicate the course or lose where it came from.
    categories = models.JSONField(default=list)
    #: The listing card's own text: skills-gained line, partner, level. Kept raw
    #: because it is the only evidence of what a course teaches that the listing
    #: page offers, and the mapping pass must be re-runnable without the network.
    card_text  = models.TextField(blank=True)
    is_active  = models.BooleanField(default=True)
    scraped_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["platform", "title"]

    def __str__(self):
        return f"{self.title} [{self.platform}]"


class Course(models.Model):
    """
    University's own internal courses, managed by admin (UC-27).
    Different from LearningResource — these are not scraped from external platforms.
    """
    admin      = models.ForeignKey(AdminProfile, on_delete=models.SET_NULL,
                                   null=True, related_name="courses")
    #: The course's primary skill, kept because every existing caller reads
    #: it. One course usually teaches several things, which is what ``skills``
    #: below records; this stays as the headline one.
    skill      = models.ForeignKey(Skill, on_delete=models.CASCADE,
                                   related_name="courses")
    skills     = models.ManyToManyField(Skill, through="CourseSkill",
                                        related_name="taught_by_courses",
                                        blank=True)
    title      = models.CharField(max_length=255)
    course_url = models.URLField(blank=True)
    department = models.CharField(max_length=100, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["title"]

    def __str__(self):
        return self.title


class CourseSkill(models.Model):
    """Every skill a course teaches.

    A single foreign key could not describe a course called "Python, Machine
    Learning", and the workaround was a Skill row whose *name* was that comma
    separated list -- seven of which sat in the catalogue matching nothing.
    This table is what those rows were trying to be.
    """
    course = models.ForeignKey("Course", on_delete=models.CASCADE,
                               related_name="skill_links")
    skill = models.ForeignKey(Skill, on_delete=models.CASCADE,
                              related_name="course_links")
    is_primary = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("course", "skill")
        ordering = ["course_id", "-is_primary"]

    def __str__(self):
        return "%s -> %s" % (self.course_id, self.skill_id)


class TrainingProgrammeSkill(models.Model):
    """Every skill a training programme covers. See :class:`CourseSkill`."""
    programme = models.ForeignKey("TrainingProgramme",
                                  on_delete=models.CASCADE,
                                  related_name="skill_links")
    skill = models.ForeignKey(Skill, on_delete=models.CASCADE,
                              related_name="programme_links")
    is_primary = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("programme", "skill")
        ordering = ["programme_id", "-is_primary"]

    def __str__(self):
        return "%s -> %s" % (self.programme_id, self.skill_id)


class Certificate(models.Model):
    """
    Proof of completion uploaded by a student after an external course.

    The document only. The skills it is offered as proof of are
    CertificateSkillEvidence rows, because one certificate routinely evidences
    several -- and because an administrator reviewing it needs to be able to
    accept some claims and refuse others, which a single skill column made
    impossible.

    An uploaded document may show the student's NRIC/MyKad or passport number.
    That number is never read out of the file into a column here or anywhere
    else; it stays inside the stored bytes, which only the owner and an
    authorised admin can retrieve. See docs/reference/privacy-consent-design.md.
    """
    class VerifiedStatus(models.TextChoices):
        PENDING  = "PENDING",  "Pending"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"

    class CertificateType(models.TextChoices):
        CERTIFICATE = "CERTIFICATE", "Certificate"
        EXAM_RESULT = "EXAM_RESULT", "Examination result"
        TRANSCRIPT  = "TRANSCRIPT",  "Transcript"
        OTHER       = "OTHER",       "Other supporting document"

    class RejectionReason(models.TextChoices):
        # There is deliberately no IDENTITY_NUMBER_MISMATCH. MomentumQuest
        # holds no stored NRIC/passport number, so an admin has nothing to
        # compare the number on a document against; offering the reason would
        # invite a decision the system cannot actually support. NAME_MISMATCH
        # is the check that is genuinely available.
        NAME_MISMATCH             = "NAME_MISMATCH",             "Name does not match"
        UNREADABLE_DOCUMENT       = "UNREADABLE_DOCUMENT",       "Document is unreadable"
        INCORRECT_DOCUMENT        = "INCORRECT_DOCUMENT",        "Incorrect document"
        INSUFFICIENT_INFORMATION  = "INSUFFICIENT_INFORMATION",  "Insufficient information"
        SUSPECTED_INVALID_DOCUMENT = "SUSPECTED_INVALID_DOCUMENT", "Suspected invalid document"
        OTHER                     = "OTHER",                     "Other"

    # Student-facing explanations for each reason. The internal code is for the
    # admin and the database; this is what the student is told, because a
    # student reading "SUSPECTED_INVALID_DOCUMENT" learns nothing useful.
    REJECTION_MESSAGES = {
        RejectionReason.NAME_MISMATCH:
            "Your document could not be verified because the name on the submitted "
            "document does not match your registered information.",
        RejectionReason.UNREADABLE_DOCUMENT:
            "Your document could not be verified because it was not readable. Please "
            "upload a clearer copy.",
        RejectionReason.INCORRECT_DOCUMENT:
            "Your document could not be verified because it does not appear to be the "
            "certificate or result you described.",
        RejectionReason.INSUFFICIENT_INFORMATION:
            "Your document could not be verified because it did not contain enough "
            "information to confirm the qualification or skill.",
        RejectionReason.SUSPECTED_INVALID_DOCUMENT:
            "Your document could not be verified. Please contact your administrator "
            "if you believe this is a mistake.",
        RejectionReason.OTHER:
            "Your document could not be verified. Please contact your administrator "
            "for details.",
    }

    student         = models.ForeignKey(Student, on_delete=models.CASCADE,
                                        related_name="certificates")
    admin           = models.ForeignKey(AdminProfile, on_delete=models.SET_NULL,
                                        null=True, blank=True,
                                        related_name="endorsed_certificates")
    cert_url        = models.URLField(blank=True)
    # Students hold their proof either as a credential link (Coursera, Microsoft
    # Learn) or as a downloaded PDF/image, so both are accepted and exactly one
    # is required. Uploaded files follow TranscriptUpload: stored outside
    # MEDIA_ROOT and reachable only through CertificateFileView, because a
    # certificate carries the student's full name.
    file_path       = models.CharField(max_length=255, blank=True)
    # Kept for display back to the student only. It is never used as the name
    # the file is served under: students name their own downloads, and one
    # called "040910101234_SPM.pdf" would put an identification number into a
    # response header and into whoever's download folder opened it.
    original_name   = models.CharField(max_length=255, blank=True)
    # Detected from the file's own bytes, not from the extension the uploader
    # supplied.
    mime_type       = models.CharField(max_length=100, blank=True)
    certificate_type = models.CharField(max_length=20, choices=CertificateType.choices,
                                        default=CertificateType.CERTIFICATE)
    certificate_name = models.CharField(max_length=255, blank=True)
    # The issuing organisation.
    source          = models.CharField(max_length=100, blank=True)
    uploaded_time   = models.DateTimeField(auto_now_add=True)
    verified_status = models.CharField(
        max_length=20,
        choices=VerifiedStatus.choices,
        default=VerifiedStatus.PENDING,
    )
    verified_at     = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.CharField(max_length=40, choices=RejectionReason.choices,
                                        blank=True)
    # Internal to the admin. Never serialised to a student or a company: an
    # admin's working note about a suspicious submission is not something the
    # submitter should read.
    verification_notes = models.TextField(blank=True)
    # The specific consent that permitted this document to be stored. Makes the
    # upload-time acknowledgement durable evidence rather than a checkbox that
    # existed for one request.
    upload_consent  = models.ForeignKey('accounts.UserConsent', on_delete=models.SET_NULL,
                                        null=True, blank=True,
                                        related_name="certificates")

    class Meta:
        ordering = ["-uploaded_time"]

    @property
    def has_file(self):
        return bool(self.file_path)

    @property
    def rejection_message(self):
        """What the student is shown when a submission is rejected."""
        if self.verified_status != self.VerifiedStatus.REJECTED:
            return ""
        return self.REJECTION_MESSAGES.get(
            self.rejection_reason,
            self.REJECTION_MESSAGES[self.RejectionReason.OTHER],
        )

    def __str__(self):
        name = self.certificate_name or "certificate"
        return f"{self.student} — {name} ({self.verified_status})"


class CertificateSkillEvidence(models.Model):
    """One skill a certificate is offered as proof of, and its decision.

    A certificate is a *document*; the claims it supports are separate facts
    about it. Modelling them as rows rather than as a single FK is what lets
    one upload evidence several skills without storing the file several times,
    and what lets an administrator approve two of three claims -- the common
    case, because a student naturally over-claims from a broad programme.

    ``claimed_level`` is what the student asserted. ``approved_level`` is what
    the administrator was willing to certify, and may be lower: an exaggerated
    claim is corrected rather than causing the whole document to be rejected.

    Only APPROVED rows on an APPROVED certificate count as live evidence, and
    only recalculate_student_skill() reads them into StudentSkill.
    """

    class ReviewStatus(models.TextChoices):
        PENDING  = "PENDING",  "Pending"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"

    #: One document cannot reasonably evidence more than a handful of skills,
    #: and an unbounded list is a cheap way to make review unusable.
    MAX_SKILLS_PER_CERTIFICATE = 10

    certificate    = models.ForeignKey(Certificate, on_delete=models.CASCADE,
                                       related_name="skill_evidence")
    skill          = models.ForeignKey(Skill, on_delete=models.CASCADE,
                                       related_name="certificate_evidence")
    claimed_level  = models.CharField(max_length=20,
                                      choices=StudentSkill.SkillLevel.choices,
                                      default=StudentSkill.SkillLevel.INTERMEDIATE)
    # Blank until reviewed. Separate from claimed_level so the student's claim
    # survives the decision -- overwriting it would destroy the evidence that
    # the claim was ever corrected.
    approved_level = models.CharField(max_length=20,
                                      choices=StudentSkill.SkillLevel.choices,
                                      blank=True)
    review_status  = models.CharField(max_length=10, choices=ReviewStatus.choices,
                                      default=ReviewStatus.PENDING)
    # Why this particular claim was refused, when the document itself is fine.
    review_note    = models.CharField(max_length=255, blank=True)
    created_time   = models.DateTimeField(auto_now_add=True)
    reviewed_at    = models.DateTimeField(null=True, blank=True)

    class Meta:
        # One decision per skill per document. Without this a student could
        # claim Python three times at three levels and the highest would win
        # by accident.
        constraints = [
            models.UniqueConstraint(fields=["certificate", "skill"],
                                    name="unique_certificate_skill_evidence"),
        ]
        ordering = ["certificate_id", "skill__skill_name"]
        verbose_name_plural = "certificate skill evidence"

    def __str__(self):
        return (f"{self.skill.skill_name} "
                f"({self.approved_level or self.claimed_level}) "
                f"[{self.review_status}]")

    @property
    def is_live(self):
        """Whether this row currently supports a StudentSkill level.

        Both facts are required: the document was accepted *and* this
        particular claim was accepted. An approved certificate can carry
        rejected claims, which is the whole point of reviewing them
        separately.
        """
        return (
            self.review_status == self.ReviewStatus.APPROVED
            and bool(self.approved_level)
            and self.certificate.verified_status == Certificate.VerifiedStatus.APPROVED
        )


class SubjectSkillMapping(models.Model):
    """
    Maps a university module code (e.g. WIX1002) to a skill in the database.

    Matching is on subject_code and never on subject_name: the transcript PDF
    text layer collapses spaces unpredictably ("PROJECTMANAGEMENT",
    "KNOWLEDGE MANAGEMENTAND ENGINEERING"), while module codes always extract
    cleanly. subject_name is kept for display and admin readability only.

    One row per subject-skill pair — WIF2003 (Web Programming) produces one
    row each for HTML, CSS and JavaScript.
    """
    subject_code = models.CharField(max_length=20, db_index=True)
    subject_name = models.CharField(max_length=255)
    skill        = models.ForeignKey(Skill, on_delete=models.CASCADE,
                                     related_name="subject_mappings")
    is_active    = models.BooleanField(default=True)

    class Meta:
        unique_together = ("subject_code", "skill")
        ordering = ["subject_code", "skill__skill_name"]

    def __str__(self):
        return f"{self.subject_code} — {self.skill.skill_name}"


class TranscriptUpload(models.Model):
    """
    An academic transcript uploaded by a student (UC: Upload Skill Validation).

    **Parsing is not verification.** A PDF that parses cleanly is not thereby
    an authentic university transcript -- anyone can typeset a document that
    matches the layout. So the two questions are tracked as separate states:

      status                -- could we read examination rows out of it?
      document_type_status  -- does it look like a transcript at all?
      verification_status   -- has the issuer been confirmed?

    Skills are written only when verification_status is a verified value.
    Uploading alone changes nothing about a student's profile.

    The PDF is stored under PRIVATE_MEDIA_ROOT rather than MEDIA_ROOT because
    it contains the student's NRIC; it is served only by TranscriptFileView.
    """
    class Status(models.TextChoices):
        PARSED = "PARSED", "Parsed"
        FAILED = "FAILED", "Failed"

    class DocumentTypeStatus(models.TextChoices):
        LIKELY_TRANSCRIPT = "LIKELY_TRANSCRIPT", "Likely a transcript"
        UNCERTAIN = "UNCERTAIN", "Uncertain"
        NOT_TRANSCRIPT = "NOT_TRANSCRIPT", "Not a transcript"
        # Uploaded before classification existed; skills were already applied
        # without any issuer check. Queued for review rather than trusted.
        LEGACY_UNVERIFIED = "LEGACY_UNVERIFIED", "Legacy, never verified"

    class VerificationStatus(models.TextChoices):
        PENDING = "PENDING", "Awaiting verification"
        AUTO_VERIFIED = "AUTO_VERIFIED", "Automatically verified"
        MANUALLY_VERIFIED = "MANUALLY_VERIFIED", "Verified by an administrator"
        REJECTED = "REJECTED", "Rejected"

    class VerificationMethod(models.TextChoices):
        NONE = "NONE", "None"
        # Verified by the classifier meeting every mandatory gate, including
        # a matric number matching the uploading student. Weaker than a
        # cryptographic check and recorded as its own value so it is never
        # mistaken for one: a forgery carrying this student's own matric and
        # consistent arithmetic would pass. Phase 2 closes that with
        # DIGITAL_SIGNATURE / QR_VERIFICATION.
        CLASSIFICATION = "CLASSIFICATION", "Automatic classification"
        ADMIN_REVIEW = "ADMIN_REVIEW", "Administrator review"
        DIGITAL_SIGNATURE = "DIGITAL_SIGNATURE", "Digital signature"
        QR_VERIFICATION = "QR_VERIFICATION", "QR verification"

    VERIFIED_STATUSES = frozenset({
        VerificationStatus.AUTO_VERIFIED,
        VerificationStatus.MANUALLY_VERIFIED,
    })

    student         = models.ForeignKey(Student, on_delete=models.CASCADE,
                                        related_name="transcripts")
    file_path       = models.CharField(max_length=255, blank=True)
    original_name   = models.CharField(max_length=255, blank=True)
    # The consent that permitted this document to be stored, mirroring
    # Certificate.upload_consent. A transcript is an examination result and
    # carries the student's NRIC, so its acknowledgement is recorded the same
    # way rather than left as a checkbox that existed for one request.
    upload_consent  = models.ForeignKey('accounts.UserConsent', on_delete=models.SET_NULL,
                                        null=True, blank=True,
                                        related_name="transcripts")
    uploaded_time   = models.DateTimeField(auto_now_add=True)
    status          = models.CharField(max_length=20, choices=Status.choices,
                                       default=Status.PARSED)
    parsed_subjects = models.JSONField(default=list, blank=True)
    skills_added    = models.IntegerField(default=0)
    error_message   = models.TextField(blank=True)

    # --- document recognition (is this a transcript?) --------------------
    document_type_status = models.CharField(
        max_length=20, choices=DocumentTypeStatus.choices,
        default=DocumentTypeStatus.UNCERTAIN)
    classification_score = models.IntegerField(default=0)
    # Every signal that fired, in words, so a reviewer can see why the score
    # is what it is instead of being handed a bare number.
    classification_reasons = models.JSONField(default=list, blank=True)
    detected_institution = models.CharField(max_length=200, blank=True)
    # Null when identity could not be checked at all (no matric number on the
    # document), which is different from checked-and-failed.
    #
    # Only the outcome is stored. The NRIC and any other identifier are
    # compared in memory and never written down -- recording them would put
    # the very data the private storage exists to protect into a database row.
    student_identity_matched = models.BooleanField(null=True, blank=True)

    # --- issuer verification (is it authentic?) --------------------------
    verification_status = models.CharField(
        max_length=20, choices=VerificationStatus.choices,
        default=VerificationStatus.PENDING)
    verification_method = models.CharField(
        max_length=20, choices=VerificationMethod.choices,
        default=VerificationMethod.NONE)
    reviewed_by = models.ForeignKey('accounts.AdminProfile', on_delete=models.SET_NULL,
                                    null=True, blank=True,
                                    related_name="reviewed_transcripts")
    reviewed_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)
    # Set once, when skills are actually written. Its presence is what makes
    # approval idempotent.
    skills_applied_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-uploaded_time"]

    @property
    def is_verified(self):
        return self.verification_status in self.VERIFIED_STATUSES

    def __str__(self):
        return (f"{self.student.student_name} — transcript "
                f"({self.status}/{self.verification_status})")


class TranscriptSkillEvidence(models.Model):
    """Which transcript created or upgraded which skill.

    Without this there is no way to answer "where did this skill come from",
    which is why the legacy migration cannot safely revoke skills applied
    before verification existed -- nothing records who granted them.

    Written when the upload applies the skills it read, at the moment
    skills are applied.
    """
    transcript  = models.ForeignKey(TranscriptUpload, on_delete=models.CASCADE,
                                    related_name="skill_evidence")
    skill       = models.ForeignKey(Skill, on_delete=models.CASCADE,
                                    related_name="transcript_evidence")
    skill_level = models.CharField(max_length=20)
    applied_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("transcript", "skill")
        ordering = ["-applied_at"]
        verbose_name_plural = "Transcript skill evidence"

    def __str__(self):
        return f"{self.transcript_id}: {self.skill.skill_name} = {self.skill_level}"


class TrainingProgramme(models.Model):
    class ApprovalStatus(models.TextChoices):
        PENDING  = 'PENDING',  'Pending'
        APPROVED = 'APPROVED', 'Approved'
        REJECTED = 'REJECTED', 'Rejected'

    company          = models.ForeignKey(Company, on_delete=models.CASCADE,
                                         related_name='training_programmes')
    admin            = models.ForeignKey(AdminProfile, on_delete=models.SET_NULL,
                                         null=True, blank=True,
                                         related_name='reviewed_programmes')
    skill            = models.ForeignKey(Skill, on_delete=models.SET_NULL,
                                         null=True, blank=True,
                                         related_name='training_programmes')
    skills           = models.ManyToManyField(
        Skill, through="TrainingProgrammeSkill",
        related_name="taught_by_programmes", blank=True)
    title            = models.CharField(max_length=255)
    description      = models.TextField(blank=True)
    programme_duration = models.CharField(max_length=100, blank=True)
    supporting_doc   = models.URLField(blank=True, null=True)
    approval_status  = models.CharField(max_length=10,
                                        choices=ApprovalStatus.choices,
                                        default=ApprovalStatus.PENDING)
    submission_time  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-submission_time']

    def __str__(self):
        return f"{self.title} by {self.company.company_name} ({self.approval_status})"

    def save(self, *args, **kwargs):
        """Sanitize before storing.

        ``description`` is written by a company and rendered with
        dangerouslySetInnerHTML on both the student resources page and the
        admin approvals panel -- so an unsanitized payload would run in the
        browser of the very administrator reviewing it.
        """
        self.description = sanitize_html(self.description)
        self.title = sanitize_text(self.title)
        super().save(*args, **kwargs)


class ResourceScrapeLog(models.Model):
    class Status(models.TextChoices):
        SUCCESS = "SUCCESS", "Success"
        PARTIAL = "PARTIAL", "Partial (some platforms failed)"
        FAILED  = "FAILED",  "Failed"

    started_at              = models.DateTimeField(auto_now_add=True)
    finished_at             = models.DateTimeField(null=True, blank=True)
    status                  = models.CharField(max_length=20, choices=Status.choices, default=Status.FAILED)
    platforms_scraped       = models.JSONField(default=list)
    resources_scraped       = models.IntegerField(default=0)
    resources_created       = models.IntegerField(default=0)
    resources_updated       = models.IntegerField(default=0)
    resources_deactivated   = models.IntegerField(default=0)
    error_message           = models.TextField(blank=True)

    class Meta:
        ordering = ["-started_at"]

    def __str__(self):
        finished = self.finished_at.strftime("%H:%M") if self.finished_at else "running"
        return f"[{self.status}] {self.started_at.strftime('%Y-%m-%d %H:%M')} → {finished} | +{self.resources_created} new"
