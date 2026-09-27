"""
Turns parsed transcript subjects into StudentSkill rows.

Two rules govern the write, and both exist to stop a transcript from making a
student's profile worse than it already is:

  * highest grade wins when two subjects map to the same skill
  * an existing StudentSkill is never downgraded, only raised
"""

import logging
from collections import defaultdict

from django.db import transaction

from accounts.models import StudentSkill
from .models import Course, SubjectSkillMapping
from .transcript_parser import GRADE_TO_LEVEL, LEVEL_RANK

logger = logging.getLogger(__name__)


def _skills_for(codes):
    """The skills each module code teaches: {code: [Skill]}.

    A code can be described in two places. Course is the table an
    administrator edits in Manage Courses; SubjectSkillMapping is a seeded
    baseline of Universiti Malaya modules. Only the second was ever read here,
    so skills attached to a course in the admin did nothing to a transcript --
    the administrator mapped the right thing in a table nothing consulted, and
    nothing said so.

    The administrator's own answer wins where there is one, and the seed
    answers for the modules nobody has entered. That leaves two tables
    describing the same thing, which is worth consolidating later; this is the
    part that makes the admin page mean what it appears to mean.

    Inactive skills are excluded from both. A name typed into the course form
    that is not in the catalogue is created inactive and held for review, and
    the whole point of that quarantine is that an administrator's typo does not
    reach a student's profile.
    """
    from_courses = defaultdict(list)
    for course in (Course.objects
                   .filter(course_code__in=codes)
                   .select_related("skill")
                   .prefetch_related("skill_links__skill")):
        links = sorted(course.skill_links.all(),
                       key=lambda l: (not l.is_primary, l.skill.skill_name))
        # A course saved before CourseSkill existed has the headline foreign
        # key and no links at all, and reading only the links made it look
        # like a course nobody had mapped -- so the seed answered for it and
        # the administrator's own entry was silently ignored.
        skills = [link.skill for link in links] or (
            [course.skill] if course.skill else [])
        for skill in skills:
            if skill.is_active:
                from_courses[course.course_code].append(skill)

    remaining = {code for code in codes if code not in from_courses}
    by_code = dict(from_courses)
    for mapping in (SubjectSkillMapping.objects
                    .filter(subject_code__in=remaining, is_active=True,
                            skill__is_active=True)
                    .select_related("skill")):
        by_code.setdefault(mapping.subject_code, []).append(mapping.skill)

    return by_code


def resolve_skills(subjects):
    """
    Map parsed subject rows to {Skill: level}, highest grade winning.

    Also annotates each subject dict in place with the skill names it produced,
    so the student can see which subject earned what.

    Rows that failed the grade-point checksum, or whose grade is below C, are
    skipped — a misparsed or barely-passed row must not reach the profile.
    """
    codes = {subject["code"] for subject in subjects}
    skills_by_code = _skills_for(codes)

    best_level = {}
    for subject in subjects:
        if not subject["checksum_ok"]:
            continue

        level = GRADE_TO_LEVEL.get(subject["grade"])
        if not level:
            continue

        for skill in skills_by_code.get(subject["code"], []):
            subject["skills"].append(skill.skill_name)

            current = best_level.get(skill)
            if current is None or LEVEL_RANK[level] > LEVEL_RANK[current]:
                best_level[skill] = level

    return best_level


@transaction.atomic
def apply_skills(student, skill_levels):
    """
    Upsert StudentSkill rows for the student.

    Returns (added, upgraded). Re-uploading the same transcript is a no-op,
    which keeps the endpoint safe to retry.

    A change here also refreshes the student's recorded skill gaps, because
    this function is the only write path into StudentSkill: an endorsed
    certificate and a parsed transcript both land here. Validating a skill is
    exactly the moment a gap closes, so recording it on a schedule instead
    would leave the student's progress history stale until the next run.
    """
    added = 0
    upgraded = 0

    for skill, level in skill_levels.items():
        row, created = StudentSkill.objects.get_or_create(
            student=student,
            skill=skill,
            defaults={"skill_level": level},
        )
        if created:
            added += 1
        elif LEVEL_RANK[level] > LEVEL_RANK.get(row.skill_level, 0):
            row.skill_level = level
            row.save(update_fields=["skill_level"])
            upgraded += 1

    if added or upgraded:
        # Imported here, not at module level: dashboard.skill_gap_snapshots
        # reaches dashboard.views, which imports resources.models, and a
        # top-level import would close that cycle.
        from dashboard.skill_gap_snapshots import refresh_skill_gaps

        # A no-op for a student with no target job, and never a reason to fail
        # the upload or the endorsement that triggered it -- the skills are
        # already written and are what the live analysis reads.
        try:
            refresh_skill_gaps(student)
        except Exception:
            logger.exception(
                "Skill-gap refresh failed for student %s after a skill change",
                student.pk,
            )

    return added, upgraded
