"""Retire two aliases that never meant the library they point at.

Both are the pattern already retired for ``essentials``: a short, common word
aliased to a specific package, where no surrounding context makes the package
reading correct. Contextualising them would be a rule with no true positives to
protect, so they are deactivated instead.

``geo`` -> rust geo
    Already flagged requires_context, and it matched anyway -- the generic
    context gate passes any text that reads as technical, and an AI-marketing
    course does. Every occurrence in the corpus was the marketing acronym or
    another language entirely:

        advert  "Bonus skills SEO, AEO or GEO"
        course  "2026 AI SEO Tools And Techniques (LLM SEO, GEO, AEO)"
        course  "2026 AI SEO WITH Traffic From LLM SEO, GEO, AEO"
        course  "Generative AI for Digital Marketing"
        course  "Setup Python Geo Stack"          <- Python, not Rust

    Not one referred to the Rust crate. ``geo rust`` and ``geospatial rust``
    stay active and are unambiguous.

``chatgpt`` -> ChatGPT.js
    120 course mappings, and they are about ChatGPT the product rather than
    the Node wrapper library: "Advanced Data Analysis with ChatGPT",
    "AI-Assisted Web Developer". Someone writing "ChatGPT" in an advert wants a
    person who can use the assistant, not one who has integrated a particular
    npm package. ``chatgpt-node`` stays active and does name the library.

Reversible: nothing is deleted, two flags move.
"""
from django.db import migrations

RETIRED = ("geo", "chatgpt")


def retire(apps, schema_editor):
    SkillAlias = apps.get_model("scrape_jobs", "SkillAlias")
    SkillAlias.objects.filter(alias_name__in=RETIRED).update(is_active=False)


def restore(apps, schema_editor):
    SkillAlias = apps.get_model("scrape_jobs", "SkillAlias")
    SkillAlias.objects.filter(alias_name__in=RETIRED).update(is_active=True)


class Migration(migrations.Migration):

    dependencies = [
        ("scrape_jobs", "0027_guard_apache_and_rest"),
    ]

    operations = [
        migrations.RunPython(retire, restore),
    ]
