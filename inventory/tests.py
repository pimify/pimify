"""Phase 1 parity tests: the stock-aggregate signal must behave exactly like
the old api.Stock.save() override it replaced.
"""
from django.test import TestCase

from api.models import Product, Stock, Warehouse
from inventory.models import Stock as MirrorStock, Warehouse as MirrorWarehouse


class StockAggregateSignalTest(TestCase):
    def setUp(self):
        self.warehouse = Warehouse.objects.create(name="W1", address="addr")
        self.product = Product.objects.create(name="Widget", sku="W-001", price=10)

    def test_create_updates_product_quantity(self):
        self.assertEqual(self.product.stock_quantity, 0)
        Stock.objects.create(product=self.product, quantity=5, warehouse=self.warehouse)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 5)

    def test_multiple_rows_sum(self):
        Stock.objects.create(product=self.product, quantity=5, warehouse=self.warehouse)
        Stock.objects.create(product=self.product, quantity=3, warehouse=self.warehouse)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 8)

    def test_update_recomputes_not_appends(self):
        stock = Stock.objects.create(product=self.product, quantity=5, warehouse=self.warehouse)
        stock.quantity = 2
        stock.save()
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 2)

    def test_delete_recomputes_quantity(self):
        Stock.objects.create(product=self.product, quantity=5, warehouse=self.warehouse)
        doomed = Stock.objects.create(product=self.product, quantity=3, warehouse=self.warehouse)
        doomed.delete()
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 5)

    def test_delete_last_row_resets_to_zero(self):
        stock = Stock.objects.create(product=self.product, quantity=5, warehouse=self.warehouse)
        stock.delete()
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 0)

    def test_product_cascade_delete_does_not_crash(self):
        # Product delete cascades into Stock rows; the post_delete receiver
        # must tolerate the already-gone parent instead of crashing the cascade.
        Stock.objects.create(product=self.product, quantity=5, warehouse=self.warehouse)
        pk = self.product.pk
        self.product.delete()
        self.assertFalse(Product.objects.filter(pk=pk).exists())
        self.assertEqual(Stock.objects.filter(product_id=pk).count(), 0)


class MirrorReadOnlyTest(TestCase):
    """Writes through unmanaged mirrors must fail loudly: the aggregate
    signal binds api.Stock only, so a silent mirror write would corrupt
    stock_quantity without any error."""

    def setUp(self):
        self.product = Product.objects.create(name="Widget", sku="RO-001", price=10)
        api_warehouse = Warehouse.objects.create(name="W1", address="addr")
        # Mirror instances must be read back through the mirror (FK type check).
        self.mirror_warehouse = MirrorWarehouse.objects.get(pk=api_warehouse.pk)

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
        Stock.objects.create(product=self.product, quantity=3, warehouse=Warehouse.objects.get(pk=self.mirror_warehouse.pk))
        self.assertEqual(MirrorStock.objects.filter(product=self.product).count(), 1)
        self.assertEqual(MirrorWarehouse.objects.count(), 1)
