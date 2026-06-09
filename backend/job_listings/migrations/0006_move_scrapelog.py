from django.db import migrations, models


class Migration(migrations.Migration):
    """Move ScrapeLog from the scrape_jobs app into job_listings WITHOUT losing
    data: the physical table is renamed scrape_jobs_scrapelog -> job_listings_scrapelog
    (database_operations), while Django's model state gains the model here
    (state_operations). The matching scrape_jobs migration removes it from that
    app's state only.
    """

    dependencies = [
        ("job_listings", "0005_backfill_job_titles"),
        ("scrape_jobs", "0004_seed_skill_aliases"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name="ScrapeLog",
                    fields=[
                        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                        ("started_at", models.DateTimeField(auto_now_add=True)),
                        ("finished_at", models.DateTimeField(blank=True, null=True)),
                        ("status", models.CharField(choices=[("SUCCESS", "Success"), ("BLOCKED", "Blocked by Anti-Bot"), ("PARTIAL", "Partial (some pages blocked)"), ("FAILED", "Failed")], default="FAILED", max_length=20)),
                        ("roles_scraped", models.JSONField(default=list)),
                        ("pages_attempted", models.IntegerField(default=0)),
                        ("jobs_scraped", models.IntegerField(default=0)),
                        ("jobs_created", models.IntegerField(default=0)),
                        ("jobs_updated", models.IntegerField(default=0)),
                        ("blocked_count", models.IntegerField(default=0)),
                        ("error_message", models.TextField(blank=True)),
                    ],
                    options={
                        "ordering": ["-started_at"],
                    },
                ),
            ],
            database_operations=[
                migrations.RunSQL(
                    sql="ALTER TABLE scrape_jobs_scrapelog RENAME TO job_listings_scrapelog;",
                    reverse_sql="ALTER TABLE job_listings_scrapelog RENAME TO scrape_jobs_scrapelog;",
                ),
            ],
        ),
    ]
