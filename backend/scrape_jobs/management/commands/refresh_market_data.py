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

Two Selenium crawls writing the same adverts, one of them halfway through
re-extraction while the other replaces the rows underneath it, is not a
situation worth reasoning about after the fact, so a second refresh refuses.
What refuses it is the ScrapeLog row rather than the advisory lock that used to.
An advisory lock lives on the connection holding it, and this command cannot
hold a connection: the crawl leaves it idle for hours and a hosted database
drops it. The lock was therefore gone long before the refresh it was guarding
finished -- and the dead connection then broke the release in the finally
clause, replacing the real failure with an InterfaceError. The lock is still
taken, but only across the checks at the start, where the connection is known
to be alive.
"""

import time
from datetime import timedelta

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.utils import timezone

from job_listings.models import JobListing, JobSkill, ScrapeLog
from scrape_jobs import db

#: Any 64-bit constant. Chosen once and never changed: the number *is* the lock
#: identity, so a different value in a future release would silently stop
#: excluding the older one.
ADVISORY_LOCK_KEY = 8_417_235_901_114_233

#: How long a refresh can plausibly still be running. A ScrapeLog row left
#: unfinished for longer than this belongs to a run that died rather than one
#: still crawling -- the row alone cannot distinguish them, so this is where the
#: line is drawn. A full forty-page crawl takes around three hours.
ABANDONED_AFTER = timedelta(hours=6)

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
            "--start-page", type=int, default=1,
            help=("Resume a crawl that was stopped. The previous run's summary "
                  "names the page to pass here; everything before it is already "
                  "stored."))
        parser.add_argument(
            "--skip-taxonomies", action="store_true", default=False,
            help="Do not reload the skill and Market Role seeds first.")
        parser.add_argument(
            "--ignore-abandoned-run", action="store_true", default=False,
            help=("Start even though an earlier ScrapeLog row was never "
                  "finished. Use when that run is known to have died, which a "
                  "dropped connection during a crawl will leave behind."))
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
        """Best effort, because failing here only hides why the run failed.

        PostgreSQL releases every session-level advisory lock when the session
        ends, so a connection that has dropped has already released this one and
        there is nothing left to do. Raising instead replaced the real
        RefreshFailed with InterfaceError from the finally clause, which is how
        a refresh that died of a dropped connection came to report a problem
        with releasing a lock.
        """
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_unlock(%s)",
                               [ADVISORY_LOCK_KEY])
        except Exception as exc:
            self.stderr.write(f"Could not release the advisory lock: {exc}")

    def _refuse_if_a_refresh_is_running(self, ignore_abandoned):
        """The guard that outlives the connection: an unfinished ScrapeLog row.

        The scraper writes one before it starts and finishes it at the end, so
        a recent row with no finished_at means a refresh is already under way.
        Being data rather than session state, it survives exactly the dropped
        connection that made the advisory lock useless here.
        """
        running = (ScrapeLog.objects
                   .filter(finished_at__isnull=True,
                           started_at__gte=timezone.now() - ABANDONED_AFTER)
                   .order_by("-id").first())
        if running is None:
            return

        started = timezone.localtime(running.started_at).strftime("%Y-%m-%d %H:%M")
        if ignore_abandoned:
            self.stdout.write(self.style.WARNING(
                f"Ignoring unfinished ScrapeLog #{running.id}, started {started}."))
            return

        raise RefreshFailed(
            f"ScrapeLog #{running.id} started {started} and was never "
            f"finished, so a refresh may still be crawling. If that run is "
            f"known to have died -- a crawl whose connection dropped leaves "
            f"exactly this -- re-run with --ignore-abandoned-run.")

    # ------------------------------------------------------------ judgement

    def _acquisition_verdict(self, log, allow_no_new):
        """Did the acquisition actually work? Reads the row, not an exit code.

        Returns None when it did, or a reason string when it did not.
        """
        if log is None:
            return "the scrape recorded no ScrapeLog row at all"

        if log.status == ScrapeLog.Status.FAILED:
            return (f"ScrapeLog #{log.id} status is {log.status}"
                    + (f": {log.error_message}" if log.error_message else ""))

        # PARTIAL deliberately passes. It is set whenever anything at all was
        # refused, including a single advert, and a crawl that traversed the
        # whole search and missed two adverts of three thousand is not a failed
        # acquisition -- but it used to be treated as one, which stopped every
        # downstream stage and left the skill gaps unrecorded. What matters is
        # what was actually missed, judged below, not the label.

        # A refused search page is the serious case: it costs a whole page of
        # adverts and ends the crawl where it stands.
        if log.stop_reason == ScrapeLog.StopReason.BLOCKED:
            return ("the source refused a page of results, so the crawl stopped "
                    f"at page {log.last_page_saved or log.start_page} -- this "
                    "host is being turned away")

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
        started = time.monotonic()

        # Before anything else, and retrying: two resumed runs died here, on the
        # first connection of all, because name resolution happened to be in one
        # of its bursts at that second. Nothing had been crawled and nothing was
        # wrong -- the run simply asked at the wrong moment and gave up.
        db.ensure()

        # The lock covers the checks and the taxonomy load, and is dropped
        # before the crawl -- the point past which no connection survives. From
        # there the unfinished ScrapeLog row the scraper writes is what refuses
        # a second run. The gap between the two is the few milliseconds
        # call_command takes to reach create_scrape_log.
        if not self._acquire_lock():
            raise RefreshFailed(
                "Another market refresh holds the advisory lock. Refusing to "
                "run a second one concurrently.")
        try:
            self._refuse_if_a_refresh_is_running(options["ignore_abandoned_run"])
            self._load_taxonomies(options)
        finally:
            self._release_lock()

        self._run(options)

        self.stdout.write(self.style.SUCCESS(
            f"Market refresh complete in {time.monotonic() - started:.0f}s."))

    def _load_taxonomies(self, options):
        if options["skip_taxonomies"]:
            return
        # First, because everything below classifies against them and the
        # scraper classifies each advert as it saves it. Both read
        # source-controlled CSVs and are idempotent.
        self.stdout.write("Loading taxonomies...")
        call_command("import_skills")
        call_command("load_market_roles")

    def _run(self, options):
        before = ScrapeLog.objects.order_by("-id").values_list("id", flat=True).first()

        self.stdout.write("Acquiring adverts...")
        try:
            call_command(
                "scrape_jobs",
                max_pages=options["max_pages"],
                max_jobs=options["max_jobs"],
                start_page=options["start_page"],
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

        # Said separately from the status, because they answer different
        # questions and only one of them is about coverage. A refresh can be
        # SUCCESS on every count here and still have read a fifth of the search.
        if log.pagination_exhausted:
            self.stdout.write(self.style.SUCCESS(
                "  Pagination status: EXHAUSTED -- the configured search was "
                "traversed to its last page."))
        else:
            self.stdout.write(self.style.WARNING(
                f"  Pagination status: INCOMPLETE ({log.stop_reason}) -- this "
                f"run did not reach the end of the search, so the adverts it "
                f"acquired are a subset of what the source offers."
                + (f" Resume with --start-page {log.resume_page}."
                   if log.resume_page else "")))

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
            ("pages with results", log.pages_with_results),
            ("pages covered", f"{log.start_page} to {log.last_page_saved}"
                              if log.last_page_saved else "none stored"),
            ("resume at page", log.resume_page or "-"),
            ("stop reason", log.stop_reason),
            ("pagination exhausted", "YES" if log.pagination_exhausted else "NO"),
            ("JobListing total", JobListing.objects.count()),
            ("JobSkill total", JobSkill.objects.count()),
            ("classified into a role", classified),
            ("latest success", ScrapeLog.objects.filter(status="SUCCESS")
                .order_by("-finished_at")
                .values_list("finished_at", flat=True).first()),
        ):
            self.stdout.write(f"    {label:24} {value}")
