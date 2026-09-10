"""Rebuild courses and learning resources from the versioned seed files.

The production bootstrap step. Offline and deterministic: no Chrome, no
Selenium, no outbound network, and the same input always produces the same
recommendations.

    python manage.py migrate
    python manage.py import_skills       # the skill catalogue first
    python manage.py import_resources    # then what is taught, and where

Ordering is not incidental. Resources name skills by string, so the skill
catalogue has to exist first; a resource naming a skill no seed declares is
reported rather than skipped silently, because that is a mismatch between two
files and swallowing it loses a recommendation without saying so.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from resources.models import (
    CourseCatalogue, LearningResource, RejectedResourceMapping,
)
from resources.seeds import (
    COURSES_FILE, DATA_DIR, RESOURCES_FILE, file_snapshot,
)
from scrape_jobs.catalogue import read_bool
from scrape_jobs.models import Skill

import json


class Command(BaseCommand):
    help = "Import courses and learning resources from the versioned CSV seeds"

    def add_arguments(self, parser):
        parser.add_argument(
            "--prune", action="store_true",
            help=("Delete rows absent from the seed files, so the database "
                  "matches the repository exactly."))

    @transaction.atomic
    def handle(self, *args, **options):
        seeds = file_snapshot(DATA_DIR)

        courses = self._load_courses(seeds["courses"])
        # Rejections first: a refusal must be in place before the resources it
        # refuses are considered, or the import would recreate a row that the
        # next mapping pass then removes.
        refusals = self._load_rejections(seeds.get("rejections", []))
        created, updated, skipped = self._load_resources(seeds["resources"])

        self.stdout.write(self.style.SUCCESS(
            f"Courses: {courses[0]} created, {courses[1]} updated. "
            f"Resources: {created} created, {updated} updated. "
            f"Reviewed rejections: {refusals}."))

        if options["prune"]:
            keep_courses = {row["url"] for row in seeds["courses"]}
            keep_pairs = {(row["skill_name"].casefold(), row["url"])
                          for row in seeds["resources"]}
            pruned = CourseCatalogue.objects.exclude(
                url__in=keep_courses).delete()[0]
            for row in LearningResource.objects.select_related("skill"):
                if (row.skill.skill_name.casefold(), row.url) not in keep_pairs:
                    row.delete()
                    pruned += 1
            self.stdout.write(self.style.WARNING(
                f"Pruned {pruned} row(s) not present in the seed files."))

        if skipped:
            self.stdout.write(self.style.WARNING(
                "%d resource(s) name a skill the skill catalogue does not "
                "declare:\n    %s" % (len(skipped), "\n    ".join(skipped[:20]))))

    def _load_courses(self, rows):
        created = updated = 0
        for row in rows:
            if not row.get("url"):
                continue
            _row, was_created = CourseCatalogue.objects.update_or_create(
                url=row["url"],
                defaults={
                    "title": row.get("title", "")[:255],
                    "platform": row.get("platform", "") or "Coursera",
                    "type": row.get("type", "") or "Course",
                    "categories": self._json(row.get("categories")),
                    "discovered_via": self._json(row.get("discovered_via")),
                    "card_text": row.get("card_text", ""),
                    # Blank means the provider never stated a price, and that
                    # must round-trip as NULL rather than becoming False.
                    "is_free": (None if not (row.get("is_free") or "").strip()
                                else read_bool(row["is_free"])),
                    "is_active": read_bool(row.get("is_active")),
                },
            )
            created += int(was_created)
            updated += int(not was_created)
        return created, updated

    def _load_rejections(self, rows):
        """Reviewed refusals, restored before anything is mapped."""
        by_name = {s.skill_name.casefold(): s for s in Skill.objects.all()}
        loaded = 0
        for row in rows:
            skill = by_name.get(row.get("skill_name", "").casefold())
            url = row.get("url", "")
            if skill is None or not url:
                continue
            RejectedResourceMapping.objects.update_or_create(
                skill=skill, url=url,
                defaults={"reason": row.get("reason", "")})
            loaded += 1
        return loaded

    def _load_resources(self, rows):
        # One query, then dict lookups: the file names skills by string and a
        # query per row would be thousands of round trips.
        by_name = {s.skill_name.casefold(): s for s in Skill.objects.all()}
        created = updated = 0
        skipped = []
        for row in rows:
            name = row.get("skill_name", "")
            url = row.get("url", "")
            if not name or not url:
                continue
            skill = by_name.get(name.casefold())
            if skill is None:
                skipped.append(f"{name!r} -> {url}")
                continue
            _row, was_created = LearningResource.objects.update_or_create(
                skill=skill, url=url,
                defaults={
                    "title": row.get("title", "")[:255],
                    "platform": row.get("platform", ""),
                    "type": row.get("type", ""),
                    "is_active": read_bool(row.get("is_active")),
                },
            )
            created += int(was_created)
            updated += int(not was_created)
        return created, updated, skipped

    @staticmethod
    def _json(value):
        try:
            return json.loads(value) if value else []
        except ValueError:
            return []
