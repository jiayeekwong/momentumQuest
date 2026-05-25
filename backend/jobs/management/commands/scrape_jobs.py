from django.core.management.base import BaseCommand

from jobs.scraper import scrape_jobs
from jobs.services import save_scraped_jobs


class Command(BaseCommand):
    help = "Scrape external job data and save into database"

    def handle(self, *args, **options):
        self.stdout.write("Starting job scraping...")

        jobs = scrape_jobs()
        created_count, updated_count = save_scraped_jobs(jobs)

        self.stdout.write(
            self.style.SUCCESS(
                f"Scraping completed. Created: {created_count}, Updated: {updated_count}"
            )
        )