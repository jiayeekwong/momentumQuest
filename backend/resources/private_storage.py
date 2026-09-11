"""Where private documents live, and who is allowed to reach them.

Certificates and transcripts carry a student's full name and often an
identification number. Nothing here is ever served by a URL: every read goes
through a Django view that has already checked ownership, and this module only
answers "give me those bytes".

Two backends, one interface:

    development     the local filesystem, under PRIVATE_MEDIA_ROOT
    production      a private object store (Cloudflare R2, S3 API)

Object storage is not an optimisation. Free hosting gives a container ephemeral
storage, so a filesystem-backed certificate is discarded by the next deploy --
silently, months after the student uploaded it, with the database row still
pointing at it. That failure has no error to notice, which is why
``configured_backend`` refuses to start in production without object storage
rather than falling back to a disk it knows will not survive.

Paths are stored as keys with forward slashes, and reads tolerate either
separator. ``os.path.join`` produces a backslash on Windows, so a row written
there reads ``certificates\\cert_abc.pdf`` -- on Linux that is not a directory
and a filename but one filename containing a backslash, so every document
uploaded on Windows would 404 after a deployment. Rows already stored that way
still resolve.
"""

import io
import logging
import os
import tempfile
from contextlib import contextmanager

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------- helpers --

def build_relative_path(directory, filename):
    """A new stored key, always with forward slashes."""
    return f"{directory}/{filename}"


def stored_filename(relative_path):
    """The generated name a file is served under.

    Never the name the student uploaded: a file they saved as
    "040910101234_SPM.pdf" would otherwise put an identification number into a
    response header and into the reader's download folder.
    """
    return os.path.basename(relative_path.replace("\\", "/"))


def _key_parts(relative_path):
    return [p for p in relative_path.replace("\\", "/").split("/") if p]


# ------------------------------------------------------------- filesystem --

class FilesystemPrivateStorage:
    """Files under PRIVATE_MEDIA_ROOT. The development and workstation backend."""

    name = "filesystem"
    durable = False

    def resolve(self, relative_path):
        """Absolute path, or None if it escapes the private root.

        Stored keys are generated from uuid4 and cannot currently escape, but
        the check is free and the consequence of being wrong is serving or
        deleting an arbitrary file.
        """
        if not relative_path:
            return None

        root = os.path.realpath(settings.PRIVATE_MEDIA_ROOT)

        # An already-absolute path is re-checked rather than mangled. Splitting
        # one on "/" and rejoining it under the root produced a nonsense path
        # that failed containment, so a caller passing this function's own
        # output back in got a silent refusal -- which is how an orphaned
        # certificate once survived a failed upload.
        if os.path.isabs(relative_path):
            target = os.path.realpath(relative_path)
        else:
            target = os.path.realpath(
                os.path.join(root, *_key_parts(relative_path)))

        try:
            contained = os.path.commonpath([root, target]) == root
        except ValueError:
            # Different drives on Windows -- itself proof it is not inside.
            return None

        return target if contained else None

    def save(self, relative_path, chunks):
        target = self.resolve(relative_path)
        if target is None:
            raise ValueError("Refusing to write outside PRIVATE_MEDIA_ROOT")
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "wb") as destination:
            for chunk in chunks:
                destination.write(chunk)
        return relative_path

    def open(self, relative_path):
        target = self.resolve(relative_path)
        if target is None or not os.path.exists(target):
            return None
        return open(target, "rb")

    def exists(self, relative_path):
        target = self.resolve(relative_path)
        return target is not None and os.path.exists(target)

    @contextmanager
    def local_path(self, relative_path):
        """A real filesystem path. Already one here, so nothing is copied."""
        target = self.resolve(relative_path)
        if target is None or not os.path.exists(target):
            raise FileNotFoundError(relative_path)
        yield target

    def delete(self, relative_path):
        target = self.resolve(relative_path)
        if target is None:
            if relative_path:
                logger.error(
                    "Refusing to delete a stored file outside PRIVATE_MEDIA_ROOT")
            return False
        try:
            os.remove(target)
        except FileNotFoundError:
            # Already gone: the outcome the caller wanted, either way.
            return True
        except OSError:
            logger.exception("Could not delete stored document %s",
                             stored_filename(relative_path))
            return False
        return True

    def iter_keys(self, prefix=""):
        root = os.path.realpath(settings.PRIVATE_MEDIA_ROOT)
        base = os.path.join(root, *_key_parts(prefix)) if prefix else root
        if not os.path.isdir(base):
            return
        for directory, _subdirs, filenames in os.walk(base):
            for filename in filenames:
                absolute = os.path.join(directory, filename)
                yield os.path.relpath(absolute, root).replace("\\", "/")


