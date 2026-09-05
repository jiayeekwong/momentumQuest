"""Assign a Market Role to every advert, from its own title and description.

Existing assignments are never translated from a previous taxonomy: each
advert is re-derived from the Raw Job Title and, where the title names a
department rather than a job, from the advert's stated responsibilities. The
scraped data itself is never modified.

    python manage.py classify_market_roles [--all] [--dry-run] [--report PATH]
"""

import collections
import io

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from job_listings.models import JobListing, MarketRoleCandidate
from scrape_jobs.market_role_classifier import (
    METHOD_AMBIGUOUS, METHOD_JD, METHOD_UNCLASSIFIED,
    build_index, classify_listing,
)
from scrape_jobs.title_normalizer import (
    extract_career_level, normalize_title, title_without_career_level,
)

FIELDS = [
    "normalized_job_title", "market_role", "career_level",
    "classification_method", "matched_alias", "classification_evidence",
    "classified_time",
]


class Command(BaseCommand):
    help = "Classify job adverts into Market Roles"

    def add_arguments(self, parser):
        parser.add_argument(
            "--all", action="store_true",
            help="Include company-posted listings (default: scraped only).")
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--report", help="Write a full breakdown to this path.")

    def handle(self, *args, **options):
        index = build_index()
        if not index.by_role:
            self.stderr.write(self.style.ERROR(
                "No active Market Roles. Run load_market_roles first."))
            return

        listings = JobListing.objects.all()
        if not options["all"]:
            listings = listings.filter(source_type=JobListing.SourceType.SCRAPED)

        methods = collections.Counter()
        per_role = collections.Counter()
        unresolved = collections.Counter()
        ambiguous = collections.Counter()
        jd_examples = []
        candidate_rows = []
        updates = []
        now = timezone.now()

        for listing in listings.iterator(chunk_size=500):
            title = listing.job_title or ""
            result = classify_listing(title, listing.description, index)

            listing.normalized_job_title = normalize_title(title)
            listing.career_level = extract_career_level(title)
            listing.market_role = result.market_role
            listing.classification_method = result.method
            listing.matched_alias = result.matched_alias[:250]
            listing.classification_evidence = result.evidence
            listing.classified_time = now
            updates.append(listing)

            methods[result.method] += 1
            if result.market_role is not None:
                per_role[result.market_role.name] += 1
                if result.method == METHOD_JD and len(jd_examples) < 40:
                    jd_examples.append((title, result.market_role.name, result.evidence))
            else:
                key = title_without_career_level(title) or listing.normalized_job_title
                if result.method == METHOD_AMBIGUOUS:
                    ambiguous[key] += 1
                elif result.method == METHOD_UNCLASSIFIED and key:
                    unresolved[key] += 1
            for role in result.candidates:
                candidate_rows.append((listing, role, result.evidence))

        if options["dry_run"]:
            self._summarise(methods, per_role, len(updates))
            self.stdout.write(self.style.WARNING("Dry run — nothing written."))
        else:
            with transaction.atomic():
                for start in range(0, len(updates), 500):
                    JobListing.objects.bulk_update(updates[start:start + 500], FIELDS)
                # Candidates are review material, so a re-run replaces the
                # machine's suggestions but leaves decided rows alone.
                MarketRoleCandidate.objects.filter(
                    status=MarketRoleCandidate.Status.PENDING).delete()
                MarketRoleCandidate.objects.bulk_create(
                    [MarketRoleCandidate(
                        listing=listing, market_role=role,
                        source=MarketRoleCandidate.Source.AMBIGUOUS_TITLE,
                        evidence_excerpt=evidence[:2000])
                     for listing, role, evidence in candidate_rows],
                    ignore_conflicts=True)
            self._summarise(methods, per_role, len(updates))

        if options["report"]:
            self._write_report(options["report"], methods, per_role,
                               unresolved, ambiguous, jd_examples, len(updates))
            self.stdout.write("Report written to %s" % options["report"])

    def _summarise(self, methods, per_role, total):
        classified = sum(per_role.values())
        self.stdout.write(
            "%d adverts: %d classified into %d Market Roles, %d ambiguous, "
            "%d unclassified"
            % (total, classified, len(per_role),
               methods.get(METHOD_AMBIGUOUS, 0), methods.get(METHOD_UNCLASSIFIED, 0)))
        for method, count in methods.most_common():
            self.stdout.write("    %-32s %4d" % (method, count))

    def _write_report(self, path, methods, per_role, unresolved, ambiguous,
                      jd_examples, total):
        from dashboard.views import MIN_LISTINGS_FOR_TARGET as FLOOR

        write = io.open(path, "w", encoding="utf-8").write
        classified = sum(per_role.values())
        at_floor = {name: n for name, n in per_role.items() if n >= FLOOR}

        write("MARKET ROLE CLASSIFICATION\n" + "=" * 74 + "\n\n")
        write("  adverts                : %d\n" % total)
        write("  classified             : %d (%.0f%%)\n"
              % (classified, classified / total * 100 if total else 0))
        write("  ambiguous              : %d\n" % methods.get(METHOD_AMBIGUOUS, 0))
        write("  unclassified           : %d\n" % methods.get(METHOD_UNCLASSIFIED, 0))
        write("  unique Market Roles    : %d\n" % len(per_role))
        write("  meeting evidence floor : %d (>=%d adverts)\n\n" % (len(at_floor), FLOOR))

        write("BY METHOD\n")
        for method, count in methods.most_common():
            write("    %-34s %4d\n" % (method, count))

        write("\nADVERTS PER MARKET ROLE\n")
        for name, count in per_role.most_common():
            write("    %-38s %4d%s\n"
                  % (name, count, "   <- at floor" if count >= FLOOR else ""))

        write("\nJD_RESOLVED EXAMPLES\n")
        for title, role, evidence in jd_examples:
            write("\n    %s\n        -> %s\n        %s\n" % (title, role, evidence))
        if not jd_examples:
            write("    (none)\n")

        write("\nAMBIGUOUS TITLES\n")
        for key, count in ambiguous.most_common(40):
            write("    %4d  %s\n" % (count, key))

        write("\nTOP UNRESOLVED NORMALIZED TITLES\n")
        for key, count in unresolved.most_common(60):
            write("    %4d  %s\n" % (count, key))
