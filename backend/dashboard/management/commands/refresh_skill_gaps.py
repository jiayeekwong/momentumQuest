from django.core.management.base import BaseCommand

from accounts.models import Student
from dashboard.skill_gap_snapshots import refresh_skill_gaps


class Command(BaseCommand):
    help = "Record each student's current skill gaps against their target jobs"

    def add_arguments(self, parser):
        parser.add_argument("--student", type=int, default=None,
                            help="Limit to one student id.")

    def handle(self, *args, **options):
        students = Student.objects.all()
        if options["student"]:
            students = students.filter(pk=options["student"])

        totals = [0, 0, 0]
        covered = 0
        for student in students.prefetch_related("target_roles"):
            opened, closed, reopened = refresh_skill_gaps(student)
            if opened or closed or reopened:
                covered += 1
            totals = [a + b for a, b in zip(totals, (opened, closed, reopened))]

        self.stdout.write(self.style.SUCCESS(
            f"Skill gaps refreshed for {covered} student(s): "
            f"{totals[0]} opened, {totals[1]} closed, {totals[2]} reopened."
        ))
