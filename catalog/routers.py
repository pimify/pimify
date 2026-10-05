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
    Feed,
    FeedRun,
    FeedRunStatus,
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
    AttributeValueSchema,
    CategoryTreeSchema,
    ChannelSchema,
    CompletenessSchema,
    FamilyDetailSchema,
    FamilyListSchema,
    FeedRunSchema,
    FeedSchema,
    LocaleSchema,
    MediaSchema,
    ProductDetailSchema,
    ProductHistorySchema,
    ProductListSchema,
    VariantSchema,
)
from .resolution import resolve_scoped_value

router = Router()


def or_404(make, error):
    """get_object_or_404 that honors the declared 404: Error envelope.

    Bare get_object_or_404 raises into Ninja's default handler, which renders
    {"detail": ...} — contradicting every endpoint's documented Error shape.
    Returns Status (not a plain tuple) because @paginate only understands
    Status for non-200 returns — plain tuples get validated as 200 payloads.

    Public for reuse by api/public_routers (cutover endpoints share the contract).
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
    return or_404(
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
    return or_404(
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
    min_price: Optional[float] = None
    max_price: Optional[float] = None


@router.get("/products/", auth=header_key,
            response={200: List[ProductListSchema]}, tags=["Product"])
@paginate(PageNumberPagination, page_size=20)
def list_catalog_products(request, filters: CatalogProductFilter = Query(...)):
    """Paginated catalog products with optional search/active/family/price filters."""
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
    # MoneyField amount column is `list_price`: plain numeric comparison is
    # correct (same verified djmoney behavior as the legacy price filter).
    if filters.min_price is not None:
        products = products.filter(list_price__gte=filters.min_price)
    if filters.max_price is not None:
        products = products.filter(list_price__lte=filters.max_price)
    return products


@router.get("/products/{id}/", auth=header_key,
            response={200: ProductDetailSchema, 404: Error}, tags=["Product"])
def retrieve_catalog_product(request, id: str):
    """Catalog product detail: categories, values, variants (+values), media."""
    return or_404(
        lambda: get_object_or_404(_product_detail_qs(), id=id),
        f'Product {id} not found.')


@router.get("/products/{id}/history/", auth=header_key,
            response={200: List[ProductHistorySchema], 404: Error}, tags=["Product"])
@paginate(PageNumberPagination, page_size=20)
def product_history(request, id: str):
    """Audit trail of a product (newest first). Field-level diff against
    published_at is a Studio feature; this endpoint exposes the raw log."""
    product = or_404(
        lambda: get_object_or_404(Product, id=id), f'Product {id} not found.')
    if isinstance(product, Status):
        return product
    return product.history.all()


@router.get("/products/{id}/variants/", auth=header_key,
            response={200: List[VariantSchema], 404: Error}, tags=["Variant"])
def list_product_variants(request, id: str):
    """Variants of one product, each with its axis values.

    Deliberately unpaginated: @paginate cannot return non-200 statuses
    (it paginates the error payload as if it were the 200 list). Variant
    collections per product are small; revisit if that changes.
    """
    product = or_404(
        lambda: get_object_or_404(Product, id=id), f'Product {id} not found.')
    if isinstance(product, Status):
        return product
    return (ProductVariant.objects.filter(product=product)
            .prefetch_related(_variant_values()).order_by('sort'))


@router.get("/variants/{sku}/", auth=header_key,
            response={200: VariantSchema, 404: Error}, tags=["Variant"])
def retrieve_variant(request, sku: str):
    """Single variant by SKU with its axis values."""
    return or_404(
        lambda: get_object_or_404(
            ProductVariant.objects.prefetch_related(_variant_values()), sku=sku),
        f'Variant {sku} not found.')


@router.get("/products/{id}/media/", auth=header_key,
            response={200: List[MediaSchema], 404: Error}, tags=["Media"])
def list_product_media(
    request, id: str, channel: Optional[str] = None, locale: Optional[str] = None,
):
    """Product media feed: product-owned rows plus variant rows (variant sku set).

    Optional channel/locale narrow to in-scope rows (global rows always
    included). NOTE: this is a lenient listing, not resolution — an omitted
    axis means "don't filter on it" (unlike /values/, where an omitted axis
    means "global rows only"). Feed builders always pass both params, which
    makes the two agree. Supersedes legacy /public/products/{id}/images/.
    Unpaginated (see variants endpoint note on @paginate + error statuses).
    """
    product = or_404(
        lambda: get_object_or_404(Product, id=id), f'Product {id} not found.')
    if isinstance(product, Status):
        return product
    media = (ProductMedia.objects
             .filter(Q(product=product) | Q(variant__product=product))
             .select_related('variant', 'channel', 'locale').order_by('sort'))
    if channel is not None:
        media = media.filter(Q(channel__isnull=True) | Q(channel_id=channel))
    if locale is not None:
        media = media.filter(Q(locale__isnull=True) | Q(locale_id=locale))
    return media


@router.get("/products/{id}/values/", auth=header_key,
            response={200: List[AttributeValueSchema], 404: Error}, tags=["Product"])
def list_resolved_values(
    request, id: str, channel: Optional[str] = None, locale: Optional[str] = None,
):
    """One winning value row per attribute for a (channel, locale) scope.

    Same fallback chain as the completeness engine (exact -> channel-only ->
    locale-only -> global); unset rows never win. NOTE: this is strict
    resolution — an omitted axis means "global rows only" (unlike /media/,
    where an omitted axis means "don't filter"). Feed builders always pass
    both params, which makes the two agree. Unpaginated: one row per
    attribute by construction.
    """
    product = or_404(
        lambda: get_object_or_404(Product, id=id), f'Product {id} not found.')
    if isinstance(product, Status):
        return product
    values = list(ProductValue.objects.filter(product=product)
                  .select_related('attribute', 'option', 'channel', 'locale')
                  .prefetch_related('options'))
    by_attr = {}
    for v in values:
        by_attr.setdefault(v.attribute.code, (v.attribute, []))[1].append(v)
    winners = []
    for code in sorted(by_attr):
        attr, rows = by_attr[code]
        won = resolve_scoped_value(rows, attr, channel, locale)
        if won is not None:
            winners.append(won)
    return winners


@router.get("/products/{id}/relations/", auth=header_key,
            response={200: List[AssociationSchema], 400: Error, 404: Error}, tags=["Product"])
def list_product_relations(request, id: str, type: Optional[str] = None):
    """Product associations (upsell/cross-sell/bundle/accessory), optional type filter.

    Unpaginated (see variants endpoint note on @paginate + error statuses).
    """
    if type is not None and type not in AssociationTypes.values:
        return 400, {'error': f'Unknown type {type!r}. Valid: {sorted(AssociationTypes.values)}.'}
    product = or_404(
        lambda: get_object_or_404(Product, id=id), f'Product {id} not found.')
    if isinstance(product, Status):
        return product
    relations = (ProductAssociation.objects.filter(from_product=product)
                 .select_related('to_product').order_by('type'))
    if type:
        relations = relations.filter(type=type)
    return relations


# Completeness ------------------------------------------------------------------


@router.get("/products/{id}/completeness/", auth=header_key,
            response={200: CompletenessSchema, 404: Error}, tags=["Completeness"])
def product_completeness(request, id: str, channel: str, locale: str):
    """Completeness % of a product for one channel+locale against its family rule.

    Side effect: refreshes Product.completeness_cache[channel] via queryset
    update (no history row, no updated_at bump). First and only writer.
    """
    product = or_404(
        lambda: get_object_or_404(Product.objects.select_related('family'), id=id),
        f'Product {id} not found.')
    if isinstance(product, Status):
        return product
    channel_obj = or_404(
        lambda: get_object_or_404(Channel, code=channel),
        f'Channel {channel} not found.')
    if isinstance(channel_obj, Status):
        return channel_obj
    locale_obj = or_404(
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
    # Variant-axis attributes live on variants: a required attribute counts
    # satisfied when ANY in-scope set value exists at product level or on any
    # variant (axis placement is enforced in clean(), so levels can't mix).
    values += list(VariantValue.objects.filter(variant__product=product)
                   .select_related('attribute', 'option', 'channel', 'locale')
                   .prefetch_related('options'))
    missing = [
        attr.code for attr in required
        if resolve_scoped_value(values, attr, channel, locale) is None
    ]

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


# Feeds -----------------------------------------------------------------------

@router.get("/feeds/", auth=header_key,
            response={200: List[FeedSchema], 404: Error}, tags=["Feeds"])
@paginate(PageNumberPagination, page_size=20)
def list_feeds(request, channel: Optional[str] = None,
               locale: Optional[str] = None, is_active: Optional[bool] = None):
    """Discover configured feeds (name/scope/format) before polling runs."""
    feeds = Feed.objects.all()
    if channel is not None:
        feeds = feeds.filter(channel_id=channel)
    if locale is not None:
        feeds = feeds.filter(locale_id=locale)
    if is_active is not None:
        feeds = feeds.filter(is_active=is_active)
    return feeds.order_by('name')


@router.get("/feeds/runs/", auth=header_key,
            response={200: List[FeedRunSchema], 404: Error}, tags=["Feeds"])
@paginate(PageNumberPagination, page_size=20)
def list_feed_runs(request, feed: Optional[int] = None,
                   status: Optional[str] = None):
    """List feed build runs (newest first). Pull model: consumers poll this,
    then download the file of the latest successful run."""
    runs = FeedRun.objects.select_related('feed')
    if feed is not None:
        runs = runs.filter(feed_id=feed)
    if status is not None:
        runs = runs.filter(status=status)
    return runs


@router.get("/feeds/runs/{id}/download/", auth=header_key,
            response={200: None, 404: Error}, tags=["Feeds"])
def download_feed_run(request, id: int):
    """Download a successful run's file. Streams from FEEDS_ROOT; the path
    is basename-guarded so a tampered `file` value can't escape the dir."""
    from pathlib import Path

    from django.conf import settings
    from django.http import FileResponse

    run = or_404(
        lambda: get_object_or_404(FeedRun, id=id), f'FeedRun {id} not found.')
    if isinstance(run, Status):
        return run
    if run.status != FeedRunStatus.SUCCESS or not run.file:
        return 404, {'error': f'FeedRun {id} has no file to download.'}
    path = Path(settings.FEEDS_ROOT) / Path(run.file).name
    if not path.is_file():
        return 404, {'error': f'Feed file for run {id} is missing from disk.'}
    return FileResponse(open(path, 'rb'), as_attachment=True,
                        filename=path.name)
