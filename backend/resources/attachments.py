"""Files attached to a posting: where they are kept, and how they come back.

An announcement carries a poster and a training programme carries a brochure.
Both were written to MEDIA_ROOT, which is inside the container: nothing serves
it once DEBUG is off -- Django's static() helper is a no-op then, and WhiteNoise
only serves STATIC_ROOT -- and the deployment has no disk, so the file was
discarded whenever the container was replaced.

Both failures are silent. The upload answers 201 with a URL, the URL is stored
on the record, and whoever opens it gets "Not Found" from a server that never
had the file. The free-tier notes describe exactly this for certificates, which
is why those went to object storage; these two never did.

They are the same feature twice, so they share this. The announcement poster
was fixed first and alone, and the training brochure went on failing in the
same way for another day -- which is the argument for the shared module rather
than a second copy of it.

Served without a token. An <img> element cannot carry one, and these are
posters: the upload reads the file's type from its own bytes precisely because
the result is handed to anyone with the link, so an .html or .svg would run
script on this origin. The stored name is a UUID with the extension the
contents earned, and anything that is not one is refused before it is joined
onto a storage path.
"""

import os
import re
import uuid
from urllib.parse import unquote, urlsplit

from django.core import signing
from django.http import FileResponse, Http404
from django.urls import reverse
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from . import private_storage

#: What a stored name looks like: a UUID4 and the extension the file earned.
#: Anything else is not something these views wrote.
STORED_NAME = re.compile(r"^[0-9a-f]{32}\.[a-z0-9]{1,5}$")

CONTENT_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".pdf": "application/pdf",
}

TRAINING_ATTACHMENT_DIR = "training"
ANNOUNCEMENT_ATTACHMENT_DIR = "announcements"
ATTACHMENT_ROUTES = {
    TRAINING_ATTACHMENT_DIR: "training-attachment",
    ANNOUNCEMENT_ATTACHMENT_DIR: "announcement-attachment",
}

# Upload and record creation are separate requests.  This receipt is the
# ownership proof joining them without accepting a storage key from a client.
ATTACHMENT_RECEIPT_SALT = "mq-public-attachment-receipt"
ATTACHMENT_RECEIPT_MAX_AGE_SECONDS = 60 * 60


class InvalidAttachmentReceipt(Exception):
    pass


def store_attachment(directory, upload, extension):
    """Save an uploaded file and return the name it was stored under.

    The extension comes from the caller because it is the one the validator
    read from the file's own bytes, not the one on the client's filename.
    """
    name = f"{uuid.uuid4().hex}{extension}"
    private_storage.save(
        private_storage.build_relative_path(directory, name), upload.chunks())
    return name


def issue_attachment_receipt(user_id, directory, name):
    """Return short-lived proof that this user uploaded this stored object."""
    if directory not in ATTACHMENT_ROUTES or not STORED_NAME.fullmatch(name):
        raise ValueError("Refusing to issue a receipt for an unknown attachment")
    return signing.dumps(
        {"user_id": user_id, "directory": directory, "name": name},
        salt=ATTACHMENT_RECEIPT_SALT,
    )


def verify_attachment_receipt(token, user_id, directory):
    """Return ``(relative_path, name)`` for a valid upload owned by the user."""
    if not token:
        raise InvalidAttachmentReceipt("An attachment upload receipt is required.")
    try:
        payload = signing.loads(
            token,
            salt=ATTACHMENT_RECEIPT_SALT,
            max_age=ATTACHMENT_RECEIPT_MAX_AGE_SECONDS,
        )
    except signing.SignatureExpired:
        raise InvalidAttachmentReceipt(
            "This attachment upload has expired. Please upload the file again.")
    except signing.BadSignature:
        raise InvalidAttachmentReceipt("This attachment upload is not valid.")

    name = payload.get("name", "")
    if payload.get("user_id") != user_id or payload.get("directory") != directory:
        raise InvalidAttachmentReceipt(
            "This attachment upload belongs to another account or form.")
    if not STORED_NAME.fullmatch(name):
        raise InvalidAttachmentReceipt("This attachment upload is not valid.")

    path = private_storage.build_relative_path(directory, name)
    if not private_storage.exists(path):
        raise InvalidAttachmentReceipt(
            "This attachment is no longer available. Please upload it again.")
    return path, name


def build_attachment_url(request, directory, name):
    return request.build_absolute_uri(reverse(ATTACHMENT_ROUTES[directory], args=[name]))


def managed_attachment_name(url, directory):
    """Return a generated name when ``url`` points at one of our file routes."""
    if not url or directory not in ATTACHMENT_ROUTES:
        return None
    path = unquote(urlsplit(url).path)
    marker = (
        "/resources/training/attachment/"
        if directory == TRAINING_ATTACHMENT_DIR
        else "/dashboard/announcements/attachment/"
    )
    if marker not in path:
        return None
    name = path.rsplit("/", 1)[-1]
    return name if STORED_NAME.fullmatch(name) else None


class StoredAttachmentView(APIView):
    """Serves one directory of stored attachments. Subclass and set `directory`."""

    directory = None
    permission_classes = [AllowAny]

    def get(self, request, name):
        if not STORED_NAME.match(name):
            raise Http404("No such attachment.")

        stream = private_storage.open_stored(
            private_storage.build_relative_path(self.directory, name))
        if stream is None:
            raise Http404("No such attachment.")

        extension = os.path.splitext(name)[1].lower()
        return FileResponse(
            stream,
            content_type=CONTENT_TYPES.get(extension, "application/octet-stream"),
        )
