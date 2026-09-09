"""Search Coursera once per uncovered in-demand skill, then map by evidence.

Two passes, deliberately separate. The network pass keeps every course it
sees; the mapping pass decides what each course teaches from the course's own
text, and can be re-run over the stored catalogue without fetching anything.

Nothing here maps a course to the skill that found it. The search phrase is a
retrieval device only -- see resources/search_terms.py for why the phrase and
the canonical identity are kept apart.

    # the validation batch, reviewed by hand before scaling
    python manage.py scrape_coursera_skills --skills UAT "C#" ERP ABAP

    # the highest-demand uncovered skills, most in demand first
    python manage.py scrape_coursera_skills --limit 25

    # what would be searched, and for what phrase -- no network
    python manage.py scrape_coursera_skills --limit 25 --plan-only

    # re-map the stored catalogue after the Skill table changes
    python manage.py scrape_coursera_skills --map-only
"""

from django.core.management.base import BaseCommand
from django.db.models import Count, Q

from resources.acquisition_state import AcquisitionCheckpoint
from resources.models import CourseCatalogue, LearningResource
from resources.search_terms import phrases_for_skills
from resources.services import map_catalogue_to_skills, save_course_catalogue
from scrape_jobs.models import Skill


class Command(BaseCommand):
    help = ("Search Coursera per uncovered in-demand skill and map the results "
            "from course text.")

    def add_arguments(self, parser):
        parser.add_argument(
            "--skills", nargs="+", default=None, metavar="NAME",
            help="Specific canonical skill names. Overrides --limit.")
        parser.add_argument(
            "--limit", type=int, default=10,
            help="How many uncovered in-demand skills to search (default 10).")
        parser.add_argument(
            "--plan-only", action="store_true", default=False,
            help="Print the skill/phrase plan and stop. No network.")
        parser.add_argument(
            "--map-only", action="store_true", default=False,
            help="Skip the network pass and re-map the stored catalogue.")
        parser.add_argument(
            "--restart", action="store_true", default=False,
            help=("Discard the checkpoint and search every query again. "
                  "Without it, queries that already succeeded are skipped."))
        parser.add_argument(
            "--checkpoint", default="coursera_skills", metavar="NAME",
            help="Checkpoint file name (default: coursera_skills).")

    # ------------------------------------------------------------------
    # Which skills are worth a search
    # ------------------------------------------------------------------

    def _uncovered_in_demand(self, limit):
        """In-demand skills with no learning resource, most in demand first.

        Demand is counted from scraped adverts, which is the only reason to
        spend a request on a skill at all: a catalogue entry nobody advertises
        for is not a gap a student can feel.
        """
        return list(
            Skill.objects
            .annotate(
                demand=Count("job_skills",
                             filter=Q(job_skills__job__source_type="SCRAPED"),
                             distinct=True),
                covered=Count("learning_resources", distinct=True),
            )
            .filter(demand__gt=0, covered=0, is_active=True)
            .order_by("-demand", "skill_name")[:limit]
        )

    def handle(self, *args, **options):
        if options["skills"]:
            skills = list(Skill.objects.filter(skill_name__in=options["skills"]))
            missing = set(options["skills"]) - {s.skill_name for s in skills}
            if missing:
                self.stdout.write(self.style.WARNING(
                    f"  Not canonical skills, skipped: {sorted(missing)}"))
        else:
            skills = self._uncovered_in_demand(options["limit"])

        plan = phrases_for_skills(skills)

        self.stdout.write(self.style.MIGRATE_HEADING(
            "\nCoursera skill search"))
        for skill_name, phrase in plan:
            note = "" if skill_name == phrase else f"   <- normalised from {skill_name!r}"
            self.stdout.write(f"  {skill_name:24} search: {phrase!r}{note}")

        if options["plan_only"]:
            self.stdout.write(self.style.SUCCESS(
                f"\n{len(plan)} search(es) planned. Nothing fetched."))
            return

        if not options["map_only"]:
            # Imported here so --plan-only and --map-only need no Selenium.
            from resources.scraper import (AcquisitionInterrupted,
                                           scrape_coursera_for_phrases)

            checkpoint = AcquisitionCheckpoint(options["checkpoint"])
            if options["restart"]:
                checkpoint.clear()

            # A phrase that has been corrected leaves its old key behind, and
            # an orphaned FAILED entry reports a failure no rerun can clear.
            # Only safe when the plan is the whole catalogue; a --skills run
            # covers a handful and would prune everything else.
            if not options["skills"]:
                dropped = checkpoint.prune(phrase for _, phrase in plan)
                if dropped:
                    self.stdout.write(self.style.WARNING(
                        f"  Pruned    : {len(dropped)} stale checkpoint "
                        f"entr(ies) for phrases no longer searched: "
                        f"{', '.join(repr(d) for d in dropped[:5])}"))

            done = sum(1 for _, phrase in plan if checkpoint.is_done(phrase))
            if done:
                self.stdout.write(
                    f"  Resuming  : {done} of {len(plan)} query(ies) already "
                    f"succeeded and will be skipped")

            def progress(index, total_queries, skill_name, phrase, outcome,
                         found, total):
                if outcome == "skipped":
                    return
                mark = "+%d new" % found if outcome == "ok" else "FAILED"
                self.stdout.write(
                    f"    [{index}/{total_queries}] {phrase!r}: {mark} "
                    f"(catalogue {total})")

            # Saved per query, not at the end: a run that dies must not lose
            # the courses its checkpoint has already called SUCCESS.
            def persist(rows):
                if rows:
                    save_course_catalogue(rows)

            interrupted = None
            try:
                courses = scrape_coursera_for_phrases(
                    plan, checkpoint=checkpoint, on_progress=progress,
                    on_courses=persist)
            except AcquisitionInterrupted as exc:
                interrupted = exc
                courses = []

            counts = checkpoint.summary()
            self.stdout.write(self.style.SUCCESS(
                f"  Queries   : {counts.get(checkpoint.SUCCESS, 0)} succeeded, "
                f"{counts.get(checkpoint.FAILED, 0)} failed"))
            if courses:
                created, updated = save_course_catalogue(courses)
                self.stdout.write(self.style.SUCCESS(
                    f"  Catalogue : {len(courses)} distinct course(s) — "
                    f"{created} new, {updated} already known"))

            failures = checkpoint.failures()
            if failures:
                self.stdout.write(self.style.WARNING(
                    f"  Failed    : {len(failures)} query(ies); rerun to retry"))
                for phrase, row in list(failures.items())[:8]:
                    self.stdout.write(f"      {phrase!r}: {row['reason'][:90]}")

            if interrupted is not None:
                # Mapping is still run below: the courses already fetched are
                # worth mapping, and the command reports the interruption.
                self.stdout.write(self.style.ERROR(f"  Stopped   : {interrupted}"))

        mapped, remapped, unmapped = map_catalogue_to_skills(
            platform_name="Coursera")

        self.stdout.write(self.style.SUCCESS(
            f"  Mapped    : {mapped} new resource(s), {remapped} updated"))
        # An unmapped course is a gap in the Skill table, not a wasted fetch: it
        # stays in the catalogue and a later re-map can pick it up.
        self.stdout.write(
            f"  Unmapped  : {unmapped} course(s) matched no known skill "
            f"(catalogue holds {CourseCatalogue.objects.count()}; "
            f"{LearningResource.objects.count()} resources total)")
