from django.db import migrations


# alias -> canonical skill_name. Aliases are only created when the canonical
# skill already exists in the Skill table, so this is safe on any dataset.
ALIASES = {
    "JS":          "JavaScript",
    "TS":          "TypeScript",
    "React.js":    "React",
    "ReactJS":     "React",
    "Node":        "Node.js",
    "NodeJS":      "Node.js",
    "k8s":         "Kubernetes",
    "Postgres":    "PostgreSQL",
    "GCP":         "Google Cloud",
    "Golang":      "Go",
    "HTML5":       "HTML",
    "CSS3":        "CSS",
    "ML":          "Machine Learning",
    "scikit-learn": "Scikit-learn",
    "Tailwind":    "Tailwind CSS",
}


def seed_aliases(apps, schema_editor):
    Skill = apps.get_model("scrape_jobs", "Skill")
    SkillAlias = apps.get_model("scrape_jobs", "SkillAlias")

    for alias, canonical in ALIASES.items():
        skill = Skill.objects.filter(skill_name__iexact=canonical).first()
        if skill is None:
            continue
        SkillAlias.objects.get_or_create(
            alias_name=alias,
            defaults={"skill": skill},
        )


def unseed_aliases(apps, schema_editor):
    SkillAlias = apps.get_model("scrape_jobs", "SkillAlias")
    SkillAlias.objects.filter(alias_name__in=list(ALIASES.keys())).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("scrape_jobs", "0003_jobtitle_skillalias"),
    ]

    operations = [
        migrations.RunPython(seed_aliases, unseed_aliases),
    ]
