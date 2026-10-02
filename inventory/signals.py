"""Phase 1 (pure-PIM pivot): stock-aggregate ownership lives here now.

Behavior is intentionally identical to the old api.Stock.save() override:
after any Stock save, recompute the parent Product's denormalized
stock_quantity. api.Stock stays the canonical model this release; this
signal keeps it in sync so the write path has a single owner (inventory/).

Parity notes vs the old override:
- post_save covers the same cases as the save() override (create + update);
  bulk ops (bulk_create/queryset.update) bypassed both, before and now.
- Product is re-fetched and saved exactly like before (including the
  updated_at bump) — no silent behavior change.
- One deliberate improvement over the old code: post_delete also recomputes.
  The old override never handled deletes, leaving stale stock_quantity behind.
"""
from django.db.models import Sum
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from api.models import Product, Stock


def _recompute_stock_quantity(product):
    """Shared aggregate: sum all Stock rows into Product.stock_quantity."""
    total = Stock.objects.filter(product=product).aggregate(
        total=Sum('quantity'))['total']
    product.stock_quantity = total if total else 0
    product.save()


@receiver(post_save, sender=Stock)
def update_product_stock_cache(sender, instance, **kwargs):
    """Recompute Product.stock_quantity from all its Stock rows."""
    product = instance.product
    # Refresh in case the in-memory instance is stale.
    product.refresh_from_db(fields=['stock_quantity'])
    _recompute_stock_quantity(product)


@receiver(post_delete, sender=Stock)
def update_product_stock_cache_on_delete(sender, instance, **kwargs):
    """Recompute after a Stock row is deleted (the old override never did)."""
    # product_id survives without a query; the parent may itself be gone when
    # a Product deletion cascades into its Stock rows — then there is nothing
    # to update and we must not crash the cascade.
    product = Product.objects.filter(pk=instance.product_id).first()
    if product is None:
        return
    _recompute_stock_quantity(product)
