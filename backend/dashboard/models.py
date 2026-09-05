from django.db import models

from accounts.models import AdminProfile
from config.sanitization import sanitize_html, sanitize_text


class Announcement(models.Model):
    class AudienceChoice(models.TextChoices):
        EVERYONE  = 'EVERYONE',  'Everyone'
        STUDENTS  = 'STUDENTS',  'Students Only'
        COMPANIES = 'COMPANIES', 'Companies Only'

    admin = models.ForeignKey(
        AdminProfile,
        on_delete=models.SET_NULL,
        null=True,
        related_name='announcements',
    )
    title          = models.CharField(max_length=200)
    message        = models.TextField()
    categories     = models.JSONField(default=list, blank=True)
    audience       = models.CharField(
        max_length=10,
        choices=AudienceChoice.choices,
        default=AudienceChoice.EVERYONE,
    )
    supporting_doc = models.URLField(blank=True, null=True)
    publish_time   = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-publish_time']

    def save(self, *args, **kwargs):
        """Sanitize before storing.

        ``message`` is rendered with dangerouslySetInnerHTML on the student,
        company and admin dashboards. An administrator account is the most
        valuable one to compromise, so the content it authors is sanitized on
        the same terms as everyone else's.
        """
        self.message = sanitize_html(self.message)
        self.title = sanitize_text(self.title)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title
