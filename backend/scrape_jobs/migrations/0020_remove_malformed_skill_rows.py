"""Delete the seven malformed rows now that nothing depends on them.

Phase 9 quarantined them; ``resources.0019`` re-pointed the three courses and
four training programmes that referenced them onto real constituent skills
through the new link tables. The only thing still attached is each row's own
INTERNAL provenance record, which cascades.

Deleting is safe *because* of that order, and only because of it. Removing
them earlier would have cascaded through ``Course.skill``, which is
``on_delete=CASCADE`` -- taking three real courses with it.

The names are logged into the migration itself rather than only into a
research CSV, so what was removed stays legible in the schema history.
"""
from django.db import migrations

REMOVED = [
    "Python, Automation, Data Analysis, Cloud & DevOps Basics",
    "Javascript, HTML, CSS, MangoDB, Node.js",
    "Python, Machine Learning",
    "Java, OOP, data structure",
    "Python, Data Analysis, Pandas, NumPy, Data Visualization",
    "Cybersecurity, Online Safety, Risk Management, Data Protection",
    "Communication, Presentation Skills, Active Listening, Teamwork",
]


def drop(apps, schema_editor):
    Skill = apps.get_model("scrape_jobs", "Skill")
    Course = apps.get_model("resources", "Course")
    TrainingProgramme = apps.get_model("resources", "TrainingProgramme")

    malformed = Skill.objects.filter(skill_name__contains=",")

    # Refuse rather than cascade. If anything still points here the earlier
    # migration did not do its job, and destroying a course to tidy up a
    # catalogue row would be a bad trade.
    blocked = (Course.objects.filter(skill__in=malformed).exists()
               or TrainingProgramme.objects.filter(skill__in=malformed).exists())
    if blocked:
        raise RuntimeError(
            "malformed skill rows still have course or programme consumers; "
            "run resources.0019 first")

    malformed.delete()


def restore(apps, schema_editor):
    """Recreate the names only. The rows carried nothing else worth keeping,
    and their consumers now point at real skills."""
    Skill = apps.get_model("scrape_jobs", "Skill")
    for name in REMOVED:
        Skill.objects.get_or_create(
            skill_name=name,
            defaults={"catalogue_status": "REVIEW_REQUIRED",
                      "is_active": False})


class Migration(migrations.Migration):

    dependencies = [
        ("scrape_jobs", "0019_quarantine_malformed_skill_rows"),
        ("resources", "0019_populate_course_skill_links"),
    ]

    operations = [migrations.RunPython(drop, restore)]
