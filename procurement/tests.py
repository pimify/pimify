"""Phase 1: procurement mirrors are read-only (same contract as inventory/).

The mirrors share api tables; writes must go through the canonical api
models. Every write path raises NotImplementedError.
"""
from django.test import TestCase

from api.models import Supplier
from procurement.models import ProductSupplier as MirrorPS, Supplier as MirrorSupplier


class ProcurementMirrorReadOnlyTest(TestCase):
    def _supplier_kwargs(self):
        return {'name': 'S', 'email': 's@x.com', 'phone': '1', 'address': 'a'}

    def test_mirror_create_save_delete_raise(self):
        with self.assertRaises(NotImplementedError):
            MirrorSupplier.objects.create(**self._supplier_kwargs())
        with self.assertRaises(NotImplementedError):
            MirrorSupplier(**self._supplier_kwargs()).save()
        with self.assertRaises(NotImplementedError):
            MirrorSupplier(**self._supplier_kwargs()).delete()

    def test_mirror_bulk_and_queryset_writes_raise(self):
        with self.assertRaises(NotImplementedError):
            MirrorSupplier.objects.bulk_create([MirrorSupplier(**self._supplier_kwargs())])
        with self.assertRaises(NotImplementedError):
            MirrorSupplier.objects.all().update(name='X')
        with self.assertRaises(NotImplementedError):
            MirrorSupplier.objects.all().delete()

    def test_mirror_reads_still_work(self):
        Supplier.objects.create(**self._supplier_kwargs())
        self.assertEqual(MirrorSupplier.objects.count(), 1)
        self.assertEqual(MirrorPS.objects.count(), 0)
