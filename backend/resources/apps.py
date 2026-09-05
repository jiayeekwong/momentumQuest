from django.apps import AppConfig


class ResourcesConfig(AppConfig):
    name = 'resources'

    def ready(self):
        # Registers the post_delete receivers that remove privately stored
        # documents when their row goes away, which is what makes the retention
        # rule in the privacy notice true.
        from . import signals  # noqa: F401
