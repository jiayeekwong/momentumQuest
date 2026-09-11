"""Where private documents go, and what must never happen to them.

Certificates carry a student's full name and often an identification number.
Two properties matter more than the mechanics: a deployment must not silently
store them somewhere they will be discarded, and there must be exactly one
route to the bytes -- the view that checks ownership.

The object store is faked. These test this project's code, not boto3, and a
unit suite that reached a real bucket would need credentials and would fail
offline.
"""

import io

from django.core.exceptions import ImproperlyConfigured
from django.test import TestCase, override_settings

from . import private_storage
from .private_storage import (
    FilesystemPrivateStorage, R2PrivateStorage, configured_backend,
)


class FakeS3Client:
    """Enough of the S3 API for one private bucket."""

    def __init__(self):
        self.objects = {}
        self.deleted = []

    def upload_fileobj(self, fileobj, bucket, key):
        self.objects[key] = fileobj.read()

    def get_object(self, Bucket, Key):
        if Key not in self.objects:
            raise KeyError(f"no such key: {Key}")
        return {"Body": io.BytesIO(self.objects[Key])}

    def head_object(self, Bucket, Key):
        if Key not in self.objects:
            raise KeyError(f"no such key: {Key}")
        return {"ContentLength": len(self.objects[Key])}

    def delete_object(self, Bucket, Key):
        self.objects.pop(Key, None)
        self.deleted.append(Key)

    def get_paginator(self, _name):
        client = self

        class Paginator:
            def paginate(self, Bucket, Prefix=""):
                yield {"Contents": [{"Key": k} for k in sorted(client.objects)
                                    if k.startswith(Prefix)]}

        return Paginator()


def r2_backend():
    storage = R2PrivateStorage(
        bucket="momentumquest-private",
        endpoint_url="https://account.r2.cloudflarestorage.com",
        access_key="key", secret_key="secret")
    storage._client = FakeS3Client()
    return storage


class BackendSelectionTests(TestCase):
    """The choice that decides whether uploads survive a deploy."""

    def setUp(self):
        private_storage.reset_backend()
        self.addCleanup(private_storage.reset_backend)

    @override_settings(DEBUG=True, PRIVATE_STORAGE_BACKEND="",
                       PRIVATE_STORAGE_ALLOW_LOCAL=False, R2_SETTINGS={})
    def test_development_uses_the_local_filesystem(self):
        self.assertIsInstance(configured_backend(), FilesystemPrivateStorage)

    @override_settings(DEBUG=False, PRIVATE_STORAGE_BACKEND="",
                       PRIVATE_STORAGE_ALLOW_LOCAL=False, R2_SETTINGS={})
    def test_production_without_object_storage_refuses_to_start(self):
        """The property this whole abstraction exists for.

        Free hosting gives a container ephemeral storage. Falling back to it
        would mean the upload succeeds, the row is written, the student is told
        it worked, and the file is gone by the next deploy -- with nothing in
        any log, because nothing failed. There is no error to catch later, so
        the only place to refuse is startup.
        """
        with self.assertRaises(ImproperlyConfigured) as caught:
            configured_backend()

        self.assertIn("ephemeral", str(caught.exception))

    @override_settings(DEBUG=False, PRIVATE_STORAGE_BACKEND="",
                       PRIVATE_STORAGE_ALLOW_LOCAL=False,
                       R2_SETTINGS={"bucket": "b", "endpoint_url": "https://e",
                                    "access_key": "k", "secret_key": "s",
                                    "region": "auto"})
    def test_production_with_a_bucket_uses_it(self):
        backend = configured_backend()

        self.assertIsInstance(backend, R2PrivateStorage)
        self.assertTrue(backend.durable)

    @override_settings(DEBUG=False, PRIVATE_STORAGE_BACKEND="filesystem",
                       PRIVATE_STORAGE_ALLOW_LOCAL=False, R2_SETTINGS={})
    def test_a_deliberate_filesystem_choice_is_honoured(self):
        """A deployment with a real mounted disk is allowed to say so."""
        self.assertIsInstance(configured_backend(), FilesystemPrivateStorage)

    @override_settings(DEBUG=False, PRIVATE_STORAGE_BACKEND="",
                       PRIVATE_STORAGE_ALLOW_LOCAL=True, R2_SETTINGS={})
    def test_the_explicit_override_also_allows_local(self):
        self.assertIsInstance(configured_backend(), FilesystemPrivateStorage)

    @override_settings(DEBUG=False, PRIVATE_STORAGE_BACKEND="r2",
                       R2_SETTINGS={"bucket": "b"})
    def test_asking_for_r2_with_half_a_configuration_is_an_error(self):
        """Rather than a client that fails on the first upload, in production."""
        with self.assertRaises(ImproperlyConfigured):
            configured_backend()

    @override_settings(DEBUG=True, PRIVATE_STORAGE_BACKEND="nonsense")
    def test_an_unknown_backend_name_is_rejected(self):
        with self.assertRaises(ImproperlyConfigured):
            configured_backend()


