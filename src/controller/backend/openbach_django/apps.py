from django.apps import AppConfig


class OpenBachConfig(AppConfig):
    name = 'openbach_django'
    verbose_name = 'OpenBACH django application'

    def ready(self):
        from . import signals
