from django.core.management.base import BaseCommand, CommandError

from scrape_jobs import db, pagination
from job_listings.expiry import expire_closed_company_listings, expire_stale_listings
from scrape_jobs.scraper import scrape_jobs, JOBSTREET_ICT_URL
from scrape_jobs.market_role_classifier import build_index
from scrape_jobs.services import create_scrape_log, finish_scrape_log, save_scraped_jobs


class Command(BaseCommand):
    help = "Scrape JobStreet ICT jobs and save to database"

    def add_arguments(self, parser):
        parser.add_argument(
            "--max-pages",
            type=int,
            default=1,
            help="Pages to scrape (default: 1)",
        )
        parser.add_argument(
            "--max-jobs",
            type=int,
            default=10,
            help="Max jobs per page (default: 10)",
        )
        parser.add_argument(
            "--url",
            type=str,
            default=None,
            help="Override the source URL (defaults to JOBSTREET_ICT_URL)",
        )
        parser.add_argument(
            "--start-page",
            type=int,
            default=1,
            help=(
                "Page to begin at (default: 1). Use it to resume a crawl that "
                "was stopped: everything up to the last page the previous run "
                "reported saved is already stored."
            ),
        )
        parser.add_argument(
            "--skip-skill-gap-refresh",
            action="store_true",
            help=(
                "Do not re-record student skill gaps after the scrape. "
                "Use when running several scrapes back to back."
            ),
        )

    def handle(self, *args, **options):
        max_pages  = options["max_pages"]
        max_jobs   = options["max_jobs"]
        start_page = options["start_page"]
        source_url = options["url"] or JOBSTREET_ICT_URL

        if start_page < 1:
            raise CommandError("--start-page is a page number, so it starts at 1.")
        if start_page > max_pages:
            raise CommandError(
                f"--start-page {start_page} is past the --max-pages ceiling of "
                f"{max_pages}, so there is nothing to crawl. Raise --max-pages.")

        self.stdout.write(self.style.MIGRATE_HEADING("\nMomentumQuest Job Scraper"))
        self.stdout.write(f"  Source    : {source_url}")
        self.stdout.write(f"  Pages     : {start_page} to {max_pages} (ceiling)")
        self.stdout.write(f"  Max jobs  : {max_jobs} per page\n")

        # Retrying, because this is the run's first query and a burst landing
        # here kills a crawl that has not started. refresh_market_data does the
        # same before its lock; this covers the command run on its own.
        db.ensure()

        log = create_scrape_log(roles_scraped=[source_url])
        error_message = ""
        status = "FAILED"
        created_count = updated_count = blocked_count = jobs_scraped = 0
        blocked_adverts = 0
        pages_attempted = pages_with_results = pages_truncated = 0
        last_page_saved = None
        # A crash is a technical failure, and never an exhausted search.
        stop_reason = pagination.FAILED

        # Built once, while there is still a connection, and reused for every
        # page. Rebuilding it per page would read the whole Market Role
        # taxonomy a hundred and thirty times over one crawl.
        role_index = build_index()

        def save_page(page, page_jobs):
            """Persist one page's adverts, then let the connection go again.

            Called by the scraper the moment a page is in hand. This is what
            makes the crawl resumable: everything up to the last completed page
            is already in the database, so an interrupt, a dead browser or a
            dropped network costs one page rather than the run.

            The connection is opened per page and released straight after for
            the reason in scrape_jobs.db -- the gap until the next page is
            minutes of no database work, which is exactly what gets dropped.
            """
            nonlocal created_count, updated_count, jobs_scraped
            nonlocal pages_with_results, last_page_saved

            db.reconnect()
            try:
                created, updated = save_scraped_jobs(page_jobs, index=role_index)
            finally:
                db.release()

            created_count += created
            updated_count += updated
            jobs_scraped += len(page_jobs)
            pages_with_results += 1
            last_page_saved = page
            self.stdout.write(
                f"  Page {page}: saved {created} new, {updated} updated "
                f"({jobs_scraped} adverts so far)")

        def announce_resume():
            """Say where to pick up, before anything that needs the database.

            Printed first, and to stdout, because the failure that ends a long
            crawl is very often the database becoming unreachable -- and then
            the ScrapeLog row recording where to resume is precisely the thing
            that cannot be written. A run that saved three pages and died on
            the fourth said nothing at all about those three, because the
            resume line lived in a summary the command never reached.
            """
            if last_page_saved is None:
                return
            self.stdout.write(self.style.WARNING(
                f"  Saved through page {last_page_saved}. Resume with "
                f"--start-page {last_page_saved + 1}"))

        try:
            # The crawl makes no database query and runs for as long as the
            # source takes. Holding an idle connection across it is what made a
            # long run die on its first write afterwards; see scrape_jobs.db.
            db.release()

            result = scrape_jobs(
                source_url=source_url,
                max_pages=max_pages,
                max_jobs_per_page=max_jobs,
                start_page=start_page,
                on_page=save_page,
            )

            db.reconnect()

            status          = result["status"]
            blocked_count   = result["blocked_count"]
            blocked_adverts = result["blocked_adverts"]
            pages_attempted = result["pages_attempted"]
            pages_truncated = result["pages_truncated"]
            stop_reason     = result["stop_reason"]

            log.roles_scraped = [result.get("source_url", source_url)]

        except KeyboardInterrupt:
            # Not an Exception, so it used to pass straight through this method:
            # the adverts died with the process and the ScrapeLog row was left
            # unfinished, blocking the next run for six hours. Now the pages are
            # already saved and this only has to record why it ended.
            status = "FAILED"
            stop_reason = pagination.INTERRUPTED
            error_message = "Stopped by the operator."
            self.stdout.write(self.style.WARNING("\n  Stopped. Finishing the log..."))
            announce_resume()
            db.reconnect()

        except Exception as exc:
            error_message = str(exc)
            status = "FAILED"
            self.stdout.write(self.style.ERROR(f"Scraper crashed: {exc}"))
            announce_resume()
            # One likely cause of that failure is the connection dying, and the
            # row below is the only record that the run happened at all. Written
            # on the old connection it raises InterfaceError instead, which is
            # how a failed crawl came to leave nothing behind.
            db.reconnect()

        # pages_attempted comes from the scraper on a clean finish; on an
        # interrupt there is no result to read, so count what was saved.
        if not pages_attempted:
            pages_attempted = pages_with_results

        log.pages_attempted = pages_attempted
        log.jobs_scraped    = jobs_scraped
        log.save()

        finish_scrape_log(
            log=log,
            status=status,
            jobs_scraped=jobs_scraped,
            jobs_created=created_count,
            jobs_updated=updated_count,
            blocked_count=blocked_count,
            blocked_adverts=blocked_adverts,
            error_message=error_message,
            pages_with_results=pages_with_results,
            stop_reason=stop_reason,
            start_page=start_page,
            last_page_saved=last_page_saved,
        )

        # Deliberately not gated on pagination_exhausted. Nothing here retires a
        # listing for having gone unseen by this crawl: scraped listings expire
        # on the source's own 30-day posting window, company listings on the
        # closing date the employer published. Both are properties of the advert
        # and hold whether this run read one page or every page, so a partial or
        # blocked crawl cannot expire anything still being advertised.
        #
        # Withholding them until a crawl exhausts pagination is the version that
        # causes harm: blocked runs are expected against this source, so lapsed
        # adverts would stay ACTIVE for months and students would click through
        # to dead postings. A rule that *did* read absence from a crawl as a
        # lapse would need that guard, and pagination_exhausted is on the log
        # ready for it -- but no rule here does.
        expired_count = expire_stale_listings()
        expired_count += expire_closed_company_listings()

        # A scrape is the only thing that moves employer demand, and a skill
        # gap is demand measured against a student's skills -- so the gaps are
        # re-recorded here rather than on a schedule of their own. Running it
        # on a timer would either fire when nothing had changed or lag behind
        # the change that mattered. The other trigger is the student's own
        # side: resources.skill_recognition.apply_skills refreshes one
        # student the moment a skill of theirs is validated.
        market_changed = bool(created_count or updated_count or expired_count)
        gap_summary = "  Gaps    : not refreshed (nothing changed)"
        if market_changed and not options["skip_skill_gap_refresh"]:
            refreshed = self.refresh_skill_gaps()
            gap_summary = (
                f"  Gaps    : {refreshed[0]} opened, {refreshed[1]} closed, "
                f"{refreshed[2]} reopened across {refreshed[3]} student(s)"
            )
        elif options["skip_skill_gap_refresh"]:
            gap_summary = "  Gaps    : skipped (--skip-skill-gap-refresh)"

        exhausted = stop_reason == pagination.PAGINATION_EXHAUSTED

        # Spelled out rather than left to be inferred from a page count,
        # because "it finished and collected 4,000 adverts" reads as
        # completeness and is not. Only the stop reason answers that.
        pagination_summary = (
            f"  Pagination:\n"
            f"    Pages attempted      : {pages_attempted}\n"
            f"    Pages with results   : {pages_with_results}\n"
            f"    Pagination exhausted : {'YES' if exhausted else 'NO'}\n"
            f"    Stop reason          : {stop_reason}"
        )
        if pages_truncated:
            pagination_summary += (
                f"\n    Pages cut by --max-jobs : {pages_truncated} "
                f"(those pages were not read in full)")

        # The page to pick up from, because working it out from a page
        # count and a ceiling is exactly the arithmetic an operator gets
        # wrong at the end of a four-hour run.
        if not exhausted and last_page_saved is not None:
            pagination_summary += (
                f"\n    Resume with          : --start-page {last_page_saved + 1}")

        # Output colour-coded result
        summary = (
            f"  Status  : {status}\n"
            f"  Scraped : {jobs_scraped}  |  Created: {created_count}  |  Updated: {updated_count}\n"
            f"  Blocked : {blocked_count} search page(s), {blocked_adverts} advert(s)\n"
            f"  Expired : {expired_count} lapsed listing(s) closed\n"
            f"{gap_summary}\n"
            f"{pagination_summary}\n"
            f"  Log ID  : {log.pk}"
        )

        if status == "SUCCESS":
            self.stdout.write(self.style.SUCCESS(summary))
        elif status == "PARTIAL":
            self.stdout.write(self.style.WARNING(summary))
        else:
            self.stdout.write(self.style.ERROR(summary))
            if error_message:
                self.stdout.write(self.style.ERROR(f"  Error   : {error_message}"))

    def refresh_skill_gaps(self):
        """Re-record every student's gaps. Returns (opened, closed, reopened, students).

        A failure here must not fail the scrape: the listings are already
        saved, and the live skill-gap view reads them directly. Only the
        historical record lags, and the next scrape re-runs this.
        """
        from accounts.models import Student
        from dashboard.skill_gap_snapshots import refresh_skill_gaps

        opened = closed = reopened = students = 0
        for student in Student.objects.prefetch_related('target_roles'):
            try:
                result = refresh_skill_gaps(student)
            except Exception as exc:
                self.stdout.write(self.style.WARNING(
                    f"  Skill-gap refresh failed for student {student.pk}: {exc}"))
                continue
            if any(result):
                students += 1
            opened, closed, reopened = (
                opened + result[0], closed + result[1], reopened + result[2])
        return opened, closed, reopened, students
