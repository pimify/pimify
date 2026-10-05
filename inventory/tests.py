"""Phase 1.4 retirement tests: api WMS models are gone (option A), the
unmanaged mirrors read the surviving tables, and stay read-only.

Mirror tables are seeded with raw SQL: no managed model exists anymore that
could create rows, which is exactly the point — nothing in the codebase can
write these tables through the ORM.
"""
from django.db import connection
from django.test import TestCase

from api.models import Product
from inventory.models import Stock as MirrorStock, Warehouse as MirrorWarehouse


def seed_warehouse(pk='wh-001', name='W1'):
    with connection.cursor() as c:
        c.execute(
            'INSERT INTO "Warehouses" (id, name, address) VALUES (%s, %s, %s)',
            [pk, name, 'addr'],
        )
    return MirrorWarehouse.objects.get(pk=pk)


def seed_stock(pk='st-001', product_id=None, quantity=1, warehouse_id='wh-001'):
    with connection.cursor() as c:
        c.execute(
            'INSERT INTO "Stocks" (id, product_id, quantity, warehouse_id)'
            ' VALUES (%s, %s, %s, %s)',
            [pk, product_id, quantity, warehouse_id],
        )
    return MirrorStock.objects.get(pk=pk)


class RetiredApiModelsTest(TestCase):
    def test_wms_models_are_gone_from_api_state(self):
        # Retirement guard: re-adding Supplier/Stock/etc. to api/models.py
        # must be a deliberate, reviewed act — never an accident.
        import api.models as api_models
        for name in ('Supplier', 'ProductSupplier', 'Warehouse', 'Stock'):
            self.assertFalse(
                hasattr(api_models, name), f'api.{name} resurrected?')


class MirrorReadOnlyTest(TestCase):
    """Writes through unmanaged mirrors must fail loudly (no aggregate
    signal exists anymore to keep any denormalized column in sync)."""

    def setUp(self):
        self.product = Product.objects.create(name="Widget", sku="RO-001", price=10)
        self.mirror_warehouse = seed_warehouse()
        seed_stock(product_id=self.product.pk, quantity=3)

    def _mirror_stock(self, **kwargs):
        defaults = {'product': self.product, 'quantity': 1, 'warehouse': self.mirror_warehouse}
        defaults.update(kwargs)
        return MirrorStock(**defaults)

    def test_mirror_create_raises(self):
        with self.assertRaises(NotImplementedError):
            MirrorStock.objects.create(
                product=self.product, quantity=1, warehouse=self.mirror_warehouse)

    def test_mirror_get_or_create_raises(self):
        with self.assertRaises(NotImplementedError):
            MirrorStock.objects.get_or_create(
                product=self.product, quantity=1, warehouse=self.mirror_warehouse)

    def test_mirror_save_raises(self):
        with self.assertRaises(NotImplementedError):
            self._mirror_stock().save()

    def test_mirror_delete_raises(self):
        with self.assertRaises(NotImplementedError):
            self._mirror_stock().delete()

    def test_mirror_bulk_create_raises(self):
        with self.assertRaises(NotImplementedError):
            MirrorStock.objects.bulk_create([self._mirror_stock()])

    def test_mirror_queryset_update_and_delete_raise(self):
        with self.assertRaises(NotImplementedError):
            MirrorStock.objects.all().update(quantity=1)
        with self.assertRaises(NotImplementedError):
            MirrorStock.objects.all().delete()

    def test_mirror_reads_still_work(self):
        self.assertEqual(
            MirrorStock.objects.filter(product=self.product).count(), 1)
        self.assertEqual(MirrorWarehouse.objects.count(), 1)

    def test_tables_survived_model_retirement(self):
        # Option (a) proof: tables exist and hold rows after DeleteModel.
        with connection.cursor() as c:
            tables = {r[0] for r in c.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
        for table in ('Warehouses', 'Stocks', 'Suppliers', 'Product Suppliers'):
            self.assertIn(table, tables)
