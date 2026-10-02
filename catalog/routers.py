"""Phase 2.2: read API for the pure-PIM catalog surface.

Mounted at /api/v1/catalog/ (api/main.py). Legacy /public/ + /private/
paths are untouched — they keep serving api models until the 1.4 cutover.
All endpoints require X-API-Key (shared api.auth.header_key). Writes are
deferred (POST/PATCH) until reads are stable.
"""
from typing import List, Optional

from django.db.models import Prefetch, Q
from django.http import Http404
from django.shortcuts import get_object_or_404
from ninja import Query, Router, Schema, Status
from ninja.pagination import paginate, PageNumberPagination

from api.auth import header_key
from api.schemas import Error
from .models import (
    AssociationTypes,
    Attribute,
    AttributeSet,
    Category,
    CategoryKind,
    Channel,
    CompletenessRule,
    Locale,
    Product,
    ProductAssociation,
    ProductCategory,
    ProductMedia,
    ProductValue,
    ProductVariant,
    VariantValue,
)
from .schemas import (
    AssociationSchema,
    AttributeSchema,
    CategoryTreeSchema,
    ChannelSchema,
    CompletenessSchema,
    FamilyDetailSchema,
    FamilyListSchema,
    LocaleSchema,
    MediaSchema,
    ProductDetailSchema,
    ProductListSchema,
    VariantSchema,
    resolve_attribute_value,
)

router = Router()


def _or_404(make, error):
    """get_object_or_404 that honors the declared 404: Error envelope.

    Bare get_object_or_404 raises into Ninja's default handler, which renders
    {"detail": ...} — contradicting every endpoint's documented Error shape.
    Returns Status (not a plain tuple) because @paginate only understands
    Status for non-200 returns — plain tuples get validated as 200 payloads.
    """
    try:
        return make()
    except Http404:
        return Status(404, {'error': error})

# Prefetch recipes (N+1 guards for nested schemas) ---------------------------

_VALUE_SELECT = ('attribute', 'option', 'channel', 'locale')


def _product_values():
    return Prefetch(
        'values',
        queryset=ProductValue.objects.select_related(*_VALUE_SELECT)
        .prefetch_related('options').order_by('attribute__code'),
    )


def _variant_values():
    return Prefetch(
        'values',
        queryset=VariantValue.objects.select_related(*_VALUE_SELECT)
        .prefetch_related('options').order_by('attribute__code'),
    )


def _variants_with_values():
    return Prefetch(
        'variants',
        queryset=ProductVariant.objects.prefetch_related(_variant_values()).order_by('sort'),
    )


def _product_detail_qs():
    return (Product.objects.select_related('family', 'brand').prefetch_related(
        Prefetch('category_links',
                 queryset=ProductCategory.objects.select_related('category')),
        _product_values(),
        _variants_with_values(),
        Prefetch('media',
                 queryset=ProductMedia.objects.select_related('variant', 'channel', 'locale')
                 .order_by('sort')),
    ))


# Reference data --------------------------------------------------------------

@router.get("/locales/", auth=header_key,
            response={200: List[LocaleSchema]}, tags=["Locale"])
@paginate(PageNumberPagination, page_size=20)
def list_locales(request):
    """List locales."""
    return Locale.objects.order_by('code')


@router.get("/channels/", auth=header_key,
            response={200: List[ChannelSchema]}, tags=["Channel"])
@paginate(PageNumberPagination, page_size=20)
def list_channels(request):
    """List channels."""
    return Channel.objects.prefetch_related('locales').order_by('code')


# Families + attributes --------------------------------------------------------

@router.get("/families/", auth=header_key,
            response={200: List[FamilyListSchema]}, tags=["Family"])
@paginate(PageNumberPagination, page_size=20)
def list_families(request):
    """List attribute families."""
    return AttributeSet.objects.order_by('code')


@router.get("/families/{code}/", auth=header_key,
            response={200: FamilyDetailSchema, 404: Error}, tags=["Family"])
def retrieve_family(request, code: str):
    """Family detail with group + attribute codes."""
    return _or_404(
        lambda: get_object_or_404(
            AttributeSet.objects.prefetch_related('groups', 'attributes'), code=code),
        f'Family {code} not found.')


