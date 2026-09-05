"""Scrape Coursera's Computer Science, Information Technology and Data Science
categories into CourseCatalogue, then map the catalogue to skills.

Two passes, deliberately separate. The old `scrape_resources --platforms
coursera` did both at once and kept a course only when a Skill name appeared
literally in its title, so most of what it fetched was discarded at the point
of storing it. Here the network pass keeps every course it finds, and the
mapping pass runs over the database -- so it can be re-run whenever the Skill
table grows, without fetching anything again.

    python manage.py scrape_coursera_categories                 # both passes
    python manage.py scrape_coursera_categories --map-only      # no network
    python manage.py scrape_coursera_categories --categories "Data Science"
"""

from django.core.management.base import BaseCommand

from resources.models import CourseCatalogue
from resources.scraper import COURSERA_CATEGORIES, COURSERA_MAX_PAGES
from resources.services import map_catalogue_to_skills, save_course_catalogue


class Command(BaseCommand):
    help = ("Scrape whole Coursera categories into the course catalogue, "
            "then map catalogue rows to skills.")

    def add_arguments(self, parser):
        parser.add_argument(
            "--categories", nargs="+", default=None, metavar="NAME",
            help=("Coursera category names. Defaults to: "
                  + ", ".join(COURSERA_CATEGORIES)),
        )
        parser.add_argument(
            "--max-pages", type=int, default=COURSERA_MAX_PAGES,
            help=f"Listing pages per category (default {COURSERA_MAX_PAGES}).",
        )
        parser.add_argument(
            "--map-only", action="store_true", default=False,
            help="Skip the network pass and re-map the existing catalogue.",
        )

    def handle(self, *args, **options):
        categories = options["categories"] or list(COURSERA_CATEGORIES)

        self.stdout.write(self.style.MIGRATE_HEADING(
            "\nCoursera category scrape"))
        self.stdout.write(f"  Categories : {', '.join(categories)}")

        if options["map_only"]:
            self.stdout.write("  Network    : skipped (--map-only)\n")
        else:
            # Imported here so --map-only needs no Selenium/Chrome present.
            from resources.scraper import scrape_coursera_categories

            self.stdout.write(f"  Max pages  : {options['max_pages']} per category\n")
            courses = scrape_coursera_categories(
                categories=categories, max_pages=options["max_pages"])
            created, updated = save_course_catalogue(courses)
            self.stdout.write(self.style.SUCCESS(
                f"  Catalogue  : {len(courses)} found — "
                f"{created} new, {updated} updated"))

        mapped, remapped, unmapped = map_catalogue_to_skills(
            platform_name="Coursera", categories=categories)

        total = CourseCatalogue.objects.filter(
            platform="Coursera", is_active=True).count()
        self.stdout.write(self.style.SUCCESS(
            f"  Mapped     : {mapped} new resource(s), {remapped} updated"))
        # Reported rather than hidden: an unmapped course is a gap in the Skill
        # table, not a wasted fetch, and it stays available to a later re-map.
        self.stdout.write(
            f"  Unmapped   : {unmapped} course(s) matched no known skill "
            f"(kept in catalogue; {total} courses stored in total)")
