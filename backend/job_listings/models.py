from django.core.exceptions import ValidationError
from django.db import models

from config.sanitization import sanitize_html, sanitize_text

from accounts.models import Company, Student, StudentSkill
from scrape_jobs.models import JobCategory, JobTitle, Skill


class JobListing(models.Model):
    class Status(models.TextChoices):
        ACTIVE = 'ACTIVE', 'Active'
        CLOSED = 'CLOSED', 'Closed'
        DRAFT  = 'DRAFT',  'Draft'

    class SourceType(models.TextChoices):
        COMPANY = 'COMPANY', 'Company-posted'
        SCRAPED = 'SCRAPED', 'Scraped'

    class ClassificationMethod(models.TextChoices):
        """How an advert reached its Market Role, most direct evidence first.

        Kept on every advert because a skill profile built from a role is only
        as trustworthy as the classifications underneath it, and a reviewer
        must be able to see which tier produced each one.
        """
        EXACT_MARKET_ROLE = 'EXACT_MARKET_ROLE', 'Title is the Market Role'
        REVIEWED_TITLE_ALIAS = 'REVIEWED_TITLE_ALIAS', 'Reviewed title alias'
        CAREER_LEVEL_NORMALIZED_ROLE = ('CAREER_LEVEL_NORMALIZED_ROLE',
                                        'Market Role after career level removed')
        CAREER_LEVEL_NORMALIZED_ALIAS = ('CAREER_LEVEL_NORMALIZED_ALIAS',
                                         'Reviewed alias after career level removed')
        REVIEWED_SEGMENT_MATCH = 'REVIEWED_SEGMENT_MATCH', 'Reviewed segment of a compound title'
        JD_RESOLVED = 'JD_RESOLVED', 'Resolved from advert responsibilities'
        AMBIGUOUS = 'AMBIGUOUS', 'Evidence names more than one Market Role'
        UNCLASSIFIED = 'UNCLASSIFIED', 'No sufficient evidence'

    # company is null for scraped jobs (they have no MomentumQuest account)
    company          = models.ForeignKey(Company, on_delete=models.CASCADE,
                                         null=True, blank=True,
                                         related_name='job_listings')
    category         = models.ForeignKey(JobCategory, on_delete=models.SET_NULL,
                                         null=True, blank=True,
                                         related_name='job_listings')
    job_title        = models.CharField(max_length=255)
    job_title_ref    = models.ForeignKey(JobTitle, on_delete=models.SET_NULL,
                                         null=True, blank=True,
                                         related_name='job_listings')
    # job_title is the Raw Job Title: always the original employer/scraper
    # value. Everything below is a per-listing classification result derived
    # from it and never replaces it.
    #
    #   Raw Job Title        job_title              "Senior Front-End Engineer (Remote)"
    #   Normalized Job Title normalized_job_title   "frontend engineer"
    #   Market Role          market_role            Frontend Developer
    #
    # The middle value is matching evidence, kept so a classification can be
    # explained and so the same normalization is never recomputed differently
    # by two callers.
    normalized_job_title = models.CharField(max_length=250, blank=True,
                                            db_index=True)
    # The standardized career group this advert belongs to. Null until the
    # classifier can say so from title or advert evidence -- an unclassified
    # advert is a valid outcome and is never guessed at.
    market_role = models.ForeignKey(
        'scrape_jobs.MarketRole',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='job_listings',
    )
    # Genuine career level read off the title ("Senior", "Graduate"), kept
    # apart from occupational function: "IT Manager" is a function, not a
    # level, and is never reduced.
    career_level = models.CharField(max_length=30, blank=True)
    # Which tier produced the assignment. Every classified advert keeps this
    # so "why is this advert here?" is answerable from the row alone.
    # Rank, kept apart from the role. "Senior Software Engineer" and
    # "Junior Software Engineer" are one occupation at two levels; storing the
    # rank in market_role would split that career's demand across two rows and
    # make both look half as sought-after as they are.
    seniority_level  = models.CharField(
        max_length=12,
        choices=[('CHIEF', 'Chief'), ('SENIOR', 'Senior'),
                 ('ASSOCIATE', 'Associate'), ('JUNIOR', 'Junior'),
                 ('ENTRY', 'Entry')],
        blank=True, db_default='', db_index=True)
    classification_method = models.CharField(
        max_length=30,
        choices=ClassificationMethod.choices,
        default=ClassificationMethod.UNCLASSIFIED,
        db_index=True,
    )
    # The alias or segment the title matched on, or the advert evidence that
    # justified a JD_RESOLVED assignment.
    matched_alias = models.CharField(max_length=250, blank=True)
    classification_evidence = models.TextField(blank=True)
    classified_time = models.DateTimeField(null=True, blank=True)
    description      = models.TextField(blank=True)
    salary_min       = models.DecimalField(max_digits=10, decimal_places=2,
                                           null=True, blank=True)
    salary_max       = models.DecimalField(max_digits=10, decimal_places=2,
                                           null=True, blank=True)
    work_mode        = models.CharField(max_length=50, blank=True)
    experience_level = models.CharField(max_length=50, blank=True)
    closing_date     = models.DateField(null=True, blank=True)
    status           = models.CharField(max_length=10, choices=Status.choices,
                                        default=Status.ACTIVE)
    posted_time      = models.DateTimeField(auto_now_add=True)

    # Source discrimination + scraped-job fields (merged from ScrapedJob)
    source_type      = models.CharField(max_length=10, choices=SourceType.choices,
                                        default=SourceType.COMPANY)
    source_url       = models.URLField(null=True, blank=True, unique=True)
    source_portal    = models.CharField(max_length=100, blank=True)
    company_name     = models.CharField(max_length=255, blank=True)
    location         = models.CharField(max_length=255, blank=True)
    job_type         = models.CharField(max_length=100, blank=True)
    salary_text      = models.CharField(max_length=100, blank=True)
    posted_date      = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ['-posted_time']

    def __str__(self):
        employer = self.company.company_name if self.company else (self.company_name or "External")
        return f"{self.job_title} @ {employer}"

    def save(self, *args, **kwargs):
        """Sanitize before storing, for every writer.

        ``description`` is rendered with dangerouslySetInnerHTML on the
        student jobs page, and it arrives from two untrusted sources: a
        company filling in a form, and a scraper copying an employer's HTML
        off JobStreet. Sanitizing here rather than in one serializer means the
        guarantee holds for the scraper and for a shell session too.

        The title and company name are stripped of markup entirely -- neither
        has any reason to carry it, and both are interpolated into headings.
        """
        self.description = sanitize_html(self.description)
        self.job_title = sanitize_text(self.job_title)
        self.company_name = sanitize_text(self.company_name)
        super().save(*args, **kwargs)


