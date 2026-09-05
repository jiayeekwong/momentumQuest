"""Load the reviewed Market Role mapping from data/market_roles.csv.

The CSV is the source of truth for role grouping, not this database table:
one reviewable, diffable, reproducible artifact rather than mappings scattered
through Python conditionals. Running this command makes the database match it.

    python manage.py load_market_roles [--prune] [--dry-run]
"""

import csv
import io
import os

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from scrape_jobs.models import MarketRole, MarketRoleAlias
from scrape_jobs.title_normalizer import normalize_title

DEFAULT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data", "market_roles.csv",
)

REQUIRED_COLUMNS = {"market_role", "normalized_title", "broad_area", "mapping_type"}

#: Broad Area is presentation metadata only, but its display order is not
#: arbitrary: students browse from building software outwards.
AREA_ORDER = (
    "Software & Applications",
    "Data & AI",
    "Infrastructure & Cloud",
    "Cybersecurity",
    "Operations & Support",
    "Business & Delivery",
)


class Command(BaseCommand):
    help = "Load Market Roles and reviewed aliases from data/market_roles.csv"

    def add_arguments(self, parser):
        parser.add_argument("--path", default=DEFAULT_PATH)
        parser.add_argument(
            "--prune", action="store_true",
            help="Deactivate roles and delete aliases absent from the CSV.")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        path = options["path"]
        if not os.path.exists(path):
            raise CommandError(f"Mapping file not found: {path}")

        with io.open(path, encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        if not rows:
            raise CommandError("Mapping file is empty.")
        missing = REQUIRED_COLUMNS - set(rows[0])
        if missing:
            raise CommandError("Missing column(s): " + ", ".join(sorted(missing)))

        # Validate the whole file before writing any of it -- a half-loaded
        # taxonomy classifies adverts inconsistently.
        seen_titles = {}
        role_areas = {}
        errors = []
        for number, row in enumerate(rows, start=2):
            role_name = (row.get("market_role") or "").strip()
            raw_title = (row.get("normalized_title") or "").strip()
            area = (row.get("broad_area") or "").strip()
            mapping = (row.get("mapping_type") or "").strip() or "reviewed_alias"
            if not role_name or not raw_title:
                errors.append(f"line {number}: market_role and normalized_title are required")
                continue
            if mapping not in dict(MarketRoleAlias.MappingType.choices):
                errors.append(f"line {number}: unknown mapping_type '{mapping}'")
            key = normalize_title(raw_title)
            if not key:
                errors.append(f"line {number}: '{raw_title}' normalizes to nothing")
                continue
            if key in seen_titles and seen_titles[key] != role_name:
                errors.append(
                    f"line {number}: '{key}' is mapped to both "
                    f"{seen_titles[key]} and {role_name}")
            seen_titles[key] = role_name
            role_areas.setdefault(role_name, area)

        if errors:
            raise CommandError("\n".join(errors))

        created_roles = updated_roles = 0
        created_aliases = updated_aliases = 0
        roles = {}

        with transaction.atomic():
            for order, (role_name, area) in enumerate(
                    sorted(role_areas.items(),
                           key=lambda kv: (AREA_ORDER.index(kv[1])
                                           if kv[1] in AREA_ORDER else len(AREA_ORDER),
                                           kv[0]))):
                role, created = MarketRole.objects.update_or_create(
                    name=role_name,
                    defaults={
                        "normalized_name": normalize_title(role_name),
                        "broad_area": area,
                        "is_active": True,
                        "display_order": order,
                    },
                )
                roles[role_name] = role
                created_roles += int(created)
                updated_roles += int(not created)

            for row in rows:
                role_name = (row.get("market_role") or "").strip()
                key = normalize_title((row.get("normalized_title") or "").strip())
                if not role_name or not key:
                    continue
                _alias, created = MarketRoleAlias.objects.update_or_create(
                    normalized_title=key,
                    defaults={
                        "market_role": roles[role_name],
                        "mapping_type": (row.get("mapping_type") or "").strip()
                                        or MarketRoleAlias.MappingType.REVIEWED_ALIAS,
                        "reviewed": True,
                        "notes": (row.get("notes") or "").strip()[:255],
                    },
                )
                created_aliases += int(created)
                updated_aliases += int(not created)

            pruned_roles = pruned_aliases = 0
            if options["prune"]:
                pruned_aliases = (MarketRoleAlias.objects
                                  .exclude(normalized_title__in=seen_titles)
                                  .delete()[0])
                pruned_roles = (MarketRole.objects
                                .exclude(name__in=role_areas)
                                .update(is_active=False))

            if options["dry_run"]:
                transaction.set_rollback(True)

        self.stdout.write(self.style.SUCCESS(
            "Market Roles: %d created, %d updated%s\n"
            "Reviewed aliases: %d created, %d updated%s%s"
            % (created_roles, updated_roles,
               f", {pruned_roles} deactivated" if options["prune"] else "",
               created_aliases, updated_aliases,
               f", {pruned_aliases} removed" if options["prune"] else "",
               "  (dry run, rolled back)" if options["dry_run"] else "")))
