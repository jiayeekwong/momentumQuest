"""One market refresh, with an honest exit code.

    python manage.py refresh_market_data [--max-pages N] [--max-jobs N]

This exists because ``scrape_jobs`` cannot be scheduled. It exits 0 whether it
worked or not -- a validation run recorded

    Status  : FAILED
    Error   : Could not reach host. Are you offline?

and still returned success. Unattended that is a monthly job reporting success
while market data silently goes stale, and stale market data is not a visible
outage: it is a skill gap quietly computed against last year's adverts, which
nobody notices because the page still renders.

So this command judges the refresh by what was *persisted*, not by what the
inner commands returned. It reads the ScrapeLog row the acquisition wrote, and
if that says FAILED -- or says every page was blocked -- it stops before the
downstream stages and exits non-zero. Running extraction and classification over
an unchanged table would produce a run that looked busy and successful having
acquired nothing.

The stages after acquisition are the ones from schedule_scraper_monthly.bat, in
the same dependency order and for the same reasons: adverts are deduplicated
before anything counts them, skills are re-extracted because JobSkill rows are a
cached extractor result, roles are re-classified because each advert was
classified when it was saved, and skill gaps are recorded once at the end over
settled data.

A PostgreSQL advisory lock makes a second concurrent refresh refuse rather than
interleave. Two Selenium crawls writing the same adverts, one of them halfway
through re-extraction while the other replaces the rows underneath it, is not a
situation worth reasoning about after the fact.
"""

import time

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from job_listings.models import JobListing, JobSkill, ScrapeLog

#: Any 64-bit constant. Chosen once and never changed: the number *is* the lock
#: identity, so a different value in a future release would silently stop
#: excluding the older one.
ADVISORY_LOCK_KEY = 8_417_235_901_114_233

#: Stages run only once the acquisition is known to have succeeded. Order is
#: dependency order, not preference.
DOWNSTREAM = (
    ("dedupe_scraped_listings", {}),
    ("recategorize_job_listings", {}),
    ("reextract_job_skills", {}),
    ("classify_market_roles", {}),
    ("refresh_skill_gaps", {}),
)


class RefreshFailed(CommandError):
    """The refresh did not acquire usable data. Exits non-zero."""


class Command(BaseCommand):
    help = ("Acquire market data and run every dependent stage, failing loudly "
            "if the acquisition did not succeed.")

    def add_arguments(self, parser):
        parser.add_argument("--max-pages", type=int, default=40)
        parser.add_argument("--max-jobs", type=int, default=32)
        parser.add_argument(
            "--skip-taxonomies", action="store_true", default=False,
            help="Do not reload the skill and Market Role seeds first.")
        parser.add_argument(
            "--allow-no-new-adverts", action="store_true", default=False,
            help=("Treat a successful scrape that created nothing as success. "
                  "A re-run inside the same posting window legitimately finds "
                  "nothing new."))

    # ------------------------------------------------------------------ lock

    def _acquire_lock(self):
        """Non-blocking, so a second run refuses instead of queueing.

        Queueing would be worse than refusing: a monthly job that waits for a
        stuck predecessor holds a runner for hours and then does the work twice
        in a row.
        """
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_lock(%s)", [ADVISORY_LOCK_KEY])
            return bool(cursor.fetchone()[0])

    def _release_lock(self):
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_unlock(%s)", [ADVISORY_LOCK_KEY])

    # ------------------------------------------------------------ judgement

    def _acquisition_verdict(self, log, allow_no_new):
        """Did the acquisition actually work? Reads the row, not an exit code.

        Returns None when it did, or a reason string when it did not.
        """
        if log is None:
            return "the scrape recorded no ScrapeLog row at all"

        if log.status != "SUCCESS":
            return (f"ScrapeLog #{log.id} status is {log.status}"
                    + (f": {log.error_message}" if log.error_message else ""))

        # Every page blocked is a bot wall, which the scraper records as a
        # count rather than as a failure. A run that was fully blocked
        # "succeeded" at being turned away.
        if log.pages_attempted and log.blocked_count >= log.pages_attempted:
            return (f"every page was blocked ({log.blocked_count} of "
                    f"{log.pages_attempted}) -- the source refused this host")

        if log.jobs_scraped == 0:
            return "the scrape returned no adverts at all"

        if not allow_no_new and log.jobs_created == 0 and log.jobs_updated == 0:
            return ("the scrape stored nothing new or changed; pass "
                    "--allow-no-new-adverts if that is expected")

        return None

    # ----------------------------------------------------------------- main

    def handle(self, *args, **options):
        if not self._acquire_lock():
            raise RefreshFailed(
                "Another market refresh holds the advisory lock. Refusing to "
                "run a second one concurrently.")

        started = time.monotonic()
        try:
            self._run(options)
        finally:
            self._release_lock()

        self.stdout.write(self.style.SUCCESS(
            f"Market refresh complete in {time.monotonic() - started:.0f}s."))

    def _run(self, options):
        if not options["skip_taxonomies"]:
            # First, because everything below classifies against them and the
            # scraper classifies each advert as it saves it. Both read
            # source-controlled CSVs and are idempotent.
            self.stdout.write("Loading taxonomies...")
            call_command("import_skills")
            call_command("load_market_roles")

        before = ScrapeLog.objects.order_by("-id").values_list("id", flat=True).first()

        self.stdout.write("Acquiring adverts...")
        try:
            call_command(
                "scrape_jobs",
                max_pages=options["max_pages"],
                max_jobs=options["max_jobs"],
                # Gaps are recorded once at the end, over settled data.
                skip_skill_gap_refresh=True,
            )
        except Exception as exc:
            # An exception here is the honest case; the silent one is below.
            raise RefreshFailed(f"The scraper raised: {exc}") from exc

        log = ScrapeLog.objects.order_by("-id").first()
        if log is not None and before is not None and log.id == before:
            raise RefreshFailed(
                "The scraper wrote no new ScrapeLog row, so nothing can be "
                "said about whether it ran.")

        reason = self._acquisition_verdict(log, options["allow_no_new_adverts"])
        if reason is not None:
            # Stop here. The downstream stages would run happily over an
            # unchanged table and report success, which is the failure this
            # command exists to prevent.
            raise RefreshFailed(
                f"Acquisition failed, so no downstream stage ran: {reason}")

        self.stdout.write(self.style.SUCCESS(
            f"  ScrapeLog #{log.id} {log.status}: {log.jobs_scraped} advert(s), "
            f"{log.jobs_created} new, {log.jobs_updated} updated, "
            f"{log.blocked_count} page(s) blocked"))

        for name, kwargs in DOWNSTREAM:
            self.stdout.write(f"Running {name}...")
            call_command(name, **kwargs)

        self._report(log)

    def _report(self, log):
        """Metrics worth having in a runner's log a month later."""
        classified = JobListing.objects.filter(market_role__isnull=False).count()
        self.stdout.write("")
        self.stdout.write("Market data after refresh:")
        for label, value in (
            ("ScrapeLog id", log.id),
            ("status", log.status),
            ("pages attempted", log.pages_attempted),
            ("pages blocked", log.blocked_count),
            ("adverts acquired", log.jobs_scraped),
            ("adverts created", log.jobs_created),
            ("adverts updated", log.jobs_updated),
            ("JobListing total", JobListing.objects.count()),
            ("JobSkill total", JobSkill.objects.count()),
            ("classified into a role", classified),
            ("latest success", ScrapeLog.objects.filter(status="SUCCESS")
                .order_by("-finished_at")
                .values_list("finished_at", flat=True).first()),
        ):
            self.stdout.write(f"    {label:24} {value}")
