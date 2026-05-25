import re

from .models import Skill


def extract_skills_from_text(text):
    """
    Word-boundary keyword skill extraction.

    Uses \b regex boundaries to prevent false positives:
      "R" won't match "required", "Go" won't match "good",
      "C" won't match "security".
    """
    if not text:
        return []

    matched_skills = []

    for skill in Skill.objects.all():
        pattern = re.compile(
            rf'\b{re.escape(skill.skill_name)}\b',
            re.IGNORECASE,
        )
        if pattern.search(text):
            matched_skills.append(skill)

    return matched_skills
