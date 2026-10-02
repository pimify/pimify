"""Phase 2 backfill: copy api catalog rows into the new catalog tables.

New tables (no interference with live api models, still canonical until the
1.4 cutover). NanoID PKs are preserved so future FK remapping stays trivial.
Media keeps the same upload dir, so no file moves are needed.

Forward copies: Categories (kind=master), Products (price -> list_price,
category links, timestamps preserved), ProductImages -> ProductMedia
(role=gallery, sort=0, PKs preserved).

Reverse removes exactly the rows forward created (matched by api PKs, which
are random NanoIDs / ints no native catalog row can collide with).
Best-effort by design: rows whose api source vanished meanwhile orphan.
"""
from api.models import Category as ApiCategory
from api.models import Product as ApiProduct
from api.models import ProductImage as ApiProductImage
from catalog.models import Category, Product, ProductCategory, ProductMedia


def forward(apps=None):
    """Copy api -> catalog. `apps` accepted for migration use; ignored (live models)."""
    for c in ApiCategory.objects.all():
        Category.objects.update_or_create(
            id=c.id,
            defaults={'name': c.name, 'slug': c.slug, 'kind': 'master', 'sort': 0},
        )
    for p in ApiProduct.objects.prefetch_related('categories'):
        obj, _ = Product.objects.update_or_create(
            id=p.id,
            defaults={
                'sku': p.sku,
                'name': p.name,
                'description': p.description,
                'list_price': p.price,
                'is_active': p.is_active,
            },
        )
        # Timestamps: auto_now(_add) overwrite on save, so restore via update.
        Product.objects.filter(pk=obj.pk).update(
            created_at=p.created_at, updated_at=p.updated_at)
        for c in p.categories.all():
            ProductCategory.objects.get_or_create(
                product=obj, category_id=c.id,
                defaults={'is_primary': False},
            )
    for img in ApiProductImage.objects.all():
        ProductMedia.objects.update_or_create(
            id=img.id,
            defaults={
                'product_id': img.product_id,
                'role': 'gallery',
                'sort': 0,
                'file': img.image,
                'alt_text': img.alt_text,
            },
        )


def reverse(apps=None):
    """Remove exactly the rows forward() created (matched by api PKs)."""
    api_product_ids = set(ApiProduct.objects.values_list('id', flat=True))
    api_category_ids = set(ApiCategory.objects.values_list('id', flat=True))
    api_image_ids = set(ApiProductImage.objects.values_list('id', flat=True))
    ProductMedia.objects.filter(id__in=api_image_ids).delete()
    ProductCategory.objects.filter(product_id__in=api_product_ids).delete()
    Product.objects.filter(id__in=api_product_ids).delete()
    Category.objects.filter(id__in=api_category_ids).delete()
