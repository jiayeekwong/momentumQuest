from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


def backfill_listing_occupations(apps, schema_editor):
    JobListing = apps.get_model("job_listings", "JobListing")
    now = django.utils.timezone.now()
    listings = JobListing.objects.exclude(
        job_title_ref__canonical_occupation_id=None
    ).select_related("job_title_ref__canonical_occupation")

    for listing in listings.iterator():
        title_ref = listing.job_title_ref
        occupation = title_ref.canonical_occupation
        listing.canonical_occupation_id = occupation.id
        listing.standardized_job_title = occupation.preferred_label
        listing.occupation_seniority = title_ref.seniority
        listing.occupation_match_method = "JOB_TITLE_REFERENCE"
        listing.occupation_match_confidence = title_ref.occupation_match_confidence
        listing.occupation_review_status = "AUTO_MATCHED"
        listing.occupation_standardized_at = now
        listing.save(update_fields=[
            "canonical_occupation",
            "standardized_job_title",
            "occupation_seniority",
            "occupation_match_method",
            "occupation_match_confidence",
            "occupation_review_status",
            "occupation_standardized_at",
        ])


def clear_listing_occupations(apps, schema_editor):
    JobListing = apps.get_model("job_listings", "JobListing")
    JobListing.objects.update(
        canonical_occupation=None,
        standardized_job_title="",
        occupation_seniority="",
        occupation_specialization="",
        occupation_match_method="",
        occupation_match_confidence=None,
        occupation_review_status="PENDING",
        occupation_standardized_at=None,
    )


class Migration(migrations.Migration):

    dependencies = [
        ("scrape_jobs", "0006_occupation_taxonomies"),
        ("job_listings", "0007_jobapplication_available_from_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="joblisting",
            name="canonical_occupation",
            field=models.ForeignKey(blank=True, limit_choices_to={"taxonomy": "MASCO"}, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="job_listings", to="scrape_jobs.occupationconcept"),
        ),
        migrations.AddField(
            model_name="joblisting",
            name="occupation_match_confidence",
            field=models.DecimalField(blank=True, decimal_places=4, max_digits=5, null=True),
        ),
        migrations.AddField(
            model_name="joblisting",
            name="occupation_match_method",
            field=models.CharField(blank=True, max_length=50),
        ),
        migrations.AddField(
            model_name="joblisting",
            name="occupation_review_status",
            field=models.CharField(choices=[("PENDING", "Pending review"), ("AUTO_MATCHED", "Automatically matched"), ("VERIFIED", "Human verified"), ("REJECTED", "Rejected")], default="PENDING", max_length=20),
        ),
        migrations.AddField(
            model_name="joblisting",
            name="occupation_seniority",
            field=models.CharField(blank=True, max_length=30),
        ),
        migrations.AddField(
            model_name="joblisting",
            name="occupation_specialization",
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name="joblisting",
            name="occupation_standardized_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="joblisting",
            name="standardized_job_title",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.RunPython(backfill_listing_occupations, clear_listing_occupations),
    ]
