"""Delete stored documents that no database row points at any more.

Certificates and transcripts are written under PRIVATE_MEDIA_ROOT and removed
by a ``post_delete`` receiver when their row goes. That covers deletion
through the ORM, and misses everything else:

  * a database reset or a rolled-back migration during development -- the
    rows vanish without a signal, the bytes stay;
  * an upload whose transaction rolled back after the file was written, if the
    view's own cleanup did not run;
  * files restored from a backup taken at a different moment than the
    database.

The result is identity-bearing PDFs sitting on disk that the system has no
record of, which the retention promise in the privacy notice says should not
exist. Nothing can reach them through the application -- every file view
resolves a path from a row -- but "unreachable" is not "deleted", and the
notice promises deleted.

    python manage.py purge_orphaned_documents            # report only
    python manage.py purge_orphaned_documents --delete

Reports by default. Deleting student documents is not something a command
should do because it was run without arguments.
"""

import os

from django.conf import settings
from django.core.management.base import BaseCommand

from resources.models import Certificate, TranscriptUpload

#: The directories the upload views write into. CVs are deliberately absent:
#: they are stored as URLs on JobApplication rather than as private files, so
#: there is nothing here to orphan.
MANAGED_DIRECTORIES = ("certificates", "transcripts")


class Command(BaseCommand):
    help = "Delete private documents with no database row pointing at them"

    def add_arguments(self, parser):
        parser.add_argument(
            "--delete", action="store_true",
            help="Actually remove the files. Without it, nothing is changed.")
        parser.add_argument(
            "--list", action="store_true",
            help="Print every orphan rather than a count.")

    def handle(self, *args, **options):
        root = settings.PRIVATE_MEDIA_ROOT

        referenced = set()
        for model in (Certificate, TranscriptUpload):
            referenced |= {
                path.replace("\\", "/")
                for path in model.objects.exclude(file_path="")
                                         .values_list("file_path", flat=True)
            }

        orphans, kept = [], 0
        for directory in MANAGED_DIRECTORIES:
            folder = os.path.join(root, directory)
            if not os.path.isdir(folder):
                continue
            for name in os.listdir(folder):
                relative = f"{directory}/{name}"
                if relative in referenced:
                    kept += 1
                elif os.path.isfile(os.path.join(folder, name)):
                    orphans.append(relative)

        total_bytes = sum(
            os.path.getsize(os.path.join(root, *o.split("/"))) for o in orphans)

        self.stdout.write(
            "%d file(s) referenced by a database row, %d orphaned (%.1f MB)"
            % (kept, len(orphans), total_bytes / 1_048_576))

        if options["list"]:
            for orphan in sorted(orphans):
                self.stdout.write("    " + orphan)

        if not options["delete"]:
            self.stdout.write(self.style.WARNING(
                "Nothing removed. Re-run with --delete to remove them."))
            return

        removed = failed = 0
        for orphan in orphans:
            try:
                os.remove(os.path.join(root, *orphan.split("/")))
                removed += 1
            except OSError as exc:
                failed += 1
                self.stderr.write(f"could not remove {orphan}: {exc}")

        self.stdout.write(self.style.SUCCESS(
            "Removed %d orphaned document(s)%s."
            % (removed, f", {failed} failed" if failed else "")))
