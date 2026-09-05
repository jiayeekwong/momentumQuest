from django.db import models
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.utils import timezone


class UserManager(BaseUserManager):
    def create_user(self, email, password=None, role='STUDENT', **extra_fields):
        if not email:
            raise ValueError('Email is required')

        email = self.normalize_email(email)
        user = self.model(email=email, role=role, **extra_fields)
        user.set_password(password)  # Hashes the password before saving
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('email_verified', True)
        extra_fields.setdefault('is_active', True)

        return self.create_user(
            email=email,
            password=password,
            role='ADMIN',
            **extra_fields
        )


class User(AbstractBaseUser, PermissionsMixin):
    class Role(models.TextChoices):
        STUDENT = 'STUDENT', 'Student'
        COMPANY = 'COMPANY', 'Company'
        ADMIN = 'ADMIN', 'Admin'

    email = models.EmailField(unique=True)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.STUDENT)
    created_time = models.DateTimeField(default=timezone.now)
    email_verified = models.BooleanField(default=False)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    def __str__(self):
        return self.email


class Student(models.Model):
    student_id = models.AutoField(primary_key=True)
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='student_profile')
    student_name = models.CharField(max_length=100)
    department = models.CharField(max_length=100, blank=True)
    # University enrolment number, shown to an admin verifying a document so
    # they can tell which student a submission belongs to. Deliberately NOT an
    # identity-document number: MomentumQuest stores no NRIC/MyKad or passport
    # number in any field -- see docs/reference/privacy-consent-design.md.
    matric_number = models.CharField(max_length=30, blank=True)

    def __str__(self):
        return self.student_name


class Company(models.Model):
    company_id = models.AutoField(primary_key=True)
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='company_profile')
    company_name = models.CharField(max_length=100)

    def __str__(self):
        return self.company_name


class AdminProfile(models.Model):
    admin_id = models.AutoField(primary_key=True)
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='admin_profile')
    admin_name = models.CharField(max_length=100)

    def __str__(self):
        return self.admin_name


class StudentTargetRole(models.Model):
    """The Market Role a student is aiming for.

    A Market Role is a standardized career group derived from what Malaysian
    ICT employers actually advertise -- "Frontend Developer", not the raw
    advert "Senior Front-End Engineer (Remote)" and not the normalized
    matching key "frontend engineer". Students name careers, so the target is
    a Market Role and everything else derives from it: the Broad Area used to
    group and to widen a thin analysis comes from the role.

    A foreign key rather than a stored name, because Market Role names are
    unique by construction -- there is exactly one "Data Analyst" -- so
    nothing needs to be recorded alongside it to say which one was meant.

    Every role is targetable even when the market cannot yet support
    analysing it; whether a role clears the evidence floor is a separate
    question, answered at analysis time.
    """
    student     = models.ForeignKey(Student, on_delete=models.CASCADE,
                                    related_name='target_roles')
    market_role = models.ForeignKey('scrape_jobs.MarketRole',
                                    on_delete=models.CASCADE,
                                    related_name='targeting_students')
    added_time  = models.DateTimeField(default=timezone.now)

    class Meta:
        unique_together = ('student', 'market_role')
        ordering = ['added_time', 'id']

    def __str__(self):
        return f"{self.student.student_name} -> {self.market_role.name}"



class RoleTerminologyFeedback(models.Model):
    """What a student searched for when no Market Role matched.

    The picker offers a reviewed set of Market Roles rather than every raw
    market title, which is deliberate: a Raw Job Title carries employer
    career level, technologies and org wording that a career name should not.
    But that means a student can look for wording no Market Role uses, and
    silently failing to find it teaches nobody anything.

    This records the wording only. It never creates a role, never writes a
    StudentTargetRole, and is not a target of any kind -- an "Other" role
    would have no adverts and no skills behind it, so the vocabulary gap is
    captured as data instead of papered over with a synthetic entry.

    Read alongside selected-but-unanalysable roles to order the review queue:
    together they say which careers students actually want, and in which
    words -- which is exactly the evidence for adding a reviewed alias or
    proposing a new Market Role.
    """
    student       = models.ForeignKey(Student, on_delete=models.CASCADE,
                                      related_name='role_terminology_feedback')
    searched_text = models.CharField(max_length=200)
    # The Broad Area they were browsing when they gave up, when there was one.
    context_broad_area = models.CharField(max_length=80, blank=True)
    created_time  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_time']
        verbose_name_plural = 'Role terminology feedback'

    def __str__(self):
        return f"{self.student.student_name} looked for '{self.searched_text}'"


