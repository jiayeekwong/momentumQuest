"""Delete an announcement's uploaded file with the database row."""

from django.db import transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver
from resources import private_storage

from .models import Announcement


@receiver(post_delete, sender=Announcement)
def delete_announcement_attachment(sender, instance, **kwargs):
    if instance.attachment_path:
        path = instance.attachment_path
        transaction.on_commit(lambda path=path: private_storage.delete(path))
