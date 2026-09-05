from collections import defaultdict

from django.core.management.base import BaseCommand
from django.db import transaction

from job_listings.models import JobApplication, JobListing, JobSkill
from scrape_jobs.services import canonical_source_url


class Command(BaseCommand):
    """Merge scraped listings that are the same advert stored more than once.

    JobStreet's per-session tracking made every re-scrape of the same advert
    look like a new posting (see canonical_source_url). This collapses the
    existing rows onto one per advert and rewrites source_url to its canonical
    form so the fix holds for future scrapes.

    The survivor is the earliest row, so first-seen dates -- which the demand
    trend uses when a posting carries no posted_date -- are preserved.
    Applications and skills are moved across before anything is deleted.
    """

    help = "Collapse duplicate scraped listings onto one row per advert"

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")

    @transaction.atomic
    def handle(self, *args, **options):
        groups = defaultdict(list)
        listings = (
            JobListing.objects
            .filter(source_type=JobListing.SourceType.SCRAPED)
            .order_by("posted_time", "id")
        )
        for listing in listings:
            groups[canonical_source_url(listing.source_url)].append(listing)

        merged = applications_moved = skills_moved = 0

        for canonical, rows in groups.items():
            survivor = rows[0]
            if survivor.source_url != canonical:
                survivor.source_url = canonical
                survivor.save(update_fields=["source_url"])

            for duplicate in rows[1:]:
                # An application must never be lost to a data cleanup, so it is
                # repointed unless the student already applied to the survivor.
                for application in JobApplication.objects.filter(job=duplicate):
                    clash = JobApplication.objects.filter(
                        job=survivor, student_id=application.student_id).exists()
                    if clash:
                        continue
                    application.job = survivor
                    application.save(update_fields=["job"])
                    applications_moved += 1

                existing = set(
                    JobSkill.objects.filter(job=survivor)
                    .values_list("skill_id", flat=True)
                )
                for job_skill in JobSkill.objects.filter(job=duplicate):
                    if job_skill.skill_id in existing:
                        continue
                    job_skill.job = survivor
                    job_skill.save(update_fields=["job"])
                    existing.add(job_skill.skill_id)
                    skills_moved += 1

                duplicate.delete()
                merged += 1

        if options["dry_run"]:
            transaction.set_rollback(True)
        suffix = " (dry run; rolled back)" if options["dry_run"] else ""
        self.stdout.write(self.style.SUCCESS(
            f"Merged {merged} duplicate listings into {len(groups)} adverts; "
            f"moved {applications_moved} applications and {skills_moved} "
            f"skill links{suffix}."
        ))
