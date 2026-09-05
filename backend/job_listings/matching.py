"""Job matching score, shared by the student and the company view.

    Job Matching Percentage = (total matched skill score / total required
                               skill score) x 100

    Proficiency value: Beginner = 1, Intermediate = 2, Advanced = 3

      * student has the skill and level >= required level -> full score
      * student has the skill but level <  required level -> partial score,
        based on the student's level
      * student does not have the skill                   -> 0

The three clauses collapse to ``min(student value, required value)``, which is
how they are implemented -- capping at the required value is exactly "full
score when you meet it, your own value when you fall short".

This module is the single definition of that formula. It previously existed
only as an employer-side serializer method that counted skill names and
ignored proficiency entirely, plus a separate client-side reimplementation in
the student jobs page; the two could not agree, and neither matched the spec.
"""

from accounts.models import StudentSkill

# Built from the model's own choices so the scale cannot drift from the levels
# a StudentSkill or a JobSkill can actually hold.
PROFICIENCY_VALUE = {
    StudentSkill.SkillLevel.BEGINNER: 1,
    StudentSkill.SkillLevel.INTERMEDIATE: 2,
    StudentSkill.SkillLevel.ADVANCED: 3,
}


def proficiency_value(level):
    """Numeric weight for a proficiency level; unknown values score lowest."""
    return PROFICIENCY_VALUE.get(level, 0)


def skill_score(required_level, student_level):
    """Score one required skill for a student.

    ``student_level`` is None when the student does not hold the skill.
    """
    if student_level is None:
        return 0
    return min(proficiency_value(student_level), proficiency_value(required_level))


def student_skill_levels(student):
    """{skill_id: level} for one student, in a single query."""
    if student is None:
        return {}
    return {
        row.skill_id: row.skill_level
        for row in student.student_skills.all()
    }


def snapshot_skill_levels(application):
    """{skill_id: level} as recorded when the application was submitted.

    Keyed on the "skills" key being *absent*, not on the list being empty. A
    student who submitted no skills submitted no skills: scoring them against
    their live profile would report a match built from information they chose
    not to send, and would drift every time they edited their profile.

    The fallback survives only for rows written before snapshots existed,
    which have no "skills" key at all and no better answer available.
    """
    snapshot = application.applicant_snapshot or {}

    if "skills" in snapshot:
        return {
            entry["skill_id"]: entry.get("skill_level")
            for entry in (snapshot.get("skills") or [])
            if entry.get("skill_id") is not None
        }

    return student_skill_levels(application.student)


def match_score(job, student_levels):
    """Percentage match between a listing and a student's skill levels.

    Returns None when the advert lists no skills. A listing with nothing to
    compare against has no meaningful score, and reporting 0 would read as
    "you match none of it" rather than "we do not know" -- the student-facing
    UI relies on that distinction to show nothing at all.

    ``job.job_skills`` should be prefetched by the caller; this function does
    not query when it has been.
    """
    required = list(job.job_skills.all())
    if not required:
        return None

    total_required = sum(
        proficiency_value(row.required_level) for row in required
    )
    if not total_required:
        return None

    total_matched = sum(
        skill_score(row.required_level, student_levels.get(row.skill_id))
        for row in required
    )
    return round(total_matched / total_required * 100)


class MatchScoreMixin:
    """Adds a per-request ``match_score`` to a job serializer.

    The student's levels are read once per serialization rather than once per
    listing, so scoring a page of jobs stays at one extra query.
    """

    def student_levels(self):
        if not hasattr(self, '_student_levels_cache'):
            self._student_levels_cache = student_skill_levels(
                self.request_student()
            )
        return self._student_levels_cache

    def request_student(self):
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        if user is None or not user.is_authenticated:
            return None
        return getattr(user, 'student_profile', None)

    def get_match_score(self, obj):
        # Anonymous visitors and company accounts get null, not 0: there is no
        # student to compare the advert against.
        if self.request_student() is None:
            return None
        return match_score(obj, self.student_levels())
