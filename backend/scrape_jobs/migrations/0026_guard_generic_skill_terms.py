"""Stop three generic English words matching as technology skills.

Found while auditing Coursera mappings, but the exposure was never limited to
courses: the same matcher reads job adverts, so each of these has been
inflating skill demand and distorting match scores for as long as it has been
active.

    'backbone'   -> Backbone.js         advert 269, "Project Engineer -
                                        IT/Fiber Optic (Data Center)":
                                        "Coordinate fiber optic, backbone, and
                                        horizontal cabling scope"
    'charts'     -> Chart.js            Coursera card: "Skills you'll gain:
                                        Microsoft Excel, Pivot Tables And
                                        Charts"
    'essentials' -> Xamarin.Essentials  "Microsoft SQL Server: Performance
                                        Tuning Essentials"

``backbone`` and ``charts`` are marked requires_context. On their own that
flag would not have been enough -- the generic context gate passes any text
mentioning "engineer" or "software", which a cabling advert certainly does --
so each also has a term guard in skill_extractor.TERM_GUARDS naming the
vocabulary that admits it and the vocabulary that rules it out. The flag says
"ask before matching"; the guard says what to ask.

``essentials`` is deactivated instead. There is no context in which the bare
word means the Xamarin library: it is a title noun ("Performance Tuning
Essentials", "Python Essentials"), and a guard would be a rule with no true
positives to protect. The explicit forms keep working -- "xamarin essentials"
stays active, and the canonical "Xamarin.Essentials" was never in question.

Sage is handled in code rather than here: it is a canonical skill name, not an
alias, so there is no requires_context flag to set. Its guard lives alongside
these in TERM_GUARDS.

Reversible. Nothing is deleted; three flags move.
"""
from django.db import migrations

CONTEXTUAL = ("backbone", "charts")
DEACTIVATED = ("essentials",)


def guard_terms(apps, schema_editor):
    SkillAlias = apps.get_model("scrape_jobs", "SkillAlias")

    SkillAlias.objects.filter(alias_name__in=CONTEXTUAL).update(
        requires_context=True)
    SkillAlias.objects.filter(alias_name__in=DEACTIVATED).update(
        is_active=False)


def unguard_terms(apps, schema_editor):
    SkillAlias = apps.get_model("scrape_jobs", "SkillAlias")

    SkillAlias.objects.filter(alias_name__in=CONTEXTUAL).update(
        requires_context=False)
    SkillAlias.objects.filter(alias_name__in=DEACTIVATED).update(
        is_active=True)


class Migration(migrations.Migration):

    dependencies = [
        ("scrape_jobs", "0025_dotnet_core_and_vbnet_provenance"),
    ]

    operations = [
        migrations.RunPython(guard_terms, unguard_terms),
    ]
