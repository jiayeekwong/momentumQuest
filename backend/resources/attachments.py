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

from rest_framework.permissions import AllowAny
from rest_framework.views import APIView
from django.http import FileResponse, Http404

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


def store_attachment(directory, upload, extension):
    """Save an uploaded file and return the name it was stored under.

    The extension comes from the caller because it is the one the validator
    read from the file's own bytes, not the one on the client's filename.
    """
    name = f"{uuid.uuid4().hex}{extension}"
    private_storage.save(
        private_storage.build_relative_path(directory, name), upload.chunks())
    return name


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
