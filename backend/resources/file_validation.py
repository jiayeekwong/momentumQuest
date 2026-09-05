"""Server-side validation of uploaded documents.

An uploaded file's extension is whatever the uploader typed, so it says
nothing about what the file actually is. This module reads the leading bytes
and decides from those, which is what stops a renamed executable from being
stored and later handed to an administrator to open.

Pure-Python on purpose: libmagic/python-magic needs a native DLL on Windows,
and the four formats MomentumQuest accepts all have short, unambiguous
signatures. There is no ambiguity worth a dependency here.
"""

import os

# (signature, offset, mime type, canonical extension)
_SIGNATURES = [
    (b"%PDF-",                 0, "application/pdf", ".pdf"),
    (b"\x89PNG\r\n\x1a\n",     0, "image/png",       ".png"),
    (b"\xff\xd8\xff",          0, "image/jpeg",      ".jpg"),
]

# Extensions a student may submit, mapped to the content types that are
# actually allowed to appear under them. .jpg and .jpeg are the same format.
ALLOWED_EXTENSIONS = {
    ".pdf":  {"application/pdf"},
    ".png":  {"image/png"},
    ".jpg":  {"image/jpeg"},
    ".jpeg": {"image/jpeg"},
}

MAX_BYTES = 10 * 1024 * 1024

# Enough for the longest signature with room to spare.
_PEEK_BYTES = 16


class InvalidUpload(Exception):
    """An uploaded file was rejected. The message is safe to show a student."""


def sniff_content_type(upload):
    """Return the MIME type implied by the file's own bytes, or None.

    The file pointer is restored, so the caller can still write the upload out
    afterwards.
    """
    try:
        upload.seek(0)
        head = upload.read(_PEEK_BYTES)
    finally:
        upload.seek(0)

    for signature, offset, mime_type, _ in _SIGNATURES:
        if head[offset:offset + len(signature)] == signature:
            return mime_type

    return None


def validate_document(upload, allowed_extensions=None, max_bytes=MAX_BYTES):
    """Check one uploaded document and return ``(extension, mime_type)``.

    Raises InvalidUpload with a student-readable message on any failure.
    """
    allowed = allowed_extensions or ALLOWED_EXTENSIONS

    extension = os.path.splitext(upload.name or "")[1].lower()
    if extension not in allowed:
        expected = ", ".join(sorted({e.lstrip(".").upper() for e in allowed}))
        raise InvalidUpload(f"A certificate must be a {expected} file.")

    if upload.size > max_bytes:
        megabytes = max_bytes // (1024 * 1024)
        raise InvalidUpload(f"A certificate must be {megabytes}MB or smaller.")

    if upload.size == 0:
        raise InvalidUpload("The uploaded file is empty.")

    mime_type = sniff_content_type(upload)
    if mime_type is None:
        # Covers executables, archives, Office documents and anything else
        # renamed to look acceptable.
        raise InvalidUpload(
            "The uploaded file is not a valid PDF, PNG or JPG. Please upload the "
            "original document."
        )

    if mime_type not in allowed[extension]:
        raise InvalidUpload(
            f"The file contents do not match its .{extension.lstrip('.')} extension. "
            "Please upload the original document."
        )

    return extension, mime_type
