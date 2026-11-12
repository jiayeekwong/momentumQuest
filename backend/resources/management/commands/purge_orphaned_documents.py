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
should do because it was run without arguments. Even with --delete, an orphan
younger than one day is left alone so the scheduled run cannot race the short
gap between storing a file and committing its database row.
"""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from resources.models import Certificate, TranscriptUpload
from resources import private_storage

#: CVs and public posting attachments have their own retention commands and
#: grace periods; this command owns identity-bearing verification documents.
MANAGED_DIRECTORIES = ("certificates", "transcripts")
UNCLAIMED_GRACE = timedelta(days=1)


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
        referenced = set()
        for model in (Certificate, TranscriptUpload):
            referenced |= {
                path.replace("\\", "/")
                for path in model.objects.exclude(file_path="")
                                         .values_list("file_path", flat=True)
            }

        # Asks the storage backend what it holds rather than walking a
        # directory, so this works against an object store too -- where the
        # orphans cost money for as long as they sit there.
        orphans, kept = [], 0
        for directory in MANAGED_DIRECTORIES:
            for key, modified in private_storage.iter_entries(directory):
                if key in referenced:
                    kept += 1
                else:
                    orphans.append((key, modified))

        cutoff = timezone.now() - UNCLAIMED_GRACE
        eligible = [(key, modified) for key, modified in orphans
                    if modified is not None and modified <= cutoff]

        self.stdout.write(
            "%d file(s) referenced by a database row, %d orphaned, "
            "%d old enough to remove"
            % (kept, len(orphans), len(eligible)))

        if options["list"]:
            for orphan, _modified in sorted(orphans):
                self.stdout.write("    " + orphan)

        if not options["delete"]:
            self.stdout.write(self.style.WARNING(
                "Nothing removed. Re-run with --delete to remove them."))
            return

        removed = failed = 0
        for orphan, _modified in eligible:
            try:
                if private_storage.delete(orphan):
                    removed += 1
                else:
                    failed += 1
                    self.stderr.write(f"could not remove {orphan}")
            except Exception as exc:
                failed += 1
                self.stderr.write(f"could not remove {orphan}: {exc}")

        self.stdout.write(self.style.SUCCESS(
            "Removed %d orphaned document(s)%s."
            % (removed, f", {failed} failed" if failed else "")))