# --------------------------------------------------------------------- R2 --

class R2PrivateStorage:
    """A private bucket over the S3 API. The production backend.

    The bucket has no public access and no permanent object URLs. Reads are
    streamed back through the authorising view, which keeps one rule in one
    place: if the view would refuse, there is no second route to the bytes.
    """

    name = "r2"
    durable = True

    def __init__(self, bucket, endpoint_url, access_key, secret_key,
                 region="auto"):
        self.bucket = bucket
        self._endpoint_url = endpoint_url
        self._access_key = access_key
        self._secret_key = secret_key
        self._region = region
        self._client = None

    @property
    def client(self):
        # Built on first use, not at import: settings are read at startup in
        # every environment including the test suite, and a missing boto3 or a
        # bad endpoint should surface when a document is actually stored.
        if self._client is None:
            import boto3
            from botocore.config import Config

            self._client = boto3.client(
                "s3",
                endpoint_url=self._endpoint_url,
                aws_access_key_id=self._access_key,
                aws_secret_access_key=self._secret_key,
                region_name=self._region,
                # R2 does not implement the AWS checksum trailers boto3 began
                # sending by default, and signature v4 is what it authenticates.
                config=Config(signature_version="s3v4",
                              retries={"max_attempts": 3, "mode": "standard"}),
            )
        return self._client

    def _normalise(self, relative_path):
        return "/".join(_key_parts(relative_path))

    def resolve(self, relative_path):
        """No filesystem path exists for an object. Deliberately None.

        Callers that need real bytes use open() or local_path(); a caller that
        wanted a path to hand to something else is a caller that would break
        here, and returning None makes that visible immediately.
        """
        return None

    def save(self, relative_path, chunks):
        key = self._normalise(relative_path)
        if not key:
            raise ValueError("Refusing to store an object with an empty key")
        # Buffered rather than streamed: these are single documents capped by
        # file_validation, and upload_fileobj wants a seekable object.
        buffer = io.BytesIO()
        for chunk in chunks:
            buffer.write(chunk)
        buffer.seek(0)
        self.client.upload_fileobj(buffer, self.bucket, key)
        return relative_path

    def open(self, relative_path):
        key = self._normalise(relative_path)
        if not key:
            return None
        try:
            return self.client.get_object(Bucket=self.bucket, Key=key)["Body"]
        except Exception:
            # A missing object is a 404 for the caller, the same as a missing
            # file. Anything else is worth the traceback.
            logger.warning("Private object could not be read: %s",
                           stored_filename(relative_path), exc_info=True)
            return None

    def exists(self, relative_path):
        key = self._normalise(relative_path)
        if not key:
            return False
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
        except Exception:
            return False
        return True

    @contextmanager
    def local_path(self, relative_path):
        """Download to a temporary file for a reader that needs a real path.

        Transcripts are parsed by a PDF library that takes a filename. The copy
        is removed in the finally block, and the object itself is deleted by the
        caller immediately afterwards -- a transcript is read once and never
        retained.
        """
        body = self.open(relative_path)
        if body is None:
            raise FileNotFoundError(relative_path)
        suffix = os.path.splitext(stored_filename(relative_path))[1]
        handle = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
        try:
            with handle:
                for chunk in iter(lambda: body.read(64 * 1024), b""):
                    handle.write(chunk)
            yield handle.name
        finally:
            try:
                os.remove(handle.name)
            except OSError:
                logger.warning("Temporary copy of a private document was left "
                               "behind at %s", handle.name)

    def delete(self, relative_path):
        key = self._normalise(relative_path)
        if not key:
            return False
        try:
            self.client.delete_object(Bucket=self.bucket, Key=key)
        except Exception:
            logger.exception("Could not delete stored document %s",
                             stored_filename(relative_path))
            return False
        return True

    def iter_keys(self, prefix=""):
        paginator = self.client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket,
                                       Prefix=self._normalise(prefix)):
            for entry in page.get("Contents", ()):
                yield entry["Key"]


