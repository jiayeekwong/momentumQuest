from django.core.management.base import BaseCommand
from django.utils import timezone

from jobs.models import Skill, ScrapeLog
from jobs.resources_scraper import PLATFORM_DISPLAY_NAMES, PLATFORM_SCRAPERS, scrape_learning_resources
from jobs.services import (
    create_scrape_log, deactivate_stale_resources,
    finish_scrape_log, save_learning_resources,
)

DAYS_THRESHOLD = 30


def is_scrape_needed():
    last = (
        ScrapeLog.objects
        .filter(status__in=["SUCCESS", "PARTIAL"])
        .order_by("-finished_at")
        .first()
    )
    if not last or not last.finished_at:
        return True
    return (timezone.now() - last.finished_at).days >= DAYS_THRESHOLD


class Command(BaseCommand):
    help = "Scrape learning resources from external platforms and save to database"

    def add_arguments(self, parser):
        parser.add_argument(
            "--platforms",
            nargs="+",
            default=None,
            metavar="PLATFORM",
            help=(
                "Platforms to scrape. Choices: "
                + ", ".join(PLATFORM_SCRAPERS.keys())
                + ". Defaults to all."
            ),
        )
        parser.add_argument(
            "--skills",
            nargs="+",
            default=None,
            metavar="SKILL",
            help="Specific skill names to scrape for, e.g. --skills Python SQL React",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            default=False,
            help=f"Run even if last scrape was less than {DAYS_THRESHOLD} days ago.",
        )

    def handle(self, *args, **options):
        force        = options["force"]
        platforms    = options["platforms"]
        skill_filter = options["skills"]

        # Frequency check — skip if scraped recently unless --force
        if not force and not is_scrape_needed():
            self.stdout.write(self.style.WARNING(
                f"Skipped: last successful scrape was less than {DAYS_THRESHOLD} days ago. "
                "Use --force to override."
            ))
            return

        # Load skill names from DB
        qs = Skill.objects.all()
        if skill_filter:
            qs = qs.filter(skill_name__in=skill_filter)
        skill_names = list(qs.values_list("skill_name", flat=True))

        if not skill_names:
            self.stdout.write(self.style.ERROR(
                "No skills found in database. Seed the Skill table first."
            ))
            return

        active_platforms = platforms or list(PLATFORM_SCRAPERS.keys())

        self.stdout.write(self.style.MIGRATE_HEADING("\nMomentumQuest Resource Scraper"))
        self.stdout.write(f"  Skills    : {len(skill_names)} skills")
        self.stdout.write(f"  Platforms : {', '.join(active_platforms)}\n")

        log = create_scrape_log(roles_scraped=active_platforms)
        error_message = ""
        status = "FAILED"
        created_count = updated_count = deactivated_total = 0
        resources = []
        errors = []

        try:
            result = scrape_learning_resources(skill_names, platforms=active_platforms)

            resources       = result["resources"]
            status          = result["status"]
            errors          = result["errors"]
            platform_counts = result["platform_counts"]

            for platform, count in platform_counts.items():
                self.stdout.write(f"  {platform:<20}: {count} resources found")

            log.pages_attempted = len(active_platforms)
            log.jobs_scraped    = len(resources)
            log.roles_scraped   = active_platforms
            log.save()

            created_count, updated_count = save_learning_resources(resources)

            # Deactivate stale resources — only for platforms that scraped successfully
            successfully_scraped = [p for p in active_platforms if p not in errors]
            for platform_key in successfully_scraped:
                platform_name = PLATFORM_DISPLAY_NAMES.get(platform_key, platform_key)
                active_urls   = {r["url"] for r in resources if r["platform"] == platform_name}
                deactivated_total += deactivate_stale_resources(platform_name, active_urls)

            if errors:
                error_message = f"Failed platforms: {', '.join(errors)}"

        except Exception as exc:
            error_message = str(exc)
            status = "FAILED"
            self.stdout.write(self.style.ERROR(f"Scraper crashed: {exc}"))

        finish_scrape_log(
            log=log,
            status=status,
            jobs_scraped=created_count + updated_count,
            jobs_created=created_count,
            jobs_updated=updated_count,
            blocked_count=0,
            error_message=error_message,
        )

        summary = (
            f"\n  Status     : {status}\n"
            f"  Created    : {created_count}  |  Updated: {updated_count}  |  Deactivated: {deactivated_total}\n"
            f"  Log ID     : {log.pk}"
        )

        if status == "SUCCESS":
            self.stdout.write(self.style.SUCCESS(summary))
        elif status == "PARTIAL":
            self.stdout.write(self.style.WARNING(summary))
            self.stdout.write(self.style.WARNING(f"  Errors     : {error_message}"))
        else:
            self.stdout.write(self.style.ERROR(summary))
            if error_message:
                self.stdout.write(self.style.ERROR(f"  Error      : {error_message}"))