class JobSkill(models.Model):
    class ImportanceLevel(models.TextChoices):
        HIGH   = 'HIGH',   'High'
        MEDIUM = 'MEDIUM', 'Medium'
        LOW    = 'LOW',    'Low'

    class MatchMethod(models.TextChoices):
        DIRECT_CANONICAL = 'DIRECT_CANONICAL', 'Canonical name matched'
        ALIAS = 'ALIAS', 'Alias matched'
        CONTEXTUAL_ALIAS = 'CONTEXTUAL_ALIAS', 'Alias matched, context checked'
        MANUAL = 'MANUAL', 'Entered by hand'

    job              = models.ForeignKey(JobListing, on_delete=models.CASCADE,
                                         related_name='job_skills')
    skill            = models.ForeignKey(Skill, on_delete=models.CASCADE,
                                         related_name='job_skills')
    # How this link came to exist. "Why is this advert tagged with Go?" is a
    # question that keeps being asked, and without the matched string the only
    # answer is to re-run the extractor and hope it behaves the same way.
    matched_text     = models.CharField(max_length=120, blank=True,
                                        db_default='')
    match_method     = models.CharField(max_length=20,
                                        choices=MatchMethod.choices,
                                        blank=True, db_default='')
    importance_level = models.CharField(max_length=10,
                                        choices=ImportanceLevel.choices,
                                        default=ImportanceLevel.MEDIUM)
    # The proficiency the advert asks for, which the match score weighs against
    # StudentSkill.skill_level. Deliberately separate from importance_level:
    # how much a skill matters to the role and how good you have to be at it
    # are different questions, and an advert can want a beginner-level grasp of
    # something critical.
    #
    # Choices come from StudentSkill so the two sides of the comparison cannot
    # drift apart. INTERMEDIATE is the default because a scraped advert states
    # no level -- assuming ADVANCED would understate every student's match and
    # assuming BEGINNER would make the score meaningless.
    required_level   = models.CharField(max_length=20,
                                        choices=StudentSkill.SkillLevel.choices,
                                        default=StudentSkill.SkillLevel.INTERMEDIATE)

    class Meta:
        unique_together = ('job', 'skill')

    def __str__(self):
        return f"{self.job.job_title} — {self.skill.skill_name} ({self.importance_level})"


