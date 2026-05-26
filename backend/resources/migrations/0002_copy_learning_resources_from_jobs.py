from django.db import migrations


def copy_learning_resources(apps, schema_editor):
    OldResource = apps.get_model("jobs", "LearningResource")
    NewResource = apps.get_model("resources", "LearningResource")

    for old in OldResource.objects.all():
        NewResource.objects.get_or_create(
            skill_id=old.skill_id,
            url=old.url,
            defaults={
                "title":     old.title,
                "platform":  old.platform,
                "type":      old.type,
                "is_active": old.is_active,
            },
        )


def reverse_copy(apps, schema_editor):
    apps.get_model("resources", "LearningResource").objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("resources", "0001_initial"),
        ("jobs", "0005_initial"),
    ]

    operations = [
        migrations.RunPython(copy_learning_resources, reverse_copy),
    ]
