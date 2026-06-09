from django.db import migrations


def backfill_job_titles(apps, schema_editor):
    """Create a JobTitle for each distinct JobListing.job_title and point the
    listing's job_title_ref at it. Category is taken from the listing itself.
    Idempotent via get_or_create on the unique title_name.
    """
    JobListing = apps.get_model("job_listings", "JobListing")
    JobTitle = apps.get_model("scrape_jobs", "JobTitle")

    for listing in JobListing.objects.all().iterator():
        title = (listing.job_title or "").strip()
        if not title:
            continue

        job_title, created = JobTitle.objects.get_or_create(
            title_name=title,
            defaults={"category": listing.category},
        )
        # Fill in a category if the title was first seen without one.
        if not created and job_title.category_id is None and listing.category_id:
            job_title.category = listing.category
            job_title.save(update_fields=["category"])

        if listing.job_title_ref_id != job_title.id:
            listing.job_title_ref = job_title
            listing.save(update_fields=["job_title_ref"])


def clear_job_titles(apps, schema_editor):
    JobListing = apps.get_model("job_listings", "JobListing")
    JobTitle = apps.get_model("scrape_jobs", "JobTitle")
    JobListing.objects.update(job_title_ref=None)
    JobTitle.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("job_listings", "0004_joblisting_job_title_ref"),
        ("scrape_jobs", "0003_jobtitle_skillalias"),
    ]

    operations = [
        migrations.RunPython(backfill_job_titles, clear_job_titles),
    ]