class MarketRoleCandidate(models.Model):
    """A suggested advert-to-Market-Role link that must be reviewed to count.

    Two things land here. A title naming two different careers -- "Junior Data
    Engineer / Data Analyst" -- is an advert for two jobs, where choosing one
    would be a coin flip. And a ranked suggestion from a similarity measure is
    a hint for a reviewer, never a classification: string or vector similarity
    may propose a Market Role but must never assign one, because "Security
    Specialist" scoring highest against six security roles is not evidence.

    Neither may write JobListing.market_role directly, so both wait for a
    person. Approving one is what turns it into a reviewed alias.

    Lives in job_listings rather than scrape_jobs because it points at
    JobListing; the app dependency runs job_listings -> scrape_jobs and must
    not be reversed.
    """

    class Source(models.TextChoices):
        AMBIGUOUS_TITLE = 'AMBIGUOUS_TITLE', 'Title names more than one Market Role'
        DESCRIPTION = 'DESCRIPTION', 'Suggested by advert description'
        SIMILARITY = 'SIMILARITY', 'Suggested by lexical similarity (review only)'

    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending review'
        APPROVED = 'APPROVED', 'Approved'
        REJECTED = 'REJECTED', 'Rejected'

    listing = models.ForeignKey(JobListing, on_delete=models.CASCADE,
                                related_name='role_candidates')
    market_role = models.ForeignKey('scrape_jobs.MarketRole',
                                    on_delete=models.CASCADE,
                                    related_name='listing_candidates')
    source = models.CharField(max_length=20, choices=Source.choices)
    confidence = models.DecimalField(max_digits=5, decimal_places=4,
                                     null=True, blank=True)
    # The matched wording, so a reviewer can judge at a glance instead of
    # reading a 2,791-character advert.
    evidence_excerpt = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=Status.choices,
                              default=Status.PENDING)
    created_time = models.DateTimeField(auto_now_add=True)
    reviewed_time = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ('listing', 'market_role', 'source')
        ordering = ['status', '-confidence', 'listing_id']

    def __str__(self):
        return f"{self.listing.job_title} -> {self.market_role.name} [{self.source}]"


class SavedJob(models.Model):
    """A job a student bookmarked to come back to.

    Deliberately not an application and deliberately not a target: saving is
    a private shortlist, visible to nobody but the student, and it commits
    them to nothing. Employers are never told a listing was saved.

    Scraped listings lapse after about 30 days, so a saved one can end up
    pointing at a closed advert. The row is kept anyway and the listing's own
    status is what the page reports -- silently dropping a saved job would
    look like the bookmark had failed.
    """

    student    = models.ForeignKey(Student, on_delete=models.CASCADE,
                                   related_name='saved_jobs')
    job        = models.ForeignKey(JobListing, on_delete=models.CASCADE,
                                   related_name='saved_by')
    saved_time = models.DateTimeField(auto_now_add=True)

    class Meta:
        # Saving twice is the same as saving once; the endpoint is idempotent
        # and the constraint is what makes that true under a double-click.
        unique_together = ('student', 'job')
        ordering = ['-saved_time']

    def __str__(self):
        return f"{self.student.student_name} saved {self.job.job_title}"