# ---------------------------------------------------------------- backend --

def configured_backend():
    """Choose a backend from settings, and refuse a lossy production default.

    The important case is the last one. A production deployment with no object
    store configured must not quietly write to container storage that the next
    deploy discards: the upload succeeds, the row is written, the student is
    told it worked, and the file is gone by the following week with nothing in
    any log. Failing at startup is the only version of that anyone notices.
    """
    configured = (getattr(settings, "PRIVATE_STORAGE_BACKEND", "") or "").strip()
    r2 = getattr(settings, "R2_SETTINGS", {}) or {}
    has_r2 = all(r2.get(k) for k in
                 ("bucket", "endpoint_url", "access_key", "secret_key"))

    if configured == "filesystem":
        return FilesystemPrivateStorage()
    if configured == "r2" or (not configured and has_r2):
        if not has_r2:
            raise ImproperlyConfigured(
                "PRIVATE_STORAGE_BACKEND is 'r2' but R2_BUCKET, "
                "R2_ENDPOINT_URL, R2_ACCESS_KEY_ID and R2_SECRET_ACCESS_KEY "
                "are not all set.")
        return R2PrivateStorage(
            bucket=r2["bucket"], endpoint_url=r2["endpoint_url"],
            access_key=r2["access_key"], secret_key=r2["secret_key"],
            region=r2.get("region") or "auto")
    if configured:
        raise ImproperlyConfigured(
            f"Unknown PRIVATE_STORAGE_BACKEND: {configured!r}. "
            f"Expected 'filesystem' or 'r2'.")

    if settings.DEBUG or getattr(settings, "PRIVATE_STORAGE_ALLOW_LOCAL", False):
        return FilesystemPrivateStorage()

    raise ImproperlyConfigured(
        "No private document storage is configured and DEBUG is false. "
        "Certificates carry identification numbers and container storage is "
        "ephemeral, so writing them to the local filesystem would lose them at "
        "the next deploy with no error. Set the R2_* variables, or set "
        "PRIVATE_STORAGE_BACKEND=filesystem deliberately if this deployment "
        "really has durable local storage.")


_backend = None


def backend():
    """The process-wide backend, built once."""
    global _backend
    if _backend is None:
        _backend = configured_backend()
    return _backend


def reset_backend():
    """Forget the cached backend. For tests that change the configuration."""
    global _backend
    _backend = None


# ------------------------------------------------------- module-level API --
#
# Callers use these and never a backend directly, so switching backends is a
# configuration change rather than a code change.

def resolve(relative_path):
    return backend().resolve(relative_path)


def save(relative_path, chunks):
    return backend().save(relative_path, chunks)


def open_stored(relative_path):
    """Binary stream for a stored document, or None if it is not there."""
    return backend().open(relative_path)


def exists(relative_path):
    return backend().exists(relative_path)


def local_path(relative_path):
    """Context manager yielding a real filesystem path for the stored bytes."""
    return backend().local_path(relative_path)


def delete(relative_path):
    """Remove one stored document.

    Returns True when it is gone afterwards (including when already absent),
    False when the path was refused or the removal failed.

    Never raises. Every caller is cleaning up after something else -- a failed
    upload, a deleted account -- and a locked or missing file must not turn that
    into a 500. Failures are logged for follow-up instead.
    """
    return backend().delete(relative_path)


def iter_keys(prefix=""):
    return backend().iter_keys(prefix)