class SkillGap(models.Model):
    """One recorded gap between a student's skills and a target's demand.

    The live analysis in ``dashboard.build_skill_gap`` stays authoritative for
    what the student sees today. This table is a point-in-time record, kept so
    the system can answer what a live computation cannot: whether a student is
    closing gaps over time. Rows are never deleted when a gap is met -- they
    are marked CLOSED with a timestamp, which is what makes progress visible.

    ``target`` is a StudentTargetRole because a gap is only meaningful relative
    to something the student is aiming at; the same missing skill is critical
    for one target and irrelevant for another.
    """

    class Priority(models.TextChoices):
        HIGH   = 'HIGH',   'High'
        MEDIUM = 'MEDIUM', 'Medium'
        LOW    = 'LOW',    'Low'

    class Status(models.TextChoices):
        OPEN   = 'OPEN',   'Open'
        CLOSED = 'CLOSED', 'Closed'

    student           = models.ForeignKey(Student, on_delete=models.CASCADE,
                                          related_name='skill_gaps')
    skill             = models.ForeignKey('scrape_jobs.Skill', on_delete=models.CASCADE,
                                          related_name='skill_gaps')
    target            = models.ForeignKey(StudentTargetRole, on_delete=models.CASCADE,
                                          related_name='skill_gaps')
    # Share of the target's listings asking for this skill, as measured when
    # the row was last refreshed. Stored rather than recomputed so a historical
    # row still reports the demand that justified it at the time.
    demand_percentage = models.DecimalField(max_digits=5, decimal_places=1, default=0)
    priority_level    = models.CharField(max_length=10, choices=Priority.choices,
                                         default=Priority.LOW)
    status            = models.CharField(max_length=10, choices=Status.choices,
                                         default=Status.OPEN)
    identified_time   = models.DateTimeField(auto_now_add=True)
    updated_time      = models.DateTimeField(auto_now=True)
    closed_time       = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ('student', 'skill', 'target')
        ordering = ['status', '-demand_percentage', 'skill__skill_name']

    def __str__(self):
        return (f"{self.student.student_name} needs {self.skill.skill_name} "
                f"for {self.target.market_role.name} ({self.status})")




class StudentSkill(models.Model):
    class SkillLevel(models.TextChoices):
        BEGINNER     = 'BEGINNER',     'Beginner'
        INTERMEDIATE = 'INTERMEDIATE', 'Intermediate'
        ADVANCED     = 'ADVANCED',     'Advanced'

    student     = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='student_skills')
    skill       = models.ForeignKey('scrape_jobs.Skill', on_delete=models.CASCADE, related_name='student_skills')
    skill_level = models.CharField(max_length=20, choices=SkillLevel.choices, default=SkillLevel.BEGINNER)

    class Meta:
        unique_together = ('student', 'skill')

    def __str__(self):
        return f"{self.student.student_name} — {self.skill.skill_name} ({self.skill_level})"


class UserConsent(models.Model):
    """Evidence that a user agreed to a specific version of the privacy notice.

    Deliberately append-only: there is no unique constraint on
    (user, consent_type), because a consent record is a historical fact rather
    than a current setting. A student who accepts notice v1.0 at signup and
    v1.1 a year later must leave two rows behind, and every certificate upload
    records its own fresh consent -- rewriting the earlier row would destroy
    the only proof of what was actually agreed to, and when.

    Storing ``consent = true`` alone would be worthless; what makes the record
    usable is the pairing of notice_version with accepted_at.
    """

    class ConsentType(models.TextChoices):
        PRIVACY_NOTICE_ACKNOWLEDGEMENT = ('PRIVACY_NOTICE_ACKNOWLEDGEMENT',
                                          'Privacy notice acknowledgement')
        DOCUMENT_VERIFICATION_CONSENT = ('DOCUMENT_VERIFICATION_CONSENT',
                                         'Document verification consent')
        # Reading a CV to pre-fill an application. Separate from document
        # verification because the purpose and the outcome differ: a
        # certificate is stored and reviewed, a CV is read once and deleted.
        CV_PROCESSING_CONSENT = ('CV_PROCESSING_CONSENT',
                                 'CV processing consent')
        # Recorded when an application is submitted. An acknowledgement rather
        # than a consent: the student's affirmative act is pressing Submit,
        # and the sentence above that button is what they are acknowledging.
        APPLICATION_DISCLOSURE_ACKNOWLEDGEMENT = (
            'APPLICATION_DISCLOSURE_ACKNOWLEDGEMENT',
            'Application disclosure acknowledgement')

    class Source(models.TextChoices):
        SIGNUP = 'SIGNUP', 'Signup'
        CERTIFICATE_UPLOAD = 'CERTIFICATE_UPLOAD', 'Certificate upload'
        TRANSCRIPT_UPLOAD = 'TRANSCRIPT_UPLOAD', 'Transcript upload'
        CV_PARSE = 'CV_PARSE', 'CV parsing'
        JOB_APPLICATION = 'JOB_APPLICATION', 'Job application'
        # Accounts that existed before the privacy notice did. These rows carry
        # accepted=False: they record that the account predates the notice, not
        # that consent was given. Writing accepted=True here would manufacture
        # the very agreement this table exists to prove.
        BACKFILL_PRE_NOTICE = 'BACKFILL_PRE_NOTICE', 'Backfilled (pre-notice account)'
        # Given again, from Settings, after a withdrawal. A new row rather
        # than a flag cleared on the old one: the withdrawal happened, and
        # editing it away would destroy the record of a decision the student
        # actually made.
        SETTINGS_RESTORE = 'SETTINGS_RESTORE', 'Restored in settings'

    @property
    def is_live(self):
        """Whether this consent still authorises processing.

        Withdrawal never deletes the row -- the record of what was agreed to,
        and when, has to survive. It stops the consent authorising anything
        further from that moment on.
        """
        return self.accepted and self.withdrawn_at is None

    user           = models.ForeignKey(User, on_delete=models.CASCADE,
                                       related_name='consents')
    consent_type   = models.CharField(max_length=40, choices=ConsentType.choices)
    notice_version = models.CharField(max_length=20)
    accepted       = models.BooleanField(default=False)
    accepted_at    = models.DateTimeField(null=True, blank=True)
    withdrawn_at   = models.DateTimeField(null=True, blank=True)
    source         = models.CharField(max_length=30, choices=Source.choices)
    created_at     = models.DateTimeField(auto_now_add=True)
    updated_at     = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'consent_type', '-created_at'],
                         name='consent_user_type_recent'),
        ]

    def __str__(self):
        state = 'accepted' if self.accepted else 'not accepted'
        return f"{self.user.email} — {self.consent_type} v{self.notice_version} ({state})"