class JobApplication(models.Model):
    class Status(models.TextChoices):
        PENDING     = 'PENDING',     'Pending'
        REVIEWED    = 'REVIEWED',    'Reviewed'
        SHORTLISTED = 'SHORTLISTED', 'Shortlisted'
        ACCEPTED    = 'ACCEPTED',    'Accepted'
        REJECTED    = 'REJECTED',    'Rejected'

    student      = models.ForeignKey(Student, on_delete=models.CASCADE,
                                     related_name='job_applications')
    job          = models.ForeignKey(JobListing, on_delete=models.CASCADE,
                                     related_name='applications')
    # What the applicant presented, frozen at the moment of applying.
    #
    # A snapshot rather than a live read of the profile: an employer reviewing
    # an application weeks later must see what was submitted, not what the
    # student has since edited. Reading student_skills live also meant adding
    # a skill silently re-scored every application already sent.
    #
    # Plain JSON, not foreign keys, precisely so nothing downstream can change
    # it. Shape:
    #   {"skills": [{"skill_id", "skill_name", "skill_level"}],
    #    "education": [str], "experience": [str], "captured_at": iso8601}
    applicant_snapshot = models.JSONField(default=dict, blank=True)
    # Legacy. CVs are no longer stored: they are parsed once and deleted, and
    # only the confirmed structured result is kept. Retained so existing rows
    # keep their value; nothing writes it any more.
    cv_url       = models.URLField(blank=True)
    status       = models.CharField(max_length=15, choices=Status.choices,
                                    default=Status.PENDING)
    applied_time = models.DateTimeField(auto_now_add=True)
    # Whether the *employer* has opened this application. Not a student-facing
    # read flag, despite the name.
    is_read      = models.BooleanField(default=False)
    # When the employer last changed the status. applied_time cannot stand in
    # for it: an application submitted in March and shortlisted in June would
    # otherwise be announced to the student as March news.
    status_changed_at = models.DateTimeField(null=True, blank=True)

    # Application-form answers (company-posted jobs)
    needs_work_permit = models.BooleanField(null=True, blank=True)
    available_from    = models.DateField(null=True, blank=True)
    phone             = models.CharField(max_length=30, blank=True)
    cover_note        = models.TextField(blank=True)

    # The two consent records behind this application.
    #
    # cv_processing_consent points at the CV_PARSE consent whose receipt was
    # presented at submission; disclosure_consent at the acknowledgement
    # written when Submit was pressed. Both nullable because applications
    # submitted before consent was recorded legitimately have neither, and
    # inventing a row for them would fabricate evidence.
    #
    # SET_NULL, not CASCADE: deleting a consent record must never silently
    # delete the application it authorised.
    cv_processing_consent = models.ForeignKey(
        'accounts.UserConsent', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='cv_applications')
    disclosure_consent = models.ForeignKey(
        'accounts.UserConsent', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='disclosure_applications')

    class Meta:
        unique_together = ('student', 'job')
        ordering = ['-applied_time']

    def __str__(self):
        return f"{self.student.student_name} → {self.job.job_title} ({self.status})"


class ScrapeLog(models.Model):
    """Audit record of a job-scraping run (moved here from the scrape_jobs app)."""
    class Status(models.TextChoices):
        SUCCESS = "SUCCESS", "Success"
        BLOCKED = "BLOCKED", "Blocked by Anti-Bot"
        PARTIAL = "PARTIAL", "Partial (some pages blocked)"
        FAILED  = "FAILED",  "Failed"

    started_at     = models.DateTimeField(auto_now_add=True)
    finished_at    = models.DateTimeField(null=True, blank=True)
    status         = models.CharField(max_length=20, choices=Status.choices, default=Status.FAILED)
    roles_scraped  = models.JSONField(default=list)
    pages_attempted = models.IntegerField(default=0)
    jobs_scraped   = models.IntegerField(default=0)
    jobs_created   = models.IntegerField(default=0)
    jobs_updated   = models.IntegerField(default=0)
    blocked_count  = models.IntegerField(default=0)
    error_message  = models.TextField(blank=True)

    class Meta:
        ordering = ["-started_at"]

    def __str__(self):
        finished = self.finished_at.strftime("%H:%M") if self.finished_at else "running"
        return f"[{self.status}] {self.started_at.strftime('%Y-%m-%d %H:%M')} → {finished} | +{self.jobs_created} new"
