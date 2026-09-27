from django.apps import AppConfig


class AccountsConfig(AppConfig):
    name = 'accounts'

    def ready(self):
        # Registers the checks that report accounts missing their profile.
        # Imported for the side effect; nothing here calls into it.
        from . import checks  # noqa: F401
