from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("scrape_jobs", "0005_remove_scrapelog"),
    ]

    operations = [
        migrations.CreateModel(
            name="OccupationConcept",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("taxonomy", models.CharField(choices=[("MASCO", "MASCO"), ("ESCO", "ESCO")], max_length=10)),
                ("code", models.CharField(max_length=255)),
                ("preferred_label", models.CharField(max_length=255)),
                ("normalized_label", models.CharField(db_index=True, max_length=255)),
                ("alternative_labels", models.JSONField(blank=True, default=list)),
                ("description", models.TextField(blank=True)),
                ("parent_code", models.CharField(blank=True, max_length=255)),
                ("isco_code", models.CharField(blank=True, max_length=20)),
                ("version", models.CharField(max_length=30)),
                ("is_active", models.BooleanField(default=True)),
            ],
            options={"ordering": ["taxonomy", "preferred_label"]},
        ),
        migrations.CreateModel(
            name="OccupationMapping",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("relation", models.CharField(choices=[("EXACT", "Exact"), ("CLOSE", "Close"), ("BROAD", "Source is broader"), ("NARROW", "Source is narrower")], default="CLOSE", max_length=10)),
                ("confidence", models.DecimalField(decimal_places=4, default=1, max_digits=5)),
                ("verified", models.BooleanField(default=False)),
                ("notes", models.TextField(blank=True)),
                ("esco", models.ForeignKey(limit_choices_to={"taxonomy": "ESCO"}, on_delete=django.db.models.deletion.CASCADE, related_name="masco_mappings", to="scrape_jobs.occupationconcept")),
                ("masco", models.ForeignKey(limit_choices_to={"taxonomy": "MASCO"}, on_delete=django.db.models.deletion.CASCADE, related_name="esco_mappings", to="scrape_jobs.occupationconcept")),
            ],
        ),
        migrations.AddField(
            model_name="jobtitle",
            name="canonical_occupation",
            field=models.ForeignKey(blank=True, help_text="Canonical MASCO occupation for this raw market title.", limit_choices_to={"taxonomy": "MASCO"}, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="job_titles", to="scrape_jobs.occupationconcept"),
        ),
        migrations.AddField(
            model_name="jobtitle",
            name="occupation_match_confidence",
            field=models.DecimalField(blank=True, decimal_places=4, max_digits=5, null=True),
        ),
        migrations.AddField(
            model_name="jobtitle",
            name="occupation_match_method",
            field=models.CharField(blank=True, max_length=50),
        ),
        migrations.AddField(
            model_name="jobtitle",
            name="seniority",
            field=models.CharField(blank=True, max_length=30),
        ),
        migrations.AddConstraint(
            model_name="occupationconcept",
            constraint=models.UniqueConstraint(fields=("taxonomy", "code", "version"), name="unique_occupation_concept_version"),
        ),
        migrations.AddConstraint(
            model_name="occupationmapping",
            constraint=models.UniqueConstraint(fields=("masco", "esco"), name="unique_masco_esco_mapping"),
        ),
        migrations.AddConstraint(
            model_name="occupationmapping",
            constraint=models.CheckConstraint(condition=models.Q(("confidence__gte", 0), ("confidence__lte", 1)), name="occupation_mapping_confidence_range"),
        ),
    ]
