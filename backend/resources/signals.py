"""Retention enforcement for privately stored documents.

The privacy notice states that uploaded certificates, examination results and
transcripts are kept only while the account is active, and are removed when it
is deleted. Deleting a row does not delete the bytes it points at, so without
these receivers the promise would be prose the code contradicts -- the files
would sit in private_media indefinitely.

Deleting a User cascades to Student and then to Certificate and
TranscriptUpload, so account deletion reaches here on its own.
"""

import logging
import os

from django.db.models.signals import post_delete
from django.dispatch import receiver

from . import private_storage
from .models import Certificate, TranscriptUpload

logger = logging.getLogger(__name__)


def _delete_private_file(relative_path):
    """Remove one file from PRIVATE_MEDIA_ROOT as part of retention cleanup.

    The containment check, the already-gone case and the never-raise contract
    all live in private_storage.delete, which the failed-upload paths use too
    -- a document must be removed the same way whichever route removes it.
    """
    private_storage.delete(relative_path)


@receiver(post_delete, sender=Certificate)
def delete_certificate_file(sender, instance, **kwargs):
    _delete_private_file(instance.file_path)


@receiver(post_delete, sender=TranscriptUpload)
def delete_transcript_file(sender, instance, **kwargs):
    _delete_private_file(instance.file_path)
