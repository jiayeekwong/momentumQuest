"""Group the Normalized Job Titles no Market Role claims, for review.

Coverage grows by a person reading this list and adding rows to
data/market_roles.csv -- never by loosening the matcher. The output is
deliberately shaped for that: the normalized title on the left, the raw
adverts it came from on the right, so a reviewer can see what the job
actually is before deciding it is a naming variant of a Market Role.

    python manage.py report_unmatched_titles [--min-count N] [--csv PATH]
"""

import collections
import csv
import io

from django.core.management.base import BaseCommand

from job_listings.models import JobListing
from scrape_jobs.market_role_classifier import build_index
from scrape_jobs.title_normalizer import normalize_title, title_without_career_level


class Command(BaseCommand):
    help = "List normalized job titles that no reviewed Market Role mapping covers"

    def add_arguments(self, parser):
        parser.add_argument("--min-count", type=int, default=1)
        parser.add_argument("--limit", type=int, default=200)
        parser.add_argument(
            "--csv", help="Write market_roles.csv-shaped rows here to fill in.")
        parser.add_argument(
            "--include-ambiguous", action="store_true",
            help="Also list titles held back as ambiguous by design.")

    def handle(self, *args, **options):
        index = build_index()
        groups = collections.defaultdict(list)

        query = JobListing.objects.filter(
            source_type=JobListing.SourceType.SCRAPED, market_role__isnull=True)
        if not options["include_ambiguous"]:
            query = query.exclude(
                classification_method=JobListing.ClassificationMethod.AMBIGUOUS)

        for title, method in query.values_list("job_title", "classification_method"):
            key = title_without_career_level(title or "") or normalize_title(title or "")
            if key:
                groups[key].append((title, method))

        rows = sorted(
            ((key, items) for key, items in groups.items()
             if len(items) >= options["min_count"]),
            key=lambda kv: (-len(kv[1]), kv[0]))

        self.stdout.write(
            "%d unmatched normalized titles across %d adverts "
            "(%d reviewed mappings loaded)\n"
            % (len(rows), sum(len(items) for _k, items in rows),
               len(index.by_role) + len(index.by_alias)))

        for key, items in rows[:options["limit"]]:
            self.stdout.write("%4d  %s" % (len(items), key))
            for raw, method in items[:3]:
                self.stdout.write("        %-58s %s" % (raw[:58], method))

        if options["csv"]:
            with io.open(options["csv"], "w", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(["market_role", "normalized_title", "broad_area",
                                 "mapping_type", "notes"])
                for key, items in rows:
                    writer.writerow(["", key, "", "reviewed_alias",
                                     "%d advert(s), e.g. %s"
                                     % (len(items), items[0][0][:80])])
            self.stdout.write(self.style.SUCCESS(
                "\nWrote %d rows to %s — fill in market_role and broad_area, "
                "then append the reviewed ones to data/market_roles.csv."
                % (len(rows), options["csv"])))
