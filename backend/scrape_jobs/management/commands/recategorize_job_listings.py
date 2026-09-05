"""Re-apply classify_job_category to rows stored under the old rules.

Two separate problems are corrected here, and only one of them is fixed by
future scrapes:

  * JobListing.category is refreshed on every scrape, so scraped rows heal on
    their own -- but only at the next scrape, which is monthly. Company-posted
    listings are never re-classified at all.
  * JobTitle.category is written once and then only ever filled when NULL
    (see get_or_create_job_category's caller), so a title first seen under a
    wrong category keeps it permanently. Nothing else repairs that.

Scraped listings that a human has verified are left alone: the category is not
part of the MASCO review, but re-writing rows under review invites confusion
about which fields a reviewer owns. Pass --include-verified to override.
"""

from collections import Counter

from django.core.management.base import BaseCommand
from django.db import transaction

from job_listings.models import JobListing
from scrape_jobs.models import JobTitle
from scrape_jobs.services import classify_job_category, get_or_create_job_category


class Command(BaseCommand):
    help = "Re-classify JobListing.category and JobTitle.category with the current rules"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would change without writing anything.",
        )
        parser.add_argument(
            "--show-moves",
            type=int,
            default=0,
            metavar="N",
            help="Print the first N re-classifications, for spot-checking.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        show_moves = options["show_moves"]

        categories = {}

        def category_for(name):
            if name not in categories:
                categories[name] = get_or_create_job_category(name)
            return categories[name]

        listing_moves = Counter()
        listings_changed = listings_checked = 0
        printed = 0

        listings = JobListing.objects.select_related("category").only(
            "id", "job_title", "category"
        )
        for listing in listings.iterator(chunk_size=500):
            listings_checked += 1
            current = listing.category.category_name if listing.category else None
            expected = classify_job_category(listing.job_title)
            if current == expected:
                continue

            listing_moves[(current, expected)] += 1
            listings_changed += 1
            if printed < show_moves:
                self.stdout.write(f"  {current or '—'} -> {expected}: {listing.job_title}")
                printed += 1

            listing.category = category_for(expected)
            listing.save(update_fields=["category"])

        titles_changed = 0
        titles = JobTitle.objects.select_related("category").only(
            "id", "title_name", "category"
        )
        for job_title in titles.iterator(chunk_size=500):
            current = job_title.category.category_name if job_title.category else None
            expected = classify_job_category(job_title.title_name)
            if current == expected:
                continue
            job_title.category = category_for(expected)
            job_title.save(update_fields=["category"])
            titles_changed += 1

        if dry_run:
            transaction.set_rollback(True)

        suffix = " (dry run; rolled back)" if dry_run else ""
        self.stdout.write(self.style.SUCCESS(
            f"Listings: {listings_changed} re-classified of {listings_checked} checked. "
            f"Job titles: {titles_changed} re-classified{suffix}."
        ))

        if listing_moves:
            self.stdout.write("\nLargest moves:")
            for (current, expected), count in listing_moves.most_common(15):
                self.stdout.write(f"  {count:5d}  {current or '—'} -> {expected}")