class PrivacyAuditLog(models.Model):
    """Append-only record of who touched identity-bearing documents, and when.

    There is deliberately no free-text detail column. Uploaded certificates and
    examination results carry NRIC/MyKad and passport numbers, and any open
    text field on this table would eventually be filled with something copied
    out of one. The schema removes the possibility rather than relying on every
    future call site to remember -- the log records *that* an action happened,
    never the document's contents.
    """

    class Action(models.TextChoices):
        CERTIFICATE_UPLOADED       = 'CERTIFICATE_UPLOADED',       'Certificate uploaded'
        CERTIFICATE_VIEWED_BY_ADMIN = 'CERTIFICATE_VIEWED_BY_ADMIN', 'Certificate viewed by admin'
        CERTIFICATE_VERIFIED       = 'CERTIFICATE_VERIFIED',       'Certificate verified'
        CERTIFICATE_REJECTED       = 'CERTIFICATE_REJECTED',       'Certificate rejected'
        CERTIFICATE_DELETED        = 'CERTIFICATE_DELETED',        'Certificate deleted'
        # A transcript is an examination result, and the document most likely
        # to show an NRIC, so its handling is logged on the same footing.
        TRANSCRIPT_UPLOADED        = 'TRANSCRIPT_UPLOADED',        'Transcript uploaded'
        TRANSCRIPT_VIEWED_BY_ADMIN = 'TRANSCRIPT_VIEWED_BY_ADMIN', 'Transcript viewed by admin'
        # Verification is the act that lets a transcript change a student's
        # skills, so approving and rejecting are both recorded.
        TRANSCRIPT_VERIFIED        = 'TRANSCRIPT_VERIFIED',        'Transcript verified'
        TRANSCRIPT_REJECTED        = 'TRANSCRIPT_REJECTED',        'Transcript rejected'
        CONSENT_ACCEPTED           = 'CONSENT_ACCEPTED',           'Consent accepted'
        CONSENT_WITHDRAWN          = 'CONSENT_WITHDRAWN',          'Consent withdrawn'

    class ResourceType(models.TextChoices):
        CERTIFICATE = 'CERTIFICATE', 'Certificate'
        TRANSCRIPT  = 'TRANSCRIPT',  'Transcript'
        CONSENT     = 'CONSENT',     'Consent'

    # SET_NULL on both sides: deleting an account must not erase the record
    # that its documents were once reviewed.
    actor_user    = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                      related_name='privacy_actions')
    target_user   = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                      related_name='privacy_events')
    action        = models.CharField(max_length=40, choices=Action.choices)
    resource_type = models.CharField(max_length=20, choices=ResourceType.choices,
                                     default=ResourceType.CERTIFICATE)
    resource_id   = models.PositiveIntegerField(null=True, blank=True)
    timestamp     = models.DateTimeField(auto_now_add=True, db_index=True)
    ip_address    = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['target_user', '-timestamp'], name='audit_target_recent'),
            models.Index(fields=['resource_type', 'resource_id'], name='audit_resource'),
        ]

    def __str__(self):
        actor = self.actor_user.email if self.actor_user else 'deleted user'
        return f"{self.timestamp:%Y-%m-%d %H:%M} {actor} {self.action} #{self.resource_id}"
