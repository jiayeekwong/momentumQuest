"""Separate the .NET platform from the ASP.NET web framework.

``.NET`` arrived from MTO as an *alias of ASP.NET*, which conflates two
different things. .NET is the platform and runtime -- the thing C#, F# and
VB.NET all target; ASP.NET is one web framework built on it. An advert asking
for "a .NET developer" is naming the ecosystem, not committing to server-side
web work, and filing it under ASP.NET overstated demand for that framework
while hiding demand for the platform entirely.

Malaysian evidence behind the split, over the 735 scraped adverts carrying a
description:

    bare ".NET"        39 adverts
    ".NET Core"        13
    ".NET Framework"   11  (4 of which are "ASP.NET framework", so ~7 real)
    "ASP.NET"          19  (4 of them "ASP.NET Core")

So the platform is named nearly twice as often as the framework it was being
filed under.

``.NET Framework`` is made an alias of ``.NET`` rather than a canonical skill
of its own, and that is a judgement about how the corpus actually uses it.
Microsoft's ".NET Framework" is a specific legacy product distinct from .NET
Core, but Malaysian adverts overwhelmingly use "the .NET framework" as an
ordinary-language name for the platform:

    "Strong proficiency in the .NET framework (C#, ASP.NET, .NET Core/5+)"
    "build software using languages and technologies of the .NET framework"

The first of those lists .NET Core *inside* "the .NET framework", which the
legacy reading cannot survive. Exactly one advert uses the strict product
sense -- "hands-on experience with .NET Core, .NET Framework, and React".
Making it canonical would split ~7 adverts on a distinction the corpus does
not make and mis-file the majority that mean the platform; if that changes,
promoting it later is a seed-file edit.

ASP.NET and ASP.NET Core are untouched and remain canonical.
"""
from django.db import migrations

SKILL_NAME = ".NET"
#: Pinned in the provenance row so the claim can be re-derived rather than
#: taken on trust. See the counts above.
EVIDENCE = "39 Malaysian adverts"


def split_dotnet(apps, schema_editor):
    Skill = apps.get_model("scrape_jobs", "Skill")
    SkillAlias = apps.get_model("scrape_jobs", "SkillAlias")
    SkillSource = apps.get_model("scrape_jobs", "SkillSource")

    # MARKET_EXTENSION, and the classification columns left blank: that is the
    # convention for a skill the Malaysian corpus vouches for, because the
    # market is evidence of demand and not an external taxonomy with a type
    # system of its own.
    dotnet, _ = Skill.objects.get_or_create(
        skill_name=SKILL_NAME,
        defaults={
            "skill_category": "",
            "skill_type": "",
            "technical_domain": "",
            "catalogue_status": "MARKET_EXTENSION",
            "is_active": True,
        },
    )

    # The alias has to go rather than be repointed at .NET. alias_name is
    # unique and the extractor reads canonical names and alias names from the
    # same term table, so an alias identical to a canonical skill's own name
    # is a second, competing route to a different skill.
    SkillAlias.objects.filter(alias_name__iexact=SKILL_NAME).delete()

    # Repointed, not deleted: ".NET Framework" is still a real thing adverts
    # say, and it should resolve -- to the platform.
    SkillAlias.objects.filter(alias_name__iexact=".NET Framework").update(
        skill_id=dotnet.id)

    SkillSource.objects.get_or_create(
        skill_id=dotnet.id,
        source="MALAYSIA_JD",
        external_label=SKILL_NAME,
        defaults={
            "external_id": "dotnet",
            "source_version": EVIDENCE,
            "source_url": "",
            "source_type": "market-evidence",
        },
    )


def rejoin_dotnet(apps, schema_editor):
    """Put ".NET" back to being an alias of ASP.NET.

    Reversible because nothing is lost either way: the alias row is recreated
    from the same two names, and the skill it pointed at still exists.
    """
    Skill = apps.get_model("scrape_jobs", "Skill")
    SkillAlias = apps.get_model("scrape_jobs", "SkillAlias")

    aspnet = Skill.objects.filter(skill_name="ASP.NET").first()
    if aspnet is not None:
        SkillAlias.objects.filter(alias_name__iexact=".NET Framework").update(
            skill_id=aspnet.id)
        SkillAlias.objects.get_or_create(
            alias_name=SKILL_NAME,
            defaults={"skill_id": aspnet.id, "source": "MTO",
                      "requires_context": True, "is_active": True},
        )

    Skill.objects.filter(skill_name=SKILL_NAME).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("scrape_jobs", "0023_repair_mangled_skill_type"),
    ]

    operations = [
        migrations.RunPython(split_dotnet, rejoin_dotnet),
    ]
