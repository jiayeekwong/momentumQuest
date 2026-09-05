"""Rebuild StudentSkill from the evidence that currently backs it.

StudentSkill is a materialized result. Every decision that changes evidence
already recalculates the skills it touched, so this command exists for the
cases where that did not happen: rows written before the evidence model, a
bulk data correction, or verifying after a migration that the stored levels
still match what the evidence says.

    python manage.py recalculate_skills [--student <id>] [--dry-run]

Skills with no recorded provenance are left alone. Transcripts uploaded before
issuer verification existed applied skills without recording where they came
from, so deleting those would be guessing rather than recalculating; --strict
includes them, and reports what it would remove.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.models import Student, StudentSkill
from resources.skill_evidence import (
    evidenced_skill_ids, live_skill_levels, recalculate_student_skills,
)


class Command(BaseCommand):
    help = "Rebuild StudentSkill rows from live certificate and transcript evidence"

    def add_arguments(self, parser):
        parser.add_argument("--student", type=int, help="Limit to one student id.")
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument(
            "--strict", action="store_true",
            help="Also remove skills with no recorded provenance.")

    def handle(self, *args, **options):
        students = Student.objects.all()
        if options["student"]:
            students = students.filter(pk=options["student"])

        totals = {"created": 0, "updated": 0, "removed": 0}
        unprovenanced = 0

        with transaction.atomic():
            for student in students.iterator(chunk_size=200):
                held = set(
                    StudentSkill.objects.filter(student=student)
                    .values_list("skill_id", flat=True))
                evidenced = evidenced_skill_ids(student)
                orphans = held - evidenced
                unprovenanced += len(orphans)

                if options["strict"] and orphans:
                    from scrape_jobs.models import Skill
                    scope = list(Skill.objects.filter(
                        pk__in=held | set(live_skill_levels(student))))
                    result = recalculate_student_skills(student, skills=scope)
                else:
                    result = recalculate_student_skills(student)

                for key in totals:
                    totals[key] += result[key]

            if options["dry_run"]:
                transaction.set_rollback(True)

        self.stdout.write(self.style.SUCCESS(
            "%d created, %d updated, %d removed%s"
            % (totals["created"], totals["updated"], totals["removed"],
               "  (dry run, rolled back)" if options["dry_run"] else "")))
        if unprovenanced:
            self.stdout.write(self.style.WARNING(
                "%d skill(s) have no recorded provenance and were %s. "
                "They predate evidence tracking; re-run with --strict to "
                "remove them." % (
                    unprovenanced,
                    "removed" if options["strict"] else "left in place")))
