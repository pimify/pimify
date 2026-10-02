"""Phase 1 (pure-PIM pivot): WMS read mirrors.

Unmanaged models sharing the api tables (managed=False → no migrations,
no table creation). api/ stays canonical this release; inventory/ owns the
stock-aggregate write logic via signals.py. Physical extraction (real table
move) happens in a later phase.

Mirrors are READ-ONLY and enforce it: every write path raises
NotImplementedError pointing at the canonical api model. This is required,
not cosmetic — the aggregate signal binds api.Stock only, so a write
through a mirror would silently skip it and corrupt stock_quantity.
Remove the guards in Phase 1.4 when mirrors become canonical.
"""
from django.db import models

from api.models import NanoIDField


class _ReadOnlyQuerySet(models.QuerySet):
    """Block bulk writes that would bypass the instance guards (and signals)."""

    def _deny(self):
        raise NotImplementedError(
            f"{self.model._meta.label} is a read-only mirror (Phase 1 transition); "
            "write via the canonical api.* model instead."
        )

    def update(self, *args, **kwargs):
        self._deny()

    def delete(self):
        self._deny()

    def bulk_create(self, *args, **kwargs):
        self._deny()


ReadOnlyManagerBase = models.Manager.from_queryset(_ReadOnlyQuerySet)


class ReadOnlyManager(ReadOnlyManagerBase):
    """Manager that denies write entry points up front with a clear message.

    Needed in addition to the queryset guards: Manager.create() builds the
    instance directly, so without this the FK type check would raise a
    confusing ValueError instead of our NotImplementedError.
    """

    def _deny(self):
        raise NotImplementedError(
            f"{self.model._meta.label} is a read-only mirror (Phase 1 transition); "
            "write via the canonical api.* model instead."
        )

    def create(self, *args, **kwargs):
        self._deny()

    def get_or_create(self, *args, **kwargs):
        self._deny()

    def update_or_create(self, *args, **kwargs):
        self._deny()


class ReadOnlyMirrorMixin:
    """Instance-level write guard for mirror models (save/delete)."""

    def save(self, *args, **kwargs):
        raise NotImplementedError(
            f"{self._meta.label} is a read-only mirror (Phase 1 transition); "
            f"write via the canonical api.{self.__class__.__name__} model instead."
        )

    def delete(self, *args, **kwargs):
        raise NotImplementedError(
            f"{self._meta.label} is a read-only mirror (Phase 1 transition); "
            f"write via the canonical api.{self.__class__.__name__} model instead."
        )


class Warehouse(ReadOnlyMirrorMixin, models.Model):
    """Mirror of api.Warehouse (db_table='Warehouses'). Read-only view."""

    id = NanoIDField(primary_key=True)
    name = models.CharField(max_length=100)
    address = models.TextField()

    objects = ReadOnlyManager()

    class Meta:
        managed = False
        db_table = 'Warehouses'
        verbose_name_plural = 'Warehouses'

    def __str__(self):
        return self.name


class Stock(ReadOnlyMirrorMixin, models.Model):
    """Mirror of api.Stock (db_table='Stocks'). Read-only view."""

    id = NanoIDField(primary_key=True)
    product = models.ForeignKey('api.Product', on_delete=models.DO_NOTHING, related_name='+')
    quantity = models.IntegerField(default=0)
    warehouse = models.ForeignKey(Warehouse, on_delete=models.DO_NOTHING, related_name='+')

    objects = ReadOnlyManager()

    class Meta:
        managed = False
        db_table = 'Stocks'
        verbose_name_plural = 'Stocks'

    def __str__(self):
        return str(self.id)
