from django.apps import AppConfig


class JobListingsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'job_listings'

    def ready(self):
        from . import signals  # noqa: F401
