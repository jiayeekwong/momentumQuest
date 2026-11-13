from django.db import models
from django.utils import timezone

from accounts.models import AdminProfile
from config.sanitization import sanitize_html, sanitize_text


class Announcement(models.Model):
    class AudienceChoice(models.TextChoices):
        EVERYONE  = 'EVERYONE',  'Everyone'
        STUDENTS  = 'STUDENTS',  'Students Only'
        COMPANIES = 'COMPANIES', 'Companies Only'

    class ApprovalStatus(models.TextChoices):
        PENDING = 'PENDING', 'Pending review'
        APPROVED = 'APPROVED', 'Approved'
        REJECTED = 'REJECTED', 'Rejected'
        WITHDRAWN = 'WITHDRAWN', 'Withdrawn'

    admin = models.ForeignKey(
        AdminProfile,
        on_delete=models.SET_NULL,
        null=True,
        related_name='announcements',
    )
    submitted_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='submitted_announcements')
    reviewed_by = models.ForeignKey(
        AdminProfile, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='reviewed_announcements')
    title          = models.CharField(max_length=200)
    message        = models.TextField()
    categories     = models.JSONField(default=list, blank=True)
    audience       = models.CharField(
        max_length=10,
        choices=AudienceChoice.choices,
        default=AudienceChoice.EVERYONE,
    )
    supporting_doc = models.URLField(blank=True, null=True)
    attachment_path = models.CharField(
        max_length=255, blank=True, null=True, unique=True, editable=False)
    approval_status = models.CharField(
        max_length=10, choices=ApprovalStatus.choices,
        default=ApprovalStatus.APPROVED, db_index=True)
    rejection_reason = models.TextField(blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    publish_time = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        ordering = ['-submitted_at']

    def save(self, *args, **kwargs):
        """Sanitize before storing.

        ``message`` is rendered with dangerouslySetInnerHTML on the student,
        company and admin dashboards. An administrator account is the most
        valuable one to compromise, so the content it authors is sanitized on
        the same terms as everyone else's.
        """
        self.message = sanitize_html(self.message)
        self.title = sanitize_text(self.title)
        # Preserve the original model-level contract: announcements created by
        # trusted admin code are published immediately unless a workflow
        # explicitly marks them pending. Company endpoints always do so.
        if (self.approval_status == self.ApprovalStatus.APPROVED
                and self.publish_time is None):
            self.publish_time = timezone.now()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title
