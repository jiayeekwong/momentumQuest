"""Write the learning-resource catalogue out to versioned seed files.

Run after a scrape and its review, so the result lands in the repository as a
reviewable diff rather than living only in whichever database ran the scraper.

    python manage.py export_resources
    python manage.py export_resources --check    # CI: fail if files are stale
"""

from django.core.management.base import BaseCommand

from resources.seeds import (
    DATA_DIR, FILES, database_snapshot, file_snapshot, snapshot_digest,
    write_files,
)


class Command(BaseCommand):
    help = "Export courses and learning resources to versioned CSV seed files."

    def add_arguments(self, parser):
        parser.add_argument(
            "--check", action="store_true", default=False,
            help="Do not write; exit non-zero if the files are out of date.")

    def handle(self, *args, **options):
        snapshot = database_snapshot()

        if options["check"]:
            on_disk = file_snapshot(DATA_DIR)
            if snapshot_digest(on_disk) == snapshot_digest(snapshot):
                self.stdout.write(self.style.SUCCESS(
                    "Resource seed files match the database."))
                return
            for key in FILES:
                if on_disk.get(key) != snapshot[key]:
                    self.stdout.write(self.style.WARNING(
                        f"  {key}: {len(on_disk.get(key, []))} in file, "
                        f"{len(snapshot[key])} in database"))
            raise SystemExit(
                "Resource seeds are out of date. Run: manage.py export_resources")

        for filename, count in write_files(snapshot, DATA_DIR).items():
            self.stdout.write(f"  {filename}: {count} row(s)")
        self.stdout.write(self.style.SUCCESS(
            f"Resources exported. Digest: {snapshot_digest(snapshot)[:16]}"))
