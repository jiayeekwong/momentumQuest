from django.db import migrations


class Migration(migrations.Migration):
    """Remove ScrapeLog from the scrape_jobs app STATE only. The physical table
    was already renamed to job_listings_scrapelog by job_listings.0006, which
    also re-created the model in the job_listings app state.
    """

    dependencies = [
        ("scrape_jobs", "0004_seed_skill_aliases"),
        ("job_listings", "0006_move_scrapelog"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.DeleteModel(name="ScrapeLog"),
            ],
            database_operations=[],
        ),
    ]
