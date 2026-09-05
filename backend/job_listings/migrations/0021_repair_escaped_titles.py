"""Undo the entity-escaping that 0020 left in plain-text titles.

``sanitize_text`` originally returned nh3's HTML output, which escapes a bare
ampersand. Job titles and company names are rendered by React as text nodes,
which escape again on output, so "R&D Software Engineer" reached the student
as the literal "R&amp;D Software Engineer" -- and 42 of the scraped titles
contain an ampersand.

The sanitizer now decodes entities back to characters for these fields, and
this repairs the rows written before it did. Re-running sanitize_text is
enough: it is idempotent, and on an already-correct title it changes nothing.
"""

from django.db import migrations

from config.sanitization import sanitize_text


def repair(apps, schema_editor):
    JobListing = apps.get_model("job_listings", "JobListing")

    changed = []
    for listing in JobListing.objects.only(
            "id", "job_title", "company_name").iterator(chunk_size=500):
        title = sanitize_text(listing.job_title)
        company = sanitize_text(listing.company_name)
        if (title, company) != (listing.job_title, listing.company_name):
            listing.job_title = title
            listing.company_name = company
            changed.append(listing)
        if len(changed) >= 500:
            JobListing.objects.bulk_update(changed, ["job_title", "company_name"])
            changed = []
    if changed:
        JobListing.objects.bulk_update(changed, ["job_title", "company_name"])


class Migration(migrations.Migration):

    dependencies = [
        ("job_listings", "0020_sanitize_stored_html"),
    ]

    operations = [
        # Irreversible: re-escaping would reintroduce the display bug.
        migrations.RunPython(repair, migrations.RunPython.noop),
    ]
