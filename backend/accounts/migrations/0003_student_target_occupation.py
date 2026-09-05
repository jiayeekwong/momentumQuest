from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


def backfill_target_occupations(apps, schema_editor):
    StudentTargetJob = apps.get_model("accounts", "StudentTargetJob")
    StudentTargetOccupation = apps.get_model("accounts", "StudentTargetOccupation")

    existing_pairs = set()
    targets = StudentTargetJob.objects.exclude(
        job_title__canonical_occupation_id=None
    ).select_related("job_title")
    rows = []
    for target in targets.iterator():
        pair = (target.student_id, target.job_title.canonical_occupation_id)
        if pair in existing_pairs:
            continue
        existing_pairs.add(pair)
        rows.append(StudentTargetOccupation(
            student_id=target.student_id,
            occupation_id=target.job_title.canonical_occupation_id,
            added_time=target.added_time,
        ))
    StudentTargetOccupation.objects.bulk_create(rows)


def clear_target_occupations(apps, schema_editor):
    StudentTargetOccupation = apps.get_model("accounts", "StudentTargetOccupation")
    StudentTargetOccupation.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("scrape_jobs", "0006_occupation_taxonomies"),
        ("accounts", "0002_remove_student_desired_job_category_studenttargetjob"),
    ]

    operations = [
        migrations.CreateModel(
            name="StudentTargetOccupation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("preferred_seniority", models.CharField(blank=True, max_length=30)),
                ("preferred_specialization", models.CharField(blank=True, max_length=100)),
                ("added_time", models.DateTimeField(default=django.utils.timezone.now)),
                ("occupation", models.ForeignKey(limit_choices_to={"taxonomy": "MASCO"}, on_delete=django.db.models.deletion.CASCADE, related_name="targeting_students", to="scrape_jobs.occupationconcept")),
                ("student", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="target_occupations", to="accounts.student")),
            ],
        ),
        migrations.AddConstraint(
            model_name="studenttargetoccupation",
            constraint=models.UniqueConstraint(fields=("student", "occupation"), name="unique_student_target_occupation"),
        ),
        migrations.RunPython(backfill_target_occupations, clear_target_occupations),
    ]
