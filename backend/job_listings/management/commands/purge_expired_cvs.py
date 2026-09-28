"""Delete CVs the notice says are gone.

Privacy Notice 1.3 tells students two things about the file they attach to an
application, and both are promises this command keeps:

  * it is deleted six months after they apply
  * an application they never submitted keeps nothing

The second is the quieter one. A CV is stored when it is parsed, before the
student has decided to apply -- because a CV that defeats the reader is still
the document they sent, and should still reach the employer. Someone who
uploads three CVs and applies once leaves two files nobody claimed, and
nothing else would ever remove them.

Reports by default. --delete removes the files, and is irreversible: a CV is a
document the student gave us and there is no second copy.

    python manage.py purge_expired_cvs
    python manage.py purge_expired_cvs --delete

Run it on a schedule. A retention period kept only when somebody remembers is
not a retention period, and the notice states this one in writing.
"""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from job_listings.models import JobApplication
from resources import private_storage

#: What the notice says, and the only place it is written in code.
RETENTION = timedelta(days=182)

#: How long a stored CV may go unclaimed by an application. Long enough to
#: read a parse, correct it and submit without rushing; short enough that an
#: abandoned upload does not sit in storage indefinitely.
UNCLAIMED_GRACE = timedelta(days=1)

CV_PREFIX = "cv/"


class Command(BaseCommand):
    help = "Delete CVs older than the retention period, and unclaimed uploads"

    def add_arguments(self, parser):
        parser.add_argument(
            "--delete", action="store_true",
            help="Actually remove the files. Irreversible.")

    def handle(self, *args, **options):
        delete = options["delete"]
        now = timezone.now()

        expired = list(JobApplication.objects
                       .exclude(cv_path="")
                       .filter(applied_time__lt=now - RETENTION)
                       .values_list("pk", "cv_path"))

        # Everything in the store, minus everything an application still
        # points at. Read from the application table rather than from a
        # timestamp on the file, because the file is not what says whether it
        # was claimed.
        claimed = set(JobApplication.objects
                      .exclude(cv_path="")
                      .values_list("cv_path", flat=True))
        # Listed with their modified times in one pass: the grace period needs
        # an age for every file, and asking per file is a request per file.
        entries = dict(private_storage.iter_entries(CV_PREFIX))
        stored = set(entries)
        unclaimed = sorted(stored - claimed)

        self.stdout.write(f"retention           : {RETENTION.days} days")
        self.stdout.write(f"applications past it: {len(expired)}")
        self.stdout.write(f"files in the store  : {len(stored)}")
        self.stdout.write(f"claimed by an application: {len(claimed & stored)}")
        self.stdout.write(f"unclaimed           : {len(unclaimed)}")

        if not delete:
            self.stdout.write(self.style.WARNING(
                "\nNothing removed. Re-run with --delete."))
            return

        for pk, path in expired:
            private_storage.delete(path)
        JobApplication.objects.filter(
            pk__in=[pk for pk, _ in expired]).update(cv_path="")

        # An unclaimed file has no row to clear, only the object itself. Ones
        # younger than the grace period are left: a student may be reading
        # their parsed CV right now, and the application that claims it has
        # not been submitted yet.
        removed_unclaimed = 0
        for key in unclaimed:
            modified = entries.get(key)
            if modified is None or now - modified < UNCLAIMED_GRACE:
                continue
            private_storage.delete(key)
            removed_unclaimed += 1

        self.stdout.write(self.style.SUCCESS(
            f"\nremoved {len(expired)} expired CV(s) and "
            f"{removed_unclaimed} unclaimed file(s)."))
