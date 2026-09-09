"""Acquire courses from one provider, then map the catalogue by evidence.

The provider-agnostic counterpart to scrape_coursera_skills. Same two passes,
same checkpointing, same rule: the provider finds courses, and the canonical
skill extractor decides what they teach.

    # what would be searched, and where -- no network
    python manage.py scrape_provider --provider "Microsoft Learn" --limit 10 --plan-only

    # a validation batch, reviewed before anything is mapped in bulk
    python manage.py scrape_provider --provider "Microsoft Learn" \\
        --skills "C#" .NET Azure --no-map

    # the uncovered in-demand skills
    python manage.py scrape_provider --provider "Microsoft Learn" --limit 120

``--no-map`` acquires without mapping, so a batch can be inspected in the
catalogue before it is allowed to produce recommendations.
"""

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count, Q

from resources.models import CourseCatalogue, LearningResource
from resources.providers import (
    AcquisitionInterrupted, acquire, checkpoint_for, get_provider,
    provider_names,
)
from resources.search_terms import phrases_for_skills
from resources.services import map_catalogue_to_skills, save_course_catalogue
from scrape_jobs.models import Skill


class Command(BaseCommand):
    help = "Acquire courses from one provider and map them from course text."

    def add_arguments(self, parser):
        parser.add_argument("--provider", required=True, metavar="NAME",
                            help=f"One of: {', '.join(provider_names())}")
        parser.add_argument("--skills", nargs="+", default=None, metavar="NAME")
        parser.add_argument("--limit", type=int, default=10)
        parser.add_argument("--plan-only", action="store_true", default=False)
        parser.add_argument("--no-map", action="store_true", default=False,
                            help="Acquire only; leave mapping for review.")
        parser.add_argument("--map-only", action="store_true", default=False)
        parser.add_argument("--restart", action="store_true", default=False)

    def _uncovered_in_demand(self, limit):
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
        try:
            provider = get_provider(options["provider"])
        except KeyError as exc:
            raise CommandError(str(exc))

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
            f"\n{provider.name} acquisition"))
        for skill_name, phrase in plan:
            note = "" if skill_name == phrase else f"   <- normalised from {skill_name!r}"
            self.stdout.write(f"  {skill_name:24} search: {phrase!r}{note}")

        if options["plan_only"]:
            self.stdout.write(self.style.SUCCESS(
                f"\n{len(plan)} search(es) planned. Nothing fetched."))
            return

        if not options["map_only"]:
            checkpoint = checkpoint_for(provider.name)
            if options["restart"]:
                checkpoint.clear()

            done = sum(1 for _, phrase in plan if checkpoint.is_done(phrase))
            if done:
                self.stdout.write(
                    f"  Resuming  : {done} of {len(plan)} query(ies) already "
                    f"succeeded and will be skipped")

            def progress(index, total, skill_name, phrase, outcome, found, seen):
                if outcome == "skipped":
                    return
                mark = f"+{found} new" if outcome == "ok" else "FAILED"
                self.stdout.write(
                    f"    [{index}/{total}] {phrase!r}: {mark} (seen {seen})")

            def persist(rows):
                if rows:
                    save_course_catalogue(rows)

            interrupted = None
            try:
                courses = acquire(provider, plan, checkpoint=checkpoint,
                                  on_progress=progress, on_courses=persist)
            except AcquisitionInterrupted as exc:
                interrupted, courses = exc, []

            counts = checkpoint.summary()
            self.stdout.write(self.style.SUCCESS(
                f"  Queries   : {counts.get(checkpoint.SUCCESS, 0)} succeeded, "
                f"{counts.get(checkpoint.FAILED, 0)} failed"))
            if courses:
                created, updated = save_course_catalogue(courses)
                self.stdout.write(self.style.SUCCESS(
                    f"  Catalogue : {len(courses)} distinct course(s) - "
                    f"{created} new, {updated} already known"))
            if interrupted is not None:
                self.stdout.write(self.style.ERROR(f"  Stopped   : {interrupted}"))

        stored = CourseCatalogue.objects.filter(platform=provider.name).count()
        if options["no_map"]:
            self.stdout.write(self.style.WARNING(
                f"  Mapping   : skipped (--no-map). {stored} course(s) stored "
                f"for {provider.name}; review before mapping."))
            return

        mapped, remapped, unmapped = map_catalogue_to_skills(
            platform_name=provider.name)
        self.stdout.write(self.style.SUCCESS(
            f"  Mapped    : {mapped} new resource(s), {remapped} updated"))
        self.stdout.write(
            f"  Unmapped  : {unmapped} course(s) matched no known skill "
            f"({stored} stored for {provider.name}; "
            f"{LearningResource.objects.count()} resources in total)")
