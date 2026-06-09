from django.apps import AppConfig


class ScrapeJobsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'scrape_jobs'
    verbose_name = 'Job Market Data'
