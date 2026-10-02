from django.apps import AppConfig


class InventoryConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "inventory"
    verbose_name = "Inventory (WMS mirror — Phase 1 transition)"

    def ready(self):
        # Wire stock-aggregate signals (owns the api.Stock write path).
        from . import signals  # noqa: F401
