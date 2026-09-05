from django.core.management.base import BaseCommand

from job_listings.expiry import expire_closed_company_listings, expire_stale_listings
from scrape_jobs.scraper import scrape_jobs, JOBSTREET_ICT_URL
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
        source_url = options["url"] or JOBSTREET_ICT_URL

        self.stdout.write(self.style.MIGRATE_HEADING("\nMomentumQuest Job Scraper"))
        self.stdout.write(f"  Source    : {source_url}")
        self.stdout.write(f"  Max pages : {max_pages}")
        self.stdout.write(f"  Max jobs  : {max_jobs} per page\n")

        log = create_scrape_log(roles_scraped=[source_url])
        error_message = ""
        status = "FAILED"
        created_count = updated_count = blocked_count = jobs_scraped = 0

        try:
            result = scrape_jobs(
                source_url=source_url,
                max_pages=max_pages,
                max_jobs_per_page=max_jobs,
            )

            jobs          = result["jobs"]
            status        = result["status"]
            blocked_count = result["blocked_count"]
            jobs_scraped  = len(jobs)

            log.pages_attempted = result["pages_attempted"]
            log.jobs_scraped    = jobs_scraped
            log.roles_scraped   = [result.get("source_url", source_url)]
            log.save()

            created_count, updated_count = save_scraped_jobs(jobs)

        except Exception as exc:
            error_message = str(exc)
            status = "FAILED"
            self.stdout.write(self.style.ERROR(f"Scraper crashed: {exc}"))

        finish_scrape_log(
            log=log,
            status=status,
            jobs_scraped=jobs_scraped,
            jobs_created=created_count,
            jobs_updated=updated_count,
            blocked_count=blocked_count,
            error_message=error_message,
        )

        # Retire listings whose advertisement has lapsed, so students are not
        # sent to "This job is no longer advertised" pages.
        expired_count = expire_stale_listings()
        # Company listings expire on their own published closing date, not on
        # age. Run here too so the one scheduled job keeps both kinds honest.
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

        # Output colour-coded result
        summary = (
            f"  Status  : {status}\n"
            f"  Scraped : {jobs_scraped}  |  Created: {created_count}  |  Updated: {updated_count}\n"
            f"  Blocked : {blocked_count} page(s)\n"
            f"  Expired : {expired_count} lapsed listing(s) closed\n"
            f"{gap_summary}\n"
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
