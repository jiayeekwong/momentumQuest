"""Remove a retained CV after the application that owns it is deleted."""

from django.db import transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver
from resources import private_storage

from .models import JobApplication


@receiver(post_delete, sender=JobApplication)
def delete_application_cv(sender, instance, **kwargs):
    if not instance.cv_path:
        return

    # Storage cannot join the database transaction.  Waiting for commit avoids
    # deleting the bytes if a surrounding cascade is rolled back.
    path = instance.cv_path
    transaction.on_commit(lambda path=path: private_storage.delete(path))
