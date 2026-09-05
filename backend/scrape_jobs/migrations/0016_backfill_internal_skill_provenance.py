"""Give every pre-existing skill and alias an explicit INTERNAL provenance row.

Provenance that only some skills carry is worse than none: a later query for
"which skills did MTO add?" would answer correctly, but "which did we curate
ourselves?" would silently return the empty set. So the 186 skills and 39
aliases that predate any external import are stamped now, before MTO lands,
while "everything currently here is ours" is still true.

Nothing is renamed, deleted or re-pointed. This adds rows to a new table and
sets a default-valued column on existing ones.
"""
from django.db import migrations


def stamp_internal(apps, schema_editor):
    Skill = apps.get_model("scrape_jobs", "Skill")
    SkillSource = apps.get_model("scrape_jobs", "SkillSource")

    existing = set(SkillSource.objects.filter(source="INTERNAL")
                   .values_list("skill_id", flat=True))

    SkillSource.objects.bulk_create([
        SkillSource(skill_id=skill.id,
                    source="INTERNAL",
                    external_label=skill.skill_name,
                    source_type=skill.skill_category,
                    source_version="pre-mto-baseline")
        for skill in Skill.objects.all() if skill.id not in existing
    ])

    Skill.objects.update(catalogue_status="ACTIVE_INTERNAL", is_active=True)


def unstamp(apps, schema_editor):
    SkillSource = apps.get_model("scrape_jobs", "SkillSource")
    SkillSource.objects.filter(source="INTERNAL",
                               source_version="pre-mto-baseline").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("scrape_jobs", "0015_skill_catalogue_status_skill_is_active_and_more"),
    ]

    operations = [migrations.RunPython(stamp_internal, unstamp)]
