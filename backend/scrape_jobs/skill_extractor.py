import re

from .models import Skill, SkillAlias


def extract_skills_from_text(text):
    """
    Word-boundary keyword skill extraction.

    Uses \b regex boundaries to prevent false positives:
      "R" won't match "required", "Go" won't match "good",
      "C" won't match "security".

    A skill also matches on any of its SkillAlias names (e.g. "JS" -> JavaScript),
    so a single skill is never added twice.
    """
    if not text:
        return []

    # Map each canonical skill to all the terms that should match it.
    terms_by_skill = {skill: [skill.skill_name] for skill in Skill.objects.all()}
    for alias in SkillAlias.objects.select_related("skill"):
        terms_by_skill.setdefault(alias.skill, [alias.skill.skill_name]).append(
            alias.alias_name
        )

    matched_skills = []
    for skill, terms in terms_by_skill.items():
        pattern = re.compile(
            r'\b(?:' + '|'.join(re.escape(t) for t in terms) + r')\b',
            re.IGNORECASE,
        )
        if pattern.search(text):
            matched_skills.append(skill)

    return matched_skills
