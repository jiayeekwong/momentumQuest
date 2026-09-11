"""Load the reviewed Market Role mapping from data/market_roles.csv.

The CSV is the source of truth for role grouping, not this database table:
one reviewable, diffable, reproducible artifact rather than mappings scattered
through Python conditionals. Running this command makes the database match it.

    python manage.py load_market_roles [--prune] [--dry-run]
    python manage.py load_market_roles --check

``--check`` compares the database against the file and changes nothing, which is
the same guarantee export_skills and export_resources already give their seeds.
Market roles went without it for a while and drifted: three reviewed
MALAYSIA_TITLE_REVIEW aliases and one IMDA_MARKET_EXTENSION role were approved
into a database and never written back, so a fresh deployment would have
silently classified those adverts differently from the one they were reviewed
on. Nothing detected it, because nothing was looking.

The comparison is built from the file and the rules in this module, so it covers
the metadata the CSV carries -- broad area, mapping type, catalogue origin,
alias source and review status -- and is ordered in Python rather than by the
database, whose collation sorts differently from codepoint order.
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

#: Reviewed provenance, carried in the file so a fresh database reproduces it.
#: Optional with defaults rather than required: a hand-written row that omits
#: them still loads deterministically, and --check is what guarantees the file
#: and the database agree.
DEFAULT_CATALOGUE_ORIGIN = "MARKET_DERIVED"
DEFAULT_ALIAS_SOURCE = "LEGACY"
DEFAULT_REVIEW_STATUS = "APPROVED"

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
        parser.add_argument(
            "--check", action="store_true",
            help=("Compare the database against the file and exit non-zero on "
                  "any difference. Changes nothing."))

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
        role_origins = {}
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
            role_origins.setdefault(
                role_name,
                (row.get("catalogue_origin") or "").strip()
                or DEFAULT_CATALOGUE_ORIGIN)

        if errors:
            raise CommandError("\n".join(errors))

        if options["check"]:
            self._check(role_areas, role_origins, rows)
            return

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
                        "catalogue_origin": role_origins.get(
                            role_name, DEFAULT_CATALOGUE_ORIGIN),
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
                        "source": (row.get("source") or "").strip()
                                  or DEFAULT_ALIAS_SOURCE,
                        "review_status": (row.get("review_status") or "").strip()
                                         or DEFAULT_REVIEW_STATUS,
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

    # ------------------------------------------------------------------ check

    def _expected(self, role_areas, role_origins, rows):
        """What the database should hold, derived from the file alone.

        Built with the same ordering rule the loader applies, so display_order
        is part of the comparison rather than something it cannot see.
        """
        roles = {}
        for order, (role_name, area) in enumerate(
                sorted(role_areas.items(),
                       key=lambda kv: (AREA_ORDER.index(kv[1])
                                       if kv[1] in AREA_ORDER else len(AREA_ORDER),
                                       kv[0]))):
            roles[role_name] = {
                "normalized_name": normalize_title(role_name),
                "broad_area": area,
                "catalogue_origin": role_origins.get(
                    role_name, DEFAULT_CATALOGUE_ORIGIN),
                "display_order": order,
                "is_active": True,
            }

        aliases = {}
        for row in rows:
            role_name = (row.get("market_role") or "").strip()
            key = normalize_title((row.get("normalized_title") or "").strip())
            if not role_name or not key:
                continue
            aliases[key] = {
                "market_role": role_name,
                "mapping_type": (row.get("mapping_type") or "").strip()
                                or MarketRoleAlias.MappingType.REVIEWED_ALIAS,
                "source": (row.get("source") or "").strip()
                          or DEFAULT_ALIAS_SOURCE,
                "review_status": (row.get("review_status") or "").strip()
                                 or DEFAULT_REVIEW_STATUS,
                "reviewed": True,
                "notes": (row.get("notes") or "").strip()[:255],
            }
        return roles, aliases

    def _actual(self):
        roles = {
            row["name"]: {
                "normalized_name": row["normalized_name"],
                "broad_area": row["broad_area"],
                "catalogue_origin": row["catalogue_origin"],
                "display_order": row["display_order"],
                "is_active": row["is_active"],
            }
            for row in MarketRole.objects.values(
                "name", "normalized_name", "broad_area", "catalogue_origin",
                "display_order", "is_active")
        }
        aliases = {
            row["normalized_title"]: {
                "market_role": row["market_role__name"],
                "mapping_type": row["mapping_type"],
                "source": row["source"],
                "review_status": row["review_status"],
                "reviewed": row["reviewed"],
                "notes": row["notes"] or "",
            }
            for row in MarketRoleAlias.objects.select_related("market_role")
            .values("normalized_title", "market_role__name", "mapping_type",
                    "source", "review_status", "reviewed", "notes")
        }
        return roles, aliases

    def _check(self, role_areas, role_origins, rows):
        expected_roles, expected_aliases = self._expected(
            role_areas, role_origins, rows)
        actual_roles, actual_aliases = self._actual()

        problems = []

        # sorted() in Python, not ORDER BY: PostgreSQL's collation and codepoint
        # order disagree, and a check whose output depends on the server's locale
        # is a check that reports differently on the machine it matters on.
        for name in sorted(set(expected_roles) - set(actual_roles)):
            problems.append(f"role missing from the database: {name}")
        for name in sorted(set(actual_roles) - set(expected_roles)):
            problems.append(f"role in the database but not the seed: {name}")
        for name in sorted(set(expected_roles) & set(actual_roles)):
            for field, want in sorted(expected_roles[name].items()):
                got = actual_roles[name][field]
                if got != want:
                    problems.append(
                        f"role {name}: {field} is {got!r}, seed says {want!r}")

        for title in sorted(set(expected_aliases) - set(actual_aliases)):
            problems.append(f"alias missing from the database: {title}")
        for title in sorted(set(actual_aliases) - set(expected_aliases)):
            problems.append(f"alias in the database but not the seed: {title}")
        for title in sorted(set(expected_aliases) & set(actual_aliases)):
            for field, want in sorted(expected_aliases[title].items()):
                got = actual_aliases[title][field]
                if got != want:
                    problems.append(
                        f"alias {title}: {field} is {got!r}, seed says {want!r}")

        if problems:
            shown = problems[:25]
            more = len(problems) - len(shown)
            joined = ("\n    ").join(shown)
            tail = f"\n    ... and {more} more" if more else ""
            raise CommandError(
                "The database does not match data/market_roles.csv:"
                + "\n    " + joined + tail
                + "\n\n        Run load_market_roles to apply the seed, "
                  "or update the seed if the database holds a reviewed decision "
                  "the file has not caught up with.")

        self.stdout.write(self.style.SUCCESS(
            "Market Role seed matches the database: "
            f"{len(expected_roles)} role(s), {len(expected_aliases)} alias(es)."))
