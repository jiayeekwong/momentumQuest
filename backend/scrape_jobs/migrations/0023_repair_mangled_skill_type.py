"""Repair skill_type values that were written one character at a time.

Thirty-three rows carry values like ``'T | o | o | l'`` and
``'S | e | r | v | i | c | e'`` -- "Tool" and "Service" with the multi-value
separator inserted between every letter, by an importer that iterated a string
where it meant to iterate a list of strings.

The column is the source's own classification of a skill, so a mangled value
does not merely read badly: it groups nothing and filters nothing, and
``skill_type='Tool'`` silently misses these rows. Repairing it matters now
because the catalogue is about to become reproducible from versioned seed
files, and exporting first would freeze the corruption into the seed
permanently.

Only rows where *every* separated part is a single character are touched. A
genuine multi-value type -- ``'Service | Tool'``, ``'Library | MarkupLanguage'``
-- has parts longer than one character and is left exactly as it is.

Not reversible. Going back would mean re-corrupting the data, and the set of
rows to re-corrupt is not recoverable once repaired: after this runs, 'Tool'
here is indistinguishable from the 174 rows that always said 'Tool'.
"""
from django.db import migrations

SEPARATOR = " | "


def _is_mangled(value):
    """Whether the value is one word split character-by-character.

    Requires at least two parts so a single character type -- were one ever
    added -- is not mistaken for a mangling of itself.
    """
    parts = value.split(SEPARATOR)
    return len(parts) > 1 and all(len(part) == 1 for part in parts)


def repair(apps, schema_editor):
    Skill = apps.get_model("scrape_jobs", "Skill")

    for skill in Skill.objects.exclude(skill_type="").iterator():
        if _is_mangled(skill.skill_type):
            skill.skill_type = "".join(skill.skill_type.split(SEPARATOR))
            skill.save(update_fields=["skill_type"])


class Migration(migrations.Migration):

    dependencies = [
        ("scrape_jobs", "0022_marketrolealias_is_active_and_more"),
    ]

    operations = [
        migrations.RunPython(repair, migrations.RunPython.noop),
    ]
