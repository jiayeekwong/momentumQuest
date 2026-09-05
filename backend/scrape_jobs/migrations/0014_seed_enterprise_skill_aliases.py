"""Superseded by ``manage.py import_skills``.

This migration seeded skill aliases, but only where the canonical skill
already existed -- and on a fresh database migrations run before anything
imports cs_skills.csv, so there were no skills to point at and every alias
was skipped. The original comment said they would "wait for the next run";
nothing ran them again, so a new deployment got the full skill list and no
aliases at all.

Aliases now live in data/skill_aliases.csv and are loaded by import_skills,
which imports the canonical skills first and the aliases second, is
idempotent, and reports any alias it could not resolve instead of silently
dropping it.

Left as an explicit no-op rather than deleted: it is already applied on
existing databases, where it did seed correctly, and removing an applied
migration would break their history.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("scrape_jobs", "0013_delete_icttrack"),
    ]

    operations = [
        migrations.RunPython(migrations.RunPython.noop,
                             migrations.RunPython.noop),
    ]
