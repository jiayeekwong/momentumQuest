from django.core.management.base import BaseCommand

from jobs.scraper import scrape_jobs, JOBSTREET_ICT_URL
from jobs.services import create_scrape_log, finish_scrape_log, save_scraped_jobs


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

        # Output colour-coded result
        summary = (
            f"  Status  : {status}\n"
            f"  Scraped : {jobs_scraped}  |  Created: {created_count}  |  Updated: {updated_count}\n"
            f"  Blocked : {blocked_count} page(s)\n"
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
