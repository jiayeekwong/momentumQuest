from django.db import migrations


def copy_scraped_jobs(apps, schema_editor):
    """Copy every ScrapedJob -> JobListing and ScrapedJobSkill -> JobSkill.

    Idempotent: keyed on source_url via get_or_create, so re-running it
    (or running it after the scraper has already written some rows) will
    not create duplicates.
    """
    ScrapedJob = apps.get_model("scrape_jobs", "ScrapedJob")
    ScrapedJobSkill = apps.get_model("scrape_jobs", "ScrapedJobSkill")
    JobListing = apps.get_model("job_listings", "JobListing")
    JobSkill = apps.get_model("job_listings", "JobSkill")

    for sj in ScrapedJob.objects.all().iterator():
        listing, _ = JobListing.objects.get_or_create(
            source_url=sj.source_url,
            defaults={
                "category":      sj.job_category,
                "job_title":     sj.job_title,
                "description":   sj.description,
                "salary_min":    sj.salary_min,
                "salary_max":    sj.salary_max,
                "salary_text":   sj.salary_text,
                "location":      sj.location,
                "job_type":      sj.job_type,
                "posted_date":   sj.posted_date,
                "company_name":  sj.company_name,
                "source_portal": sj.source_portal,
                "source_type":   "SCRAPED",
                "company":       None,
                "status":        "ACTIVE",
            },
        )

        for rel in ScrapedJobSkill.objects.filter(scraped_job=sj).select_related("skill"):
            JobSkill.objects.get_or_create(
                job=listing,
                skill=rel.skill,
                defaults={"importance_level": "MEDIUM"},
            )


def remove_scraped_listings(apps, schema_editor):
    """Reverse: delete the JobListing rows that came from scraping."""
    JobListing = apps.get_model("job_listings", "JobListing")
    # JobSkill rows cascade-delete with their JobListing.
    JobListing.objects.filter(source_type="SCRAPED").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("job_listings", "0002_joblisting_company_name_joblisting_job_type_and_more"),
        ("scrape_jobs", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(copy_scraped_jobs, remove_scraped_listings),
    ]
