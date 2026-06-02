from django.db import models

from accounts.models import AdminProfile


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

    def __str__(self):
        return self.title