@router.get("/attributes/", auth=header_key,
            response={200: List[AttributeSchema]}, tags=["Attribute"])
@paginate(PageNumberPagination, page_size=20)
def list_attributes(request):
    """List attribute definitions with their options."""
    return Attribute.objects.prefetch_related('options').order_by('code')


@router.get("/attributes/{code}/", auth=header_key,
            response={200: AttributeSchema, 404: Error}, tags=["Attribute"])
def retrieve_attribute(request, code: str):
    """Attribute definition with its options."""
    return _or_404(
        lambda: get_object_or_404(
            Attribute.objects.prefetch_related('options'), code=code),
        f'Attribute {code} not found.')


# Categories ------------------------------------------------------------------

@router.get("/categories/tree/", auth=header_key,
            response={200: List[CategoryTreeSchema], 400: Error}, tags=["Category"])
def category_tree(request, kind: str = "master"):
    """Category tree (nested children) for one taxonomy kind."""
    if kind not in CategoryKind.values:
        return 400, {'error': f'Unknown kind {kind!r}. Valid: {sorted(CategoryKind.values)}.'}
    cats = list(Category.objects.filter(kind=kind).order_by('sort', 'name'))
    by_parent = {}
    for cat in cats:
        by_parent.setdefault(cat.parent_id, []).append(cat)

    def node(cat):
        return {
            'id': cat.id,
            'name': cat.name,
            'slug': cat.slug,
            'kind': cat.kind,
            'sort': cat.sort,
            'children': [node(child) for child in by_parent.get(cat.id, [])],
        }

    return [node(root) for root in by_parent.get(None, [])]


# Products, variants, media, relations ------------------------------------------

class CatalogProductFilter(Schema):
    is_active: Optional[bool] = None
    search: Optional[str] = None
    family: Optional[str] = None


@router.get("/products/", auth=header_key,
            response={200: List[ProductListSchema]}, tags=["Product"])
@paginate(PageNumberPagination, page_size=20)
def list_catalog_products(request, filters: CatalogProductFilter = Query(...)):
    """Paginated catalog products with optional search/active/family filters."""
    products = Product.objects.select_related('family', 'brand').order_by('sku')
    if filters.is_active is not None:
        products = products.filter(is_active=filters.is_active)
    if filters.family:
        products = products.filter(family_id=filters.family)
    if filters.search:
        products = products.filter(
            Q(name__icontains=filters.search)
            | Q(sku__icontains=filters.search)
            | Q(description__icontains=filters.search)
        )
    return products


@router.get("/products/{id}/", auth=header_key,
            response={200: ProductDetailSchema, 404: Error}, tags=["Product"])
def retrieve_catalog_product(request, id: str):
    """Catalog product detail: categories, values, variants (+values), media."""
    return _or_404(
        lambda: get_object_or_404(_product_detail_qs(), id=id),
        f'Product {id} not found.')


@router.get("/products/{id}/variants/", auth=header_key,
            response={200: List[VariantSchema], 404: Error}, tags=["Variant"])
def list_product_variants(request, id: str):
    """Variants of one product, each with its axis values.

    Deliberately unpaginated: @paginate cannot return non-200 statuses
    (it paginates the error payload as if it were the 200 list). Variant
    collections per product are small; revisit if that changes.
    """
    product = _or_404(
        lambda: get_object_or_404(Product, id=id), f'Product {id} not found.')
    if isinstance(product, Status):
        return product
    return (ProductVariant.objects.filter(product=product)
            .prefetch_related(_variant_values()).order_by('sort'))


@router.get("/variants/{sku}/", auth=header_key,
            response={200: VariantSchema, 404: Error}, tags=["Variant"])
def retrieve_variant(request, sku: str):
    """Single variant by SKU with its axis values."""
    return _or_404(
        lambda: get_object_or_404(
            ProductVariant.objects.prefetch_related(_variant_values()), sku=sku),
        f'Variant {sku} not found.')