class R2StorageTests(TestCase):
    """The four operations the application needs from a bucket."""

    def setUp(self):
        self.storage = r2_backend()
        self.key = private_storage.build_relative_path(
            "certificates", "cert_abc123.pdf")

    def test_a_document_is_stored_and_read_back_whole(self):
        self.storage.save(self.key, [b"%PDF-1.7 ", b"certificate bytes"])

        self.assertEqual(self.storage.open(self.key).read(),
                         b"%PDF-1.7 certificate bytes")

    def test_the_key_keeps_forward_slashes_whatever_the_caller_passed(self):
        """A row written on Windows reads "certificates\\cert.pdf", which on an
        object store would be one key containing a backslash -- a different
        object from the one Linux would ask for."""
        self.storage.save("certificates\\cert_win.pdf", [b"x"])

        self.assertIn("certificates/cert_win.pdf", self.storage.client.objects)

    def test_a_missing_object_reads_as_absent_rather_than_raising(self):
        """The view turns this into a 404; an exception would be a 500."""
        self.assertIsNone(self.storage.open("certificates/never_stored.pdf"))
        self.assertFalse(self.storage.exists("certificates/never_stored.pdf"))

    def test_a_stored_document_is_reported_present(self):
        self.storage.save(self.key, [b"x"])

        self.assertTrue(self.storage.exists(self.key))

    def test_deleting_removes_the_object(self):
        self.storage.save(self.key, [b"x"])

        self.assertTrue(self.storage.delete(self.key))
        self.assertFalse(self.storage.exists(self.key))

    def test_deleting_never_raises(self):
        """Every caller is cleaning up after something else -- a failed upload,
        a deleted account -- and must not have that turn into a 500."""
        class Broken(FakeS3Client):
            def delete_object(self, Bucket, Key):
                raise RuntimeError("bucket unreachable")

        self.storage._client = Broken()

        self.assertFalse(self.storage.delete(self.key))

    def test_an_empty_key_is_refused_rather_than_stored(self):
        with self.assertRaises(ValueError):
            self.storage.save("", [b"x"])

    def test_keys_can_be_listed_for_orphan_cleanup(self):
        """Orphans in a bucket cost money for as long as they sit there."""
        self.storage.save("certificates/a.pdf", [b"a"])
        self.storage.save("certificates/b.pdf", [b"b"])
        self.storage.save("transcripts/c.pdf", [b"c"])

        self.assertEqual(sorted(self.storage.iter_keys("certificates")),
                         ["certificates/a.pdf", "certificates/b.pdf"])

    def test_a_local_path_is_produced_for_a_reader_that_needs_one(self):
        """The transcript parser takes a filename, not a stream."""
        import os

        self.storage.save(self.key, [b"%PDF-1.7"])

        with self.storage.local_path(self.key) as path:
            self.assertTrue(os.path.exists(path))
            with open(path, "rb") as handle:
                self.assertEqual(handle.read(), b"%PDF-1.7")
            leaked = path

        # The copy carries identification data; it must not outlive the block.
        self.assertFalse(os.path.exists(leaked))

    def test_there_is_no_filesystem_path_for_an_object(self):
        """resolve() returning None is deliberate: a caller that wanted a path
        to hand elsewhere breaks here rather than silently addressing nothing."""
        self.assertIsNone(self.storage.resolve(self.key))
