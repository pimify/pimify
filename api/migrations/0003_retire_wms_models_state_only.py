# Phase 1.4 cutover, option (a): retire the api WMS models WITHOUT touching
# their tables. Supplier/ProductSupplier/Warehouse/Stock leave api state via
# SeparateDatabaseAndState (empty database_operations) so the unmanaged
# inventory/procurement mirrors keep reading the intact tables.
# stock_quantity is dropped for real: nothing reads or writes it anymore
# (public API serves catalog, the aggregate signal is deleted with api.Stock).
# Generated operations were produced by `makemigrations api` (Django 6.1.1)
# and hand-split into state-only vs real database operations.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0002_remove_organization_api_keys_apikey_organization"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AlterUniqueTogether(
                    name="productsupplier",
                    unique_together=None,
                ),
                migrations.RemoveField(
                    model_name="productsupplier",
                    name="product",
                ),
                migrations.RemoveField(
                    model_name="productsupplier",
                    name="supplier",
                ),
                migrations.RemoveIndex(
                    model_name="stock",
                    name="Stocks_id_634175_idx",
                ),
                migrations.RemoveIndex(
                    model_name="supplier",
                    name="Suppliers_id_f3b6aa_idx",
                ),
                migrations.RemoveIndex(
                    model_name="supplier",
                    name="Suppliers_name_6427cd_idx",
                ),
                migrations.RemoveIndex(
                    model_name="warehouse",
                    name="Warehouses_id_61e763_idx",
                ),
                migrations.RemoveIndex(
                    model_name="warehouse",
                    name="Warehouses_name_691f9f_idx",
                ),
                migrations.DeleteModel(
                    name="ProductSupplier",
                ),
                migrations.DeleteModel(
                    name="Supplier",
                ),
                migrations.DeleteModel(
                    name="Stock",
                ),
                migrations.DeleteModel(
                    name="Warehouse",
                ),
            ],
            database_operations=[],
        ),
        migrations.RemoveField(
            model_name="product",
            name="stock_quantity",
        ),
    ]
