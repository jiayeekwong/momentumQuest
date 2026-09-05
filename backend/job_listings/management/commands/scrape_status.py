from django.core.management.base import BaseCommand
from django.utils import timezone

from job_listings.models import JobListing, ScrapeLog


class Command(BaseCommand):
    """Answer "is the scrape finished?" without guessing.

    The obvious signals all mislead while a run is in flight:

      * ``status`` is written as FAILED when the run STARTS and only corrected
        at the end, so a healthy run in progress reads FAILED.
      * ``jobs_scraped`` stays 0 until the very end, because the command
        collects every page in memory and saves once.
      * the JobListing count stays flat for the same reason.

    ``finished_at`` is the only field that distinguishes running from done.
    """

    help = "Show whether a scrape is still running and how the last ones went"

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=5)

    def handle(self, *args, **options):
        latest = ScrapeLog.objects.order_by("-id").first()
        if latest is None:
            self.stdout.write("No scrape has ever been run.")
            return

        def local(value):
            return timezone.localtime(value).strftime("%Y-%m-%d %H:%M:%S") if value else "-"

        if latest.finished_at is None:
            elapsed = timezone.now() - latest.started_at
            minutes = int(elapsed.total_seconds() // 60)
            self.stdout.write(self.style.WARNING(
                f"RUNNING - scrape #{latest.pk} started {local(latest.started_at)} "
                f"({minutes} min ago)."
            ))
            self.stdout.write(
                "  Counters stay at zero until the run ends; that is not a stall.\n"
                "  Confirm the process is alive with:\n"
                '    powershell "Get-Process python,chrome -ErrorAction SilentlyContinue | '
                'Measure-Object | Select-Object Count"'
            )
        else:
            style = self.style.SUCCESS if latest.status == "SUCCESS" else self.style.ERROR
            took = latest.finished_at - latest.started_at
            self.stdout.write(style(
                f"DONE - scrape #{latest.pk} {latest.status}, "
                f"took {int(took.total_seconds() // 60)} min "
                f"(finished {local(latest.finished_at)})."
            ))
            if latest.error_message:
                self.stdout.write(self.style.ERROR(f"  error: {latest.error_message}"))

        self.stdout.write("")
        self.stdout.write("  id  started              status    scraped  created  updated  blocked")
        for log in ScrapeLog.objects.order_by("-id")[:options["limit"]]:
            state = log.status if log.finished_at else "RUNNING"
            self.stdout.write(
                f"  {log.pk:<3} {local(log.started_at):<20} {state:<9} "
                f"{log.jobs_scraped:>7}  {log.jobs_created:>7}  "
                f"{log.jobs_updated:>7}  {log.blocked_count:>7}"
            )

        scraped = JobListing.objects.filter(source_type=JobListing.SourceType.SCRAPED)
        self.stdout.write("")
        self.stdout.write(
            f"  Database: {scraped.count()} scraped listings "
            f"({scraped.filter(status=JobListing.Status.ACTIVE).count()} active, "
            f"{scraped.filter(market_role__isnull=False).count()} classified)"
        )
