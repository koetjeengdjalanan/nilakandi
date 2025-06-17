from django.apps import AppConfig


class NilakandiConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "nilakandi"

    def ready(self):
        import nilakandi.signals  # noqa: F401
