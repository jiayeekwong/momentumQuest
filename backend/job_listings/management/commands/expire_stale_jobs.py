"""
Retire listings that are no longer being advertised.

    python manage.py expire_stale_jobs --dry-run
    python manage.py expire_stale_jobs

Two different rules, because the two kinds of listing expire for different
reasons:

  * scraped  -- on age. The source portal drops a posting after ~30 days, so
                an older one sends the student to a dead page.
  * company  -- on the closing date the employer published themselves. Nothing
                enforced this before, so a listing stayed ACTIVE, visible and
                applicable indefinitely past its own deadline.

Runs at the end of every scrape; this command exists so it can also be run on
its own or on a schedule between scrapes.
"""

from django.core.management.base import BaseCommand
from django.utils import timezone

from job_listings.expiry import (
    SOURCE_LISTING_LIFESPAN_DAYS,
    expire_closed_company_listings,
    expire_stale_listings,
    expiry_report,
)
from job_listings.models import JobListing


class Command(BaseCommand):
    help = "Close scraped listings past the portal's advertising window, and company listings past their closing date."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true",
                            help="Report what would be closed without changing anything.")

    def handle(self, *args, **options):
        before = expiry_report()
        lapsed_company = JobListing.objects.filter(
            source_type=JobListing.SourceType.COMPANY,
            status=JobListing.Status.ACTIVE,
            closing_date__lt=timezone.localdate(),
        ).count()

        self.stdout.write(
            f"Scraped listings: {before['total_scraped']} "
            f"({before['active']} active, {before['closed']} closed). "
            f"Advertising window: {SOURCE_LISTING_LIFESPAN_DAYS} days."
        )

        if options["dry_run"]:
            self.stdout.write(self.style.WARNING(
                f"{before['stale_active']} scraped listing(s) would be closed on age.\n"
                f"{lapsed_company} company listing(s) would be closed on closing_date.\n"
                "(dry run; nothing changed)"
            ))
            return

        closed_scraped = expire_stale_listings()
        closed_company = expire_closed_company_listings()
        after = expiry_report()
        self.stdout.write(self.style.SUCCESS(
            f"Closed {closed_scraped} lapsed scraped listing(s) and "
            f"{closed_company} company listing(s) past their closing date. "
            f"Scraped now {after['active']} active, {after['closed']} closed."
        ))
