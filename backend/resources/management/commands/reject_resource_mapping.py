"""Record that a reviewed Skill<->Resource pairing is wrong.

For the cases lexical matching cannot fix. "2026 AI SEO Tools And Techniques
(LLM SEO, GEO, AEO)" genuinely contains "LLM" in its title, and is a
search-marketing course; no boundary rule or alias flag separates that from a
course about language models, because the string really is there.

A rejection is durable and reviewable. It survives offline remapping, travels
in the seed files, and carries the reason so whoever revisits it can see what
was decided and why.

    python manage.py reject_resource_mapping --skill LLM \\
        --url https://www.coursera.org/learn/... \\
        --reason "Search-marketing course; LLM appears as SEO jargon."

    python manage.py reject_resource_mapping --skill LLM --url ... --undo
    python manage.py reject_resource_mapping --list

Nothing here touches the extractor. The general rules stay general, and the
exceptions a person has ruled on live in data.
"""

from django.core.management.base import BaseCommand, CommandError

from resources.models import LearningResource, RejectedResourceMapping
from scrape_jobs.models import Skill


class Command(BaseCommand):
    help = "Record or remove a reviewed rejection of one Skill<->Resource pairing."

    def add_arguments(self, parser):
        parser.add_argument("--skill", metavar="NAME",
                            help="Canonical skill name.")
        parser.add_argument("--url", metavar="URL",
                            help="The course's canonical URL.")
        parser.add_argument("--reason", default="", metavar="TEXT",
                            help="Why this pairing is wrong. Worth writing.")
        parser.add_argument("--undo", action="store_true", default=False,
                            help="Remove an existing rejection.")
        parser.add_argument("--list", action="store_true", default=False,
                            help="Show every recorded rejection.")

    def handle(self, *args, **options):
        if options["list"]:
            rows = RejectedResourceMapping.objects.select_related("skill")
            if not rows:
                self.stdout.write("No rejections recorded.")
                return
            for row in rows:
                self.stdout.write(f"  {row.skill.skill_name:24} {row.url}")
                if row.reason:
                    self.stdout.write(f"      {row.reason}")
            return

        if not options["skill"] or not options["url"]:
            raise CommandError("--skill and --url are both required.")

        skill = Skill.objects.filter(skill_name__iexact=options["skill"]).first()
        if skill is None:
            raise CommandError(f"No such canonical skill: {options['skill']!r}")

        url = options["url"].strip()

        if options["undo"]:
            removed, _ = RejectedResourceMapping.objects.filter(
                skill=skill, url=url).delete()
            self.stdout.write(self.style.SUCCESS(
                f"Removed {removed} rejection(s). The next mapping pass may "
                f"restore this pairing if the course text still supports it."))
            return

        RejectedResourceMapping.objects.update_or_create(
            skill=skill, url=url, defaults={"reason": options["reason"]})

        # The existing row goes now rather than at the next mapping pass, so a
        # rejection takes effect for students immediately.
        dropped, _ = LearningResource.objects.filter(skill=skill, url=url).delete()

        self.stdout.write(self.style.SUCCESS(
            f"Rejected {skill.skill_name} x {url}"))
        self.stdout.write(
            f"  {dropped} existing resource row(s) removed. Run "
            f"export_resources to put the decision in the seed files.")
