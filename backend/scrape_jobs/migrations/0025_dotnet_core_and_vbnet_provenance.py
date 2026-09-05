"""Collapse .NET Core into the platform, and record VB.NET's Malaysian evidence.

Two changes, both following the granularity rule settled in 0024: runtime and
platform variants collapse into ``.NET``, while ASP.NET and ASP.NET Core stay
separate framework concepts.

``.NET Core`` was an alias of ``ASP.NET Core``, which is the same conflation
0024 removed for bare ".NET" -- .NET Core is the runtime, ASP.NET Core is the
web framework built on it. The Malaysian corpus names .NET Core in 13 adverts
against 4 for ASP.NET Core, so the alias was filing platform demand under a
framework roughly three times more often than that framework was actually
asked for. One advert shows it plainly:

    "Hands-on with .NET Core, .NET Framework, and React"

which named no web framework at all and was nonetheless recorded as ASP.NET
Core. The alias is repointed rather than deleted, because ".NET Core" is still
a real thing adverts say -- it simply names the platform.

ASP.NET Core is untouched and remains canonical, so an advert that does say
"ASP.NET Core" still resolves to it: ".NET Core" cannot match inside
"ASP.NET Core" because the term begins with a dot and its left assertion
rejects a preceding token character.

VB.NET needs no creation -- it is already canonical, from MTO -- but it had
only MTO provenance while Malaysian adverts do ask for it: 7 adverts across 4
distinct employers (SLS Bearings, Tony Ng & Associates, Exact Asia Development
Centre, Grain & Protein Technologies). That clears the admission rule for
Malaysian evidence, and SkillSource exists precisely so a skill can be attested
by more than one catalogue. It is emphatically *not* mapped to .NET: VB.NET is
a language that targets the platform, the same way C# does.

Classic ``Visual Basic`` stays a separate canonical skill. Two QES adverts ask
for "MS Office, Visual Basic, C# & C++" in an industrial-automation context,
which is VB6/VBA and not VB.NET, and folding the two together would file those
under a language they do not mention.
"""
from django.db import migrations

#: 7 adverts across 4 employers. Pinned so the claim can be re-derived.
VBNET_EVIDENCE = "7 Malaysian adverts across 4 employers"


def apply_decisions(apps, schema_editor):
    Skill = apps.get_model("scrape_jobs", "Skill")
    SkillAlias = apps.get_model("scrape_jobs", "SkillAlias")
    SkillSource = apps.get_model("scrape_jobs", "SkillSource")

    dotnet = Skill.objects.filter(skill_name=".NET").first()
    if dotnet is not None:
        SkillAlias.objects.filter(alias_name__iexact=".NET Core").update(
            skill_id=dotnet.id)

    vbnet = Skill.objects.filter(skill_name="VB.NET").first()
    if vbnet is not None:
        SkillSource.objects.get_or_create(
            skill_id=vbnet.id,
            source="MALAYSIA_JD",
            external_label="VB.NET",
            defaults={
                "external_id": "vb.net",
                "source_version": VBNET_EVIDENCE,
                "source_url": "",
                "source_type": "market-evidence",
            },
        )


def revert_decisions(apps, schema_editor):
    Skill = apps.get_model("scrape_jobs", "Skill")
    SkillAlias = apps.get_model("scrape_jobs", "SkillAlias")
    SkillSource = apps.get_model("scrape_jobs", "SkillSource")

    aspnet_core = Skill.objects.filter(skill_name="ASP.NET Core").first()
    if aspnet_core is not None:
        SkillAlias.objects.filter(alias_name__iexact=".NET Core").update(
            skill_id=aspnet_core.id)

    SkillSource.objects.filter(skill__skill_name="VB.NET",
                               source="MALAYSIA_JD").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("scrape_jobs", "0024_dotnet_canonical_skill"),
    ]

    operations = [
        migrations.RunPython(apply_decisions, revert_decisions),
    ]
