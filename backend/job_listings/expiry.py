"""
Retires scraped listings whose source advertisement has lapsed.

JobStreet keeps a posting for 30 days unless the advertiser pulls it sooner,
so a scraped listing older than that window is almost certainly a dead link —
clicking "View on JobStreet" lands on "This job is no longer advertised".

Listings are marked CLOSED rather than deleted. Demand statistics are built
from history on purpose: the 12-month trend and the skill-gap analysis need
last quarter's postings to describe the market, even though a student can no
longer apply to them.
"""

from datetime import timedelta

from django.db.models import DateField
from django.db.models.functions import Cast, Coalesce
from django.utils import timezone

from .models import JobListing


# How long a posting stays advertised on the source portal.
SOURCE_LISTING_LIFESPAN_DAYS = 30


def stale_scraped_listings(as_of=None):
    """ACTIVE scraped listings whose advertising window has passed.

    Age is measured from posted_date where the scraper captured one, falling
    back to when we first saw the listing — the same Coalesce the demand chart
    uses, and the only option for the listings with no posted_date.
    """
    as_of = as_of or timezone.localdate()
    cutoff = as_of - timedelta(days=SOURCE_LISTING_LIFESPAN_DAYS)

    return (
        JobListing.objects
        .filter(
            source_type=JobListing.SourceType.SCRAPED,
            status=JobListing.Status.ACTIVE,
        )
        .annotate(effective_date=Coalesce(
            'posted_date',
            Cast('posted_time', output_field=DateField()),
        ))
        .filter(effective_date__lt=cutoff)
    )


def expire_stale_listings(as_of=None):
    """Mark lapsed scraped listings CLOSED. Returns how many were changed."""
    return stale_scraped_listings(as_of).update(status=JobListing.Status.CLOSED)


def expiry_report(as_of=None):
    """Counts for reporting, without changing anything."""
    as_of = as_of or timezone.localdate()
    scraped = JobListing.objects.filter(source_type=JobListing.SourceType.SCRAPED)
    return {
        'total_scraped': scraped.count(),
        'active': scraped.filter(status=JobListing.Status.ACTIVE).count(),
        'closed': scraped.filter(status=JobListing.Status.CLOSED).count(),
        'stale_active': stale_scraped_listings(as_of).count(),
        'lifespan_days': SOURCE_LISTING_LIFESPAN_DAYS,
    }


def expire_closed_company_listings():
    """Close company listings whose advertised closing date has passed.

    Scraped listings expire on age (the source portal drops them after ~30
    days); a company listing expires on the date the employer themselves
    published. Nothing enforced that, so a listing stayed ACTIVE -- and
    therefore applicable -- indefinitely past its own deadline.

    Returns the number closed. Safe to re-run.
    """
    from django.utils import timezone

    from .models import JobListing

    return (
        JobListing.objects
        .filter(source_type=JobListing.SourceType.COMPANY,
                status=JobListing.Status.ACTIVE,
                closing_date__lt=timezone.localdate())
        .update(status=JobListing.Status.CLOSED)
    )
