import csv
from pathlib import Path

from django.core.management.base import BaseCommand

from scrape_jobs.models import Skill


class Command(BaseCommand):
    help = "Import CS skills from CSV into the Skill table"

    def handle(self, *args, **options):
        csv_path = Path(__file__).resolve().parents[3] / "scrape_jobs" / "data" / "cs_skills.csv"

        if not csv_path.exists():
            self.stdout.write(
                self.style.ERROR(f"CSV file not found: {csv_path}")
            )
            return

        created_count = 0
        updated_count = 0

        with open(csv_path, mode="r", encoding="utf-8") as file:
            reader = csv.DictReader(file)

            for row in reader:
                skill_name = row["skill_name"].strip()
                skill_category = row["skill_category"].strip()

                if not skill_name:
                    continue

                skill, created = Skill.objects.update_or_create(
                    skill_name=skill_name,
                    defaults={
                        "skill_category": skill_category,
                    },
                )

                if created:
                    created_count += 1
                else:
                    updated_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Skills imported successfully. Created: {created_count}, Updated: {updated_count}"
            )
        )