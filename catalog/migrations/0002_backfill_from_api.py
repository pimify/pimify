"""Phase 2 backfill: copy api catalog rows into catalog tables (new tables,
PKs preserved). Depends on api.0001 so api tables exist first. Reversible
(best-effort: rows whose api source vanished meanwhile orphan).
"""
from django.db import migrations

from catalog import backfill


def copy_forward(apps, schema_editor):
    backfill.forward()


def copy_reverse(apps, schema_editor):
    backfill.reverse()


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0001_initial'),
        ('api', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(copy_forward, copy_reverse),
    ]
