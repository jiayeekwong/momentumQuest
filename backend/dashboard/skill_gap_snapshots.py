"""
Records the live skill-gap analysis into accounts.SkillGap rows.

Why persist something already computed on demand: the live view answers "what
am I missing right now", which is the question a student asks on the day. It
cannot answer "am I making progress", because it keeps no history. These rows
do -- a gap that is met becomes CLOSED with a timestamp rather than vanishing,
so the difference between two dates is measurable.

The live analysis stays authoritative. Nothing reads these rows to render the
dashboard; they are a record, not a cache, and a stale row can never make the
student's page wrong.
"""

from django.db import transaction
from django.utils import timezone

from accounts.models import SkillGap


def _priority(demand_percentage):
    from .views import HIGH_PRIORITY_DEMAND, MEDIUM_PRIORITY_DEMAND

    if demand_percentage >= HIGH_PRIORITY_DEMAND:
        return SkillGap.Priority.HIGH
    if demand_percentage >= MEDIUM_PRIORITY_DEMAND:
        return SkillGap.Priority.MEDIUM
    return SkillGap.Priority.LOW


@transaction.atomic
def refresh_skill_gaps(student):
    """Bring a student's SkillGap rows in line with the current analysis.

    Returns (opened, closed, reopened). Safe to run repeatedly: a gap that is
    still open is updated in place, so re-running does not inflate the history.
    """
    # Imported here rather than at module level: dashboard.views imports this
    # module's caller chain, and a top-level import would close the cycle.
    from .views import build_skill_gap

    opened = closed = reopened = 0
    now = timezone.now()

    targets = list(student.target_roles.all())
    if not targets:
        return opened, closed, reopened

    for target in targets:
        # Scoped by the role explicitly, never left to the default: passing
        # nothing would resolve the student's *first* target and record one
        # target's gaps against another's row.
        #
        # No skip for a thin role, unlike the occupation version this replaces.
        # build_skill_gap falls back to the role's track, which is an honest
        # scope for that target rather than a reason to record nothing -- and
        # with 2 of 124 roles above the evidence floor, skipping would mean
        # recording almost no history at all.
        analysis = build_skill_gap(student, role=target.market_role)

        missing = {
            entry['skill_id']: entry
            for entry in analysis['missing_skills']
        }

        for skill_id, entry in missing.items():
            demand = entry['demand_percentage']
            row, created = SkillGap.objects.get_or_create(
                student=student,
                skill_id=skill_id,
                target=target,
                defaults={
                    'demand_percentage': demand,
                    'priority_level': _priority(demand),
                },
            )
            if created:
                opened += 1
                continue

            was_closed = row.status == SkillGap.Status.CLOSED
            row.demand_percentage = demand
            row.priority_level = _priority(demand)
            row.status = SkillGap.Status.OPEN
            row.closed_time = None
            row.save(update_fields=[
                'demand_percentage', 'priority_level', 'status',
                'closed_time', 'updated_time',
            ])
            if was_closed:
                reopened += 1

        # A gap the student has since met is closed, never deleted: the record
        # of having closed it is the point of keeping this table.
        newly_closed = (
            SkillGap.objects
            .filter(student=student, target=target, status=SkillGap.Status.OPEN)
            .exclude(skill_id__in=missing.keys())
        )
        closed += newly_closed.update(
            status=SkillGap.Status.CLOSED, closed_time=now)

    return opened, closed, reopened
