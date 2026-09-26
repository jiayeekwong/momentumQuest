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

Works in committed chunks with the skill vocabulary built once for the run.
Both matter only at scale and only against a hosted database: rebuilding the
vocabulary per advert is two full-table queries each, and a single
transaction across several thousand adverts stays open long enough for the
server to close the connection under it -- discarding every advert already
done.
"""

import collections

from django.core.management.base import BaseCommand
from django.db import transaction

from job_listings.models import JobListing, JobSkill
from scrape_jobs.skill_extractor import (
    build_skill_terms, extract_skills_from_text)


class Command(BaseCommand):
    help = "Re-extract skills for stored job listings"

    #: Adverts per transaction. Small enough that a dropped connection costs
    #: seconds of work rather than the whole run, large enough that the commits
    #: are not themselves the cost.
    CHUNK = 200

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--show", type=int, default=15,
                            help="How many of the largest changes to print.")
        parser.add_argument(
            "--scraped-only", action="store_true", default=True,
            help="Leave company-posted listings alone (default).")

    def handle(self, *args, **options):
        listings = JobListing.objects.all()
        if options["scraped_only"]:
            listings = listings.filter(
                source_type=JobListing.SourceType.SCRAPED)

        # Once for the run, not once per advert. Re-reading the skill and alias
        # tables for each listing is two full-table queries apiece: unnoticeable
        # against a local socket, and eight thousand round trips across the
        # internet for a table of four thousand adverts -- which is how this
        # command came to hold one transaction open long enough for a hosted
        # database to close the connection under it.
        terms = build_skill_terms()

        # Ids first, then chunks. Iterating a queryset while committing would
        # mean committing under a server-side cursor, which closes it.
        ids = list(listings.values_list("id", flat=True))

        if options["dry_run"]:
            with transaction.atomic():
                stats = self._reextract(ids, terms)
                transaction.set_rollback(True)
        else:
            stats = self._reextract(ids, terms)

        touched, removed, added = stats
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

    def _reextract(self, ids, terms):
        """Re-extract in committed chunks. Returns (touched, removed, added).

        One transaction per chunk rather than one for the whole command: a run
        over several thousand adverts takes minutes, and a connection dropped
        in the ninth minute used to discard the eight that worked.
        """
        removed = collections.Counter()
        added = collections.Counter()
        touched = 0

        for start in range(0, len(ids), self.CHUNK):
            batch = ids[start:start + self.CHUNK]
            with transaction.atomic():
                # The chunk's existing links in one query rather than one per
                # advert. Another few thousand round trips otherwise, for rows
                # that could be asked for together.
                existing_by_job = {}
                for job_id, skill_id, name in (
                        JobSkill.objects.filter(job_id__in=batch)
                        .values_list("job_id", "skill_id", "skill__skill_name")):
                    existing_by_job.setdefault(job_id, {})[skill_id] = name

                for listing in JobListing.objects.filter(id__in=batch):
                    matched = extract_skills_from_text(
                        f"{listing.job_title} {listing.description or ''}",
                        terms_by_skill=terms)
                    matched_by_id = {skill.id: skill for skill in matched}

                    existing = existing_by_job.get(listing.id, {})

                    stale = set(existing) - set(matched_by_id)
                    fresh = set(matched_by_id) - set(existing)
                    if not stale and not fresh:
                        continue

                    touched += 1
                    for skill_id in stale:
                        removed[existing[skill_id]] += 1
                    for skill_id in fresh:
                        added[matched_by_id[skill_id].skill_name] += 1

                    JobSkill.objects.filter(
                        job=listing, skill_id__in=stale).delete()
                    JobSkill.objects.bulk_create(
                        [JobSkill(job=listing, skill_id=skill_id,
                                  importance_level="MEDIUM")
                         for skill_id in fresh],
                        ignore_conflicts=True)

        return touched, removed, added
