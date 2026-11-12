"""Remove abandoned public posting attachments after a safe grace period."""

from datetime import timedelta

from dashboard.models import Announcement
from django.core.management.base import BaseCommand
from django.utils import timezone

from resources import private_storage
from resources.attachments import (
    ANNOUNCEMENT_ATTACHMENT_DIR,
    TRAINING_ATTACHMENT_DIR,
)
from resources.models import TrainingProgramme

UNCLAIMED_GRACE = timedelta(days=1)


class Command(BaseCommand):
    help = "Delete uploaded posting attachments no database row points at"

    def add_arguments(self, parser):
        parser.add_argument(
            "--delete", action="store_true",
            help="Actually remove eligible files. Without it, report only.")
        parser.add_argument(
            "--list", action="store_true",
            help="Print every orphaned key.")

    def handle(self, *args, **options):
        referenced = set(TrainingProgramme.objects
                         .exclude(attachment_path__isnull=True)
                         .values_list("attachment_path", flat=True))
        referenced |= set(Announcement.objects
                          .exclude(attachment_path__isnull=True)
                          .values_list("attachment_path", flat=True))

        entries = []
        for directory in (TRAINING_ATTACHMENT_DIR,
                          ANNOUNCEMENT_ATTACHMENT_DIR):
            entries.extend(private_storage.iter_entries(directory))

        orphans = [(key, modified) for key, modified in entries
                   if key not in referenced]
        cutoff = timezone.now() - UNCLAIMED_GRACE
        eligible = [(key, modified) for key, modified in orphans
                    if modified is not None and modified <= cutoff]

        self.stdout.write(
            f"{len(referenced)} attachment(s) referenced, "
            f"{len(orphans)} orphaned, {len(eligible)} old enough to remove")
        if options["list"]:
            for key, _modified in sorted(orphans):
                self.stdout.write("    " + key)

        if not options["delete"]:
            self.stdout.write(self.style.WARNING(
                "Nothing removed. Re-run with --delete to remove eligible files."))
            return

        removed = 0
        for key, _modified in eligible:
            if private_storage.delete(key):
                removed += 1
        self.stdout.write(self.style.SUCCESS(
            f"Removed {removed} orphaned attachment(s)."))
