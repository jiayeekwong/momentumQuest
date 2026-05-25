from .models import Skill

# simplest keyword matching skill extractor for now

def extract_skills_from_text(text):
    """
    Simple keyword-based skill extraction.

    This compares job description text with skills stored in the Skill table.
    Later, this can be upgraded to spaCy, SkillNER, or BERT.
    """
    if not text:
        return []

    text_lower = text.lower()
    matched_skills = []

    skills = Skill.objects.all()

    for skill in skills:
        skill_name_lower = skill.skill_name.lower()

        if skill_name_lower in text_lower:
            matched_skills.append(skill)

    return matched_skills