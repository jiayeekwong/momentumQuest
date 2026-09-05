"""Move courses and programmes onto the through tables, expanding the lists.

Two things happen here, in order.

First every existing Course and TrainingProgramme gets a through row for the
skill its foreign key already names, marked ``is_primary``. Nothing is lost
and nothing changes meaning.

Then the seven courses and programmes pointing at a malformed row -- one whose
``skill_name`` is a comma-separated list such as
``Javascript, HTML, CSS, MangoDB, Node.js`` -- are expanded into one link per
constituent skill, which is what those rows were always trying to express.
``MangoDB`` is corrected to MongoDB on the way through; it has been a typo in
the catalogue since the transcript subject-mapping work.

A constituent with no canonical row of its own is **skipped, not invented**.
"Cloud & DevOps Basics" and "data structure" are not skills we hold, and
guessing at them would put fabricated rows into a catalogue whose whole value
is that its entries are evidenced.

The primary foreign key is then re-pointed from the malformed row onto the
first constituent that resolved, so nothing references a quarantined row any
more.
"""
import re
import unicodedata

from django.db import migrations

#: Long-standing typos in the malformed strings, corrected on expansion.
TYPO_CORRECTIONS = {"mangodb": "MongoDB"}


def normalize(value):
    text = unicodedata.normalize("NFKC", str(value or "")).casefold().strip()
    text = text.replace("&", " and ")
    text = re.sub(r"[^\w+#.\- ]", " ", text)
    text = re.sub(r"[\s\-_]+", " ", text)
    return text.strip(" .")


def expand(apps, schema_editor):
    Skill = apps.get_model("scrape_jobs", "Skill")
    SkillAlias = apps.get_model("scrape_jobs", "SkillAlias")
    Course = apps.get_model("resources", "Course")
    CourseSkill = apps.get_model("resources", "CourseSkill")
    TrainingProgramme = apps.get_model("resources", "TrainingProgramme")
    TrainingProgrammeSkill = apps.get_model("resources",
                                            "TrainingProgrammeSkill")

    lookup = {}
    for skill in Skill.objects.all():
        if "," not in skill.skill_name:
            lookup.setdefault(normalize(skill.skill_name), skill)
    for alias in SkillAlias.objects.filter(is_active=True).select_related("skill"):
        if "," not in alias.skill.skill_name:
            lookup.setdefault(normalize(alias.alias_name), alias.skill)

    def constituents(name):
        found = []
        for part in [p.strip() for p in name.split(",") if p.strip()]:
            key = normalize(part)
            corrected = TYPO_CORRECTIONS.get(key)
            target = lookup.get(normalize(corrected)) if corrected else lookup.get(key)
            if target is not None and target not in found:
                found.append(target)
        return found

    for model, through, field in ((Course, CourseSkill, "course"),
                                  (TrainingProgramme, TrainingProgrammeSkill,
                                   "programme")):
        for row in model.objects.select_related("skill"):
            if row.skill is None:
                continue

            targets = ([row.skill] if "," not in row.skill.skill_name
                       else constituents(row.skill.skill_name))
            if not targets:
                # Nothing resolved; leave the row exactly as it is rather than
                # silently detaching it from its only skill.
                continue

            for index, skill in enumerate(targets):
                through.objects.get_or_create(
                    **{field: row, "skill": skill},
                    defaults={"is_primary": index == 0})

            if "," in row.skill.skill_name:
                row.skill = targets[0]
                row.save(update_fields=["skill"])


def unexpand(apps, schema_editor):
    apps.get_model("resources", "CourseSkill").objects.all().delete()
    apps.get_model("resources", "TrainingProgrammeSkill").objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("resources", "0018_courseskill_course_skills_trainingprogrammeskill_and_more"),
        ("scrape_jobs", "0019_quarantine_malformed_skill_rows"),
    ]

    operations = [migrations.RunPython(expand, unexpand)]
