"""Add "AI Coding Assistants" -- using AI tools to write and debug software.

Sixteen Malaysian adverts across sixteen employers ask for this and the
catalogue recorded nothing for it. What it *did* have was ``chatgpt``
pointing at ChatGPT.js, a Node wrapper library, which meant an advert asking
for a developer comfortable with Copilot was filed under an npm package or
under nothing at all.

The competence is coherent and narrower than "uses AI". These adverts want
someone who writes software with an assistant: SNSOFT wants Claude Code and
Codex "to improve development efficiency, solution design, debugging";
AIRDROITECH wants Copilot "to generate and optimize test cases"; CODEMAX
advertises an "AI-Forward Full-Stack Developer". That is a different thing from
using ChatGPT to draft an email, from generating marketing copy, and from
integrating an LLM API -- the last of which the catalogue already covers as
LLM, GenAI, Prompt Engineering and OpenAI API.

So the product names are contextual triggers, never unconditional aliases.
Every one of them -- ChatGPT, Copilot, Cursor, Claude, Codex, Amazon Q, Gemini
-- is used outside software development, and each carries a term guard in
skill_extractor requiring coding vocabulary nearby and rejecting the
business-productivity, content and API-integration senses. They are evidence,
not synonyms: SkillAlias is read by the extractor and exposed in no API, so
none of these ever appears in the interface as another name for this skill.

Shadow-run over the 30 adverts that mention any of these products before any of
it was written:

    16 adverts gain the skill   (8 of which recorded no AI skill at all)
    14 do not fire              Power Apps/Automate/Studio, SharePoint,
                                Purview, corporate communications, Figma and
                                Firefly, content generation, LLM API
                                integration, Gemini Enterprise

Three rules came out of false positives that shadow run caught rather than out
of theory: bare "develop" is not a trigger (it fired on "application
development" in a Power Platform advert), a reject beats a trigger in the same
window, and the window is 120 characters rather than 260 because at 260
unrelated vocabulary drifted in and vetoed two genuine adverts.

Power BI is deliberately *not* a reject. It appeared to be a business-stack
signal until the shadow showed it sitting beside genuine assistant-assisted
development in two adverts, so it is not a reliable anti-signal.

MARKET_EXTENSION: admitted on Malaysian evidence. External corroboration is
weak and recorded as such -- Tech Jobs rates GitHub Copilot and Copilot
TOO_NICHE at three postings each -- which under the admission rule informs the
provenance without blocking it.
"""
from django.db import migrations

SKILL_NAME = "AI Coding Assistants"
EVIDENCE = "16 Malaysian adverts across 16 employers"

#: Product names that are evidence for this skill *in coding context only*.
#: Guarded in skill_extractor.TERM_GUARDS; requires_context is what sends them
#: through that gate.
CONTEXTUAL_ALIASES = (
    "chatgpt", "github copilot", "copilot", "cursor", "claude", "claude code",
    "codex", "amazon q", "gemini",
)


def add_skill(apps, schema_editor):
    Skill = apps.get_model("scrape_jobs", "Skill")
    SkillAlias = apps.get_model("scrape_jobs", "SkillAlias")
    SkillSource = apps.get_model("scrape_jobs", "SkillSource")

    skill, _ = Skill.objects.get_or_create(
        skill_name=SKILL_NAME,
        defaults={
            "skill_category": "Software Engineering",
            "skill_type": "",
            "technical_domain": "",
            "catalogue_status": "MARKET_EXTENSION",
            "is_active": True,
        },
    )

    SkillSource.objects.get_or_create(
        skill_id=skill.id,
        source="MALAYSIA_JD",
        external_label=SKILL_NAME,
        defaults={
            "external_id": "ai coding assistants",
            "source_version": EVIDENCE,
            "source_url": "",
            "source_type": "market-evidence",
        },
    )

    for alias in CONTEXTUAL_ALIASES:
        # update_or_create rather than create: "chatgpt" already exists as a
        # deactivated alias of ChatGPT.js, and alias_name is unique, so it is
        # repointed here rather than duplicated. Repointing is also the right
        # answer on the merits -- an advert saying "ChatGPT" in a coding
        # context means this, and never the npm package.
        SkillAlias.objects.update_or_create(
            alias_name=alias,
            defaults={
                "skill_id": skill.id,
                "source": "INTERNAL",
                "requires_context": True,
                "is_active": True,
            },
        )


def remove_skill(apps, schema_editor):
    """Put ``chatgpt`` back where it was and drop the rest.

    Reversible, but not lossless in one respect worth naming: ChatGPT.js is
    itself a mapping this project judged wrong, so reversing restores a known
    bad alias in a deactivated state rather than pretending it was right.
    """
    Skill = apps.get_model("scrape_jobs", "Skill")
    SkillAlias = apps.get_model("scrape_jobs", "SkillAlias")

    chatgpt_js = Skill.objects.filter(skill_name="ChatGPT.js").first()
    if chatgpt_js is not None:
        SkillAlias.objects.filter(alias_name="chatgpt").update(
            skill_id=chatgpt_js.id, source="MTO", requires_context=False,
            is_active=False)
    SkillAlias.objects.filter(
        alias_name__in=[a for a in CONTEXTUAL_ALIASES if a != "chatgpt"]
    ).delete()
    Skill.objects.filter(skill_name=SKILL_NAME).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("scrape_jobs", "0028_retire_geo_and_chatgpt_aliases"),
    ]

    operations = [
        migrations.RunPython(add_skill, remove_skill),
    ]
