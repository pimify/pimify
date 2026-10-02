"""Phase 1 (pure-PIM pivot): procurement read mirrors.

Unmanaged models sharing the api tables (managed=False → no migrations,
no table creation). api/ stays canonical this release. Physical extraction
(real table move) happens in a later phase.

Mirrors are READ-ONLY and enforce it: every write path raises
NotImplementedError pointing at the canonical api model. Remove the guards
if/when mirrors become canonical.
"""
from django.db import models

from api.models import NanoIDField
from inventory.models import ReadOnlyManager, ReadOnlyMirrorMixin


class Supplier(ReadOnlyMirrorMixin, models.Model):
    """Mirror of api.Supplier (db_table='Suppliers'). Read-only view."""

    id = NanoIDField(primary_key=True)
    name = models.CharField(max_length=100)
    email = models.EmailField()
    phone = models.CharField(max_length=20)
    address = models.TextField()

    objects = ReadOnlyManager()

    class Meta:
        managed = False
        db_table = 'Suppliers'
        verbose_name_plural = 'Suppliers'

    def __str__(self):
        return self.name


class ProductSupplier(ReadOnlyMirrorMixin, models.Model):
    """Mirror of api.ProductSupplier (db_table='Product Suppliers'). Read-only view."""

    id = NanoIDField(primary_key=True)
    product = models.ForeignKey('api.Product', on_delete=models.DO_NOTHING, related_name='+')
    supplier = models.ForeignKey(Supplier, on_delete=models.DO_NOTHING, related_name='+')
    cost_price = models.DecimalField(max_digits=10, decimal_places=2)
    lead_time = models.IntegerField(help_text="Lead time in days")

    objects = ReadOnlyManager()

    class Meta:
        managed = False
        db_table = 'Product Suppliers'
        verbose_name_plural = 'Product Suppliers'

    def __str__(self):
        return self.id
