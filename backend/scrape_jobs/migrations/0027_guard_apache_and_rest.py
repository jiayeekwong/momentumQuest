"""Gate two more terms that mean something else more often than not.

Found by the exposure sweep that followed the backbone/charts/essentials fix,
and measured against the live corpus rather than a word list:

    'apache' -> Apache (HTTP Server)
        43 of 44 occurrences were a different Apache Foundation project --
        "Apache Spark", "Apache Kafka", "Apache Flink", "Apache Polaris",
        "Dubbo (Apache or Alibaba)". One occurrence, "Nginx/Apache", was the
        web server. A 97.7% false-positive rate, the worst in the sweep.

    'REST' -> REST API
        84 of 89 occurrences were the API style. The other five were English:
        "rest day given in lieu", "Rest assured, we handle every application",
        "trainable for the rest".

The flag says "ask before matching"; what to ask is in
skill_extractor.TERM_GUARDS, because the generic context gate cannot separate
these -- a Spark advert and an httpd advert both read as technical, and both
mention "engineer".

Deliberately narrow. The exposure sweep produced 220 candidate terms and this
migration changes two, because these are the two with counted false positives.
Everything else on that list -- Python, Azure, Git, Linux, Docker, React,
Jira, Node, Oracle, Kubernetes and the rest -- was sampled and found correct,
and gating a correct term costs recall for nothing.
"""
from django.db import migrations

CONTEXTUAL = ("apache", "REST")


def guard_terms(apps, schema_editor):
    SkillAlias = apps.get_model("scrape_jobs", "SkillAlias")
    SkillAlias.objects.filter(alias_name__in=CONTEXTUAL).update(
        requires_context=True)


def unguard_terms(apps, schema_editor):
    SkillAlias = apps.get_model("scrape_jobs", "SkillAlias")
    SkillAlias.objects.filter(alias_name__in=CONTEXTUAL).update(
        requires_context=False)


class Migration(migrations.Migration):

    dependencies = [
        ("scrape_jobs", "0026_guard_generic_skill_terms"),
    ]

    operations = [
        migrations.RunPython(guard_terms, unguard_terms),
    ]
