"""Re-run skill extraction over stored adverts.

Needed whenever the extractor's rules change: JobSkill rows are the cached
result of running it once at scrape time, so a correction to the rules leaves
every existing advert holding the old answer. The skill gap, the match score
and the demand percentages are all computed from those rows, so a stale one
is not cosmetic.

Synchronises rather than adds: a skill the new rules reject is removed, in the
same way save_scraped_job does it, because an extractor fix that could only
ever add skills would never undo a false positive.

    python manage.py reextract_job_skills [--dry-run] [--show N]
"""

import collections

from django.core.management.base import BaseCommand
from django.db import transaction

from job_listings.models import JobListing, JobSkill
from scrape_jobs.skill_extractor import extract_skills_from_text


class Command(BaseCommand):
    help = "Re-extract skills for stored job listings"

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--show", type=int, default=15,
                            help="How many of the largest changes to print.")
        parser.add_argument(
            "--scraped-only", action="store_true", default=True,
            help="Leave company-posted listings alone (default).")

    @transaction.atomic
    def handle(self, *args, **options):
        listings = JobListing.objects.all()
        if options["scraped_only"]:
            listings = listings.filter(
                source_type=JobListing.SourceType.SCRAPED)

        removed = collections.Counter()
        added = collections.Counter()
        touched = 0

        for listing in listings.iterator(chunk_size=200):
            matched = extract_skills_from_text(
                f"{listing.job_title} {listing.description or ''}")
            matched_by_id = {skill.id: skill for skill in matched}

            existing = dict(
                JobSkill.objects.filter(job=listing)
                .values_list("skill_id", "skill__skill_name"))

            stale = set(existing) - set(matched_by_id)
            fresh = set(matched_by_id) - set(existing)
            if not stale and not fresh:
                continue

            touched += 1
            for skill_id in stale:
                removed[existing[skill_id]] += 1
            for skill_id in fresh:
                added[matched_by_id[skill_id].skill_name] += 1

            JobSkill.objects.filter(job=listing, skill_id__in=stale).delete()
            JobSkill.objects.bulk_create(
                [JobSkill(job=listing, skill_id=skill_id,
                          importance_level="MEDIUM") for skill_id in fresh],
                ignore_conflicts=True)

        if options["dry_run"]:
            transaction.set_rollback(True)

        self.stdout.write(self.style.SUCCESS(
            "%d advert(s) changed: %d skill link(s) removed, %d added%s"
            % (touched, sum(removed.values()), sum(added.values()),
               "  (dry run, rolled back)" if options["dry_run"] else "")))

        show = options["show"]
        if removed:
            self.stdout.write("\nRemoved most often:")
            for name, count in removed.most_common(show):
                self.stdout.write("    -%-4d %s" % (count, name))
        if added:
            self.stdout.write("\nAdded most often:")
            for name, count in added.most_common(show):
                self.stdout.write("    +%-4d %s" % (count, name))