@router.get("/products/{id}/media/", auth=header_key,
            response={200: List[MediaSchema], 404: Error}, tags=["Media"])
def list_product_media(request, id: str):
    """Product media feed: product-owned rows plus variant rows (variant sku set).

    Supersedes legacy /public/products/{id}/images/ (removed in 1.4 cutover).
    Unpaginated (see variants endpoint note on @paginate + error statuses).
    """
    product = _or_404(
        lambda: get_object_or_404(Product, id=id), f'Product {id} not found.')
    if isinstance(product, Status):
        return product
    return (ProductMedia.objects
            .filter(Q(product=product) | Q(variant__product=product))
            .select_related('variant', 'channel', 'locale').order_by('sort'))


@router.get("/products/{id}/relations/", auth=header_key,
            response={200: List[AssociationSchema], 400: Error, 404: Error}, tags=["Product"])
def list_product_relations(request, id: str, type: Optional[str] = None):
    """Product associations (upsell/cross-sell/bundle/accessory), optional type filter.

    Unpaginated (see variants endpoint note on @paginate + error statuses).
    """
    if type is not None and type not in AssociationTypes.values:
        return 400, {'error': f'Unknown type {type!r}. Valid: {sorted(AssociationTypes.values)}.'}
    product = _or_404(
        lambda: get_object_or_404(Product, id=id), f'Product {id} not found.')
    if isinstance(product, Status):
        return product
    relations = (ProductAssociation.objects.filter(from_product=product)
                 .select_related('to_product').order_by('type'))
    if type:
        relations = relations.filter(type=type)
    return relations


# Completeness ------------------------------------------------------------------

def _value_present(value) -> bool:
    """A value counts toward completeness only when it carries real data.

    Empty MULTISELECT (no options) counts as UNSET — see 2.1 audit BUG 2.
    """
    resolved = resolve_attribute_value(value)
    return resolved not in (None, '', [])


@router.get("/products/{id}/completeness/", auth=header_key,
            response={200: CompletenessSchema, 404: Error}, tags=["Completeness"])
def product_completeness(request, id: str, channel: str, locale: str):
    """Completeness % of a product for one channel+locale against its family rule.

    Side effect: refreshes Product.completeness_cache[channel] via queryset
    update (no history row, no updated_at bump). First and only writer.
    """
    product = _or_404(
        lambda: get_object_or_404(Product.objects.select_related('family'), id=id),
        f'Product {id} not found.')
    if isinstance(product, Status):
        return product
    channel_obj = _or_404(
        lambda: get_object_or_404(Channel, code=channel),
        f'Channel {channel} not found.')
    if isinstance(channel_obj, Status):
        return channel_obj
    locale_obj = _or_404(
        lambda: get_object_or_404(Locale, code=locale),
        f'Locale {locale} not found.')
    if isinstance(locale_obj, Status):
        return locale_obj
    if product.family_id is None:
        return 404, {'error': 'Product has no family; completeness is undefined.'}
    rule = (CompletenessRule.objects
            .filter(channel=channel_obj, locale=locale_obj, family=product.family)
            .prefetch_related('required_attributes').first())
    if rule is None:
        return 404, {'error': 'No completeness rule for this channel/locale/family.'}

    required = list(rule.required_attributes.all())
    values = list(ProductValue.objects.filter(product=product)
                  .select_related('attribute', 'option', 'channel', 'locale')
                  .prefetch_related('options'))
    missing = []
    for attr in required:
        satisfied = any(
            (v.channel_id is None or v.channel_id == channel)
            and (v.locale_id is None or v.locale_id == locale)
            and _value_present(v)
            for v in values if v.attribute_id == attr.pk
        )
        if not satisfied:
            missing.append(attr.code)

    total = len(required)
    percent = round((total - len(missing)) / total * 100, 2) if total else 100.0
    Product.objects.filter(pk=product.pk).update(
        completeness_cache={**(product.completeness_cache or {}), channel: percent})

    return {
        'product': product.sku,
        'channel': channel,
        'locale': locale,
        'family': product.family_id,
        'percent': percent,
        'complete': percent == 100.0,
        'missing': missing,
        'total_required': total,
    }
