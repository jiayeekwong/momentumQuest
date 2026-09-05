"""Sanitize job descriptions written before the sanitizer existed.

The model now sanitizes on save, so nothing new can arrive with script in it.
That says nothing about the rows already stored: every scraped description was
copied from an employer's HTML and every company-posted one came straight from
a form, and all of them are rendered with dangerouslySetInnerHTML.

Idempotent, so re-running is harmless.
"""

from django.db import migrations

from config.sanitization import sanitize_html, sanitize_text


def sanitize(apps, schema_editor):
    JobListing = apps.get_model("job_listings", "JobListing")
    changed = []
    for listing in JobListing.objects.only(
            "id", "description", "job_title", "company_name").iterator(chunk_size=500):
        description = sanitize_html(listing.description)
        title = sanitize_text(listing.job_title)
        company = sanitize_text(listing.company_name)
        if (description, title, company) != (
                listing.description, listing.job_title, listing.company_name):
            listing.description = description
            listing.job_title = title
            listing.company_name = company
            changed.append(listing)
        if len(changed) >= 500:
            JobListing.objects.bulk_update(
                changed, ["description", "job_title", "company_name"])
            changed = []
    if changed:
        JobListing.objects.bulk_update(
            changed, ["description", "job_title", "company_name"])


class Migration(migrations.Migration):

    dependencies = [
        ("job_listings", "0019_joblisting_market_role_joblisting_matched_alias_and_more"),
    ]

    operations = [
        # Irreversible: the removed markup was an injection vector, and there
        # is nothing to restore it to that would be safe.
        migrations.RunPython(sanitize, migrations.RunPython.noop),
    ]
