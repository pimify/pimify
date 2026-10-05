"""Phase 1.4 retirement: procurement mirrors are read-only (same contract as
inventory/). Tables are seeded with raw SQL — no managed model exists anymore
that could create rows.
"""
from django.db import connection
from django.test import TestCase

from procurement.models import ProductSupplier as MirrorPS, Supplier as MirrorSupplier


def seed_supplier(pk='sup-001'):
    with connection.cursor() as c:
        c.execute(
            'INSERT INTO "Suppliers" (id, name, email, phone, address)'
            ' VALUES (%s, %s, %s, %s, %s)',
            [pk, 'S', 's@x.com', '1', 'a'],
        )
    return MirrorSupplier.objects.get(pk=pk)


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
        seed_supplier()
        self.assertEqual(MirrorSupplier.objects.count(), 1)
        self.assertEqual(MirrorPS.objects.count(), 0)
