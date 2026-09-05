"""Write the skill catalogue out to the versioned seed files.

The counterpart to ``import_skills``. Run it after curating the catalogue --
adding a skill, retiring one, correcting a provenance row -- so the change
lands in the repository as a reviewable diff rather than living only in
whichever database happened to receive it.

    python manage.py export_skills
    python manage.py export_skills --check    # CI: fail if files are stale

``--check`` writes nothing. It compares the database against the files and
exits non-zero when they disagree, which is what stops a catalogue change from
being committed without its seed update.
"""

import csv

from django.core.management.base import BaseCommand

from scrape_jobs.catalogue import (
    DATA_DIR, FILES, database_snapshot, file_snapshot, snapshot_digest,
)


class Command(BaseCommand):
    help = "Export the skill catalogue to the versioned CSV seed files."

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
                    "Seed files match the database."))
                return
            # Named per table rather than a bare mismatch: knowing it is the
            # relationships that drifted is most of the work of fixing it.
            for key in FILES:
                if on_disk.get(key) != snapshot[key]:
                    self.stdout.write(self.style.WARNING(
                        f"  {key}: {len(on_disk.get(key, []))} in file, "
                        f"{len(snapshot[key])} in database"))
            raise SystemExit(
                "Seed files are out of date. Run: manage.py export_skills")

        for key, (filename, fields) in FILES.items():
            path = DATA_DIR / filename
            with open(path, "w", encoding="utf-8", newline="") as handle:
                # LF endings and no BOM, so the file is identical whichever
                # platform exported it and the diff is the catalogue change.
                writer = csv.DictWriter(handle, fieldnames=fields,
                                        lineterminator="\n")
                writer.writeheader()
                writer.writerows(snapshot[key])
            self.stdout.write(f"  {filename}: {len(snapshot[key])} row(s)")

        self.stdout.write(self.style.SUCCESS(
            f"Catalogue exported. Digest: {snapshot_digest(snapshot)[:16]}"))
