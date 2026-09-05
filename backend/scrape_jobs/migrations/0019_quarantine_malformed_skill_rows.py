"""Take the seven malformed catalogue rows out of circulation.

Each of these rows stores a comma-separated *list* in ``skill_name`` -- one
reads ``Javascript, HTML, CSS, MangoDB, Node.js`` as a single skill, and
carries a typo (`MangoDB` for MongoDB) that has been in the catalogue since
the transcript subject-mapping work. They arrived from course and programme
definitions, where one row was meant to describe everything a course teaches.

They are **deactivated, not deleted**. Three Course rows and four
TrainingProgramme rows point at them through a single-valued foreign key, so
deleting would break real references, and re-pointing is not a decision this
migration can make: a course teaching "Python, Machine Learning" maps to two
skills and the column holds one. That re-pointing is left to a human, with
the split written to
``research/malaysia_gap_production_integration/results/malformed_row_split_plan.csv``.

Deactivating is enough to fix the damage they actually do: the extractor
skips inactive skills, so they can no longer match advert text, and the
Malaysia-gap reconciliation excludes them so no new candidate can be resolved
onto one.
"""
from django.db import migrations

MALFORMED_MARKER = ","


def quarantine(apps, schema_editor):
    Skill = apps.get_model("scrape_jobs", "Skill")
    for skill in Skill.objects.filter(skill_name__contains=MALFORMED_MARKER):
        skill.is_active = False
        skill.catalogue_status = "REVIEW_REQUIRED"
        skill.save(update_fields=["is_active", "catalogue_status"])


def restore(apps, schema_editor):
    Skill = apps.get_model("scrape_jobs", "Skill")
    Skill.objects.filter(skill_name__contains=MALFORMED_MARKER).update(
        is_active=True, catalogue_status="ACTIVE_INTERNAL")


class Migration(migrations.Migration):

    dependencies = [("scrape_jobs", "0018_alter_skillsource_source")]

    operations = [migrations.RunPython(quarantine, restore)]
