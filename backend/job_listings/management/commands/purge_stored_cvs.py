"""Delete CV files left behind by the old upload flow.

CVs are no longer stored: they are parsed once, deleted in a finally block,
and only the structured result the student confirms is kept. But files
uploaded before that change are still on disk under MEDIA_ROOT -- which is
public, so a deployment that serves /media/ exposes them, and one that does
not leaves broken links.

Nothing reads them any more. CVParseView does not write there, the apply flow
stores an applicant_snapshot instead of a URL, and no view serves the path.
The rows keep their legacy cv_url text so the history is not rewritten; only
the files go.

Reports by default. --delete removes them, and is irreversible: a CV is a
document the student gave us and there is no second copy.

    python manage.py purge_stored_cvs
    python manage.py purge_stored_cvs --delete
"""

import os

from django.conf import settings
from django.core.management.base import BaseCommand

from job_listings.models import JobApplication


class Command(BaseCommand):
    help = "Report or delete CV files left in MEDIA_ROOT by the old upload flow"

    def add_arguments(self, parser):
        parser.add_argument(
            "--delete", action="store_true",
            help="Actually remove the files. Irreversible.")

    def handle(self, *args, **options):
        delete = options["delete"]
        directory = os.path.join(settings.MEDIA_ROOT, "cv")

        if not os.path.isdir(directory):
            self.stdout.write(self.style.SUCCESS(
                "No CV directory. Nothing was ever stored, or it is already gone."))
            return

        files = sorted(
            name for name in os.listdir(directory)
            if os.path.isfile(os.path.join(directory, name))
        )
        if not files:
            self.stdout.write(self.style.SUCCESS("No stored CVs remain."))
            return

        referencing = JobApplication.objects.exclude(cv_url="").count()
        total_bytes = sum(
            os.path.getsize(os.path.join(directory, name)) for name in files)

        self.stdout.write(
            f"{len(files)} CV file(s) in {directory} "
            f"({total_bytes / 1024:.0f} KB)."
        )
        self.stdout.write(
            f"{referencing} application(s) still carry a legacy cv_url. Those "
            "rows keep their text; only the files are affected."
        )
        for name in files:
            self.stdout.write(f"  {name}")

        if not delete:
            self.stdout.write(self.style.WARNING(
                "\nReport only. These sit under the public MEDIA_ROOT and are "
                "served to anyone who can guess the path if /media/ is exposed. "
                "Re-run with --delete to remove them."))
            return

        removed = 0
        for name in files:
            try:
                os.unlink(os.path.join(directory, name))
                removed += 1
            except OSError as exc:
                self.stderr.write(self.style.ERROR(f"  could not delete {name}: {exc}"))

        try:
            os.rmdir(directory)
        except OSError:
            pass

        self.stdout.write(self.style.SUCCESS(
            f"\nDeleted {removed} stored CV file(s). No CV is written to disk "
            "any more."))
