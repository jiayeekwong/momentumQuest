from django.db import models

from accounts.models import AdminProfile


class Announcement(models.Model):
    admin = models.ForeignKey(
        AdminProfile,
        on_delete=models.SET_NULL,
        null=True,
        related_name='announcements',
    )
    title = models.CharField(max_length=200)
    message = models.TextField()
    supporting_doc = models.URLField(blank=True, null=True)
    publish_time = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-publish_time']

    def __str__(self):
        return self.title
