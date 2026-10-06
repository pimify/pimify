"""Phase 4.2: Shopify transform (Admin GraphQL 2026-10, file-artifact v1).

Emits the two-call shape Shopify requires, because `productCreate` builds a
product with exactly ONE initial variant — per-variant data goes through
`productVariantsBulkCreate`:

1. `productCreate(product: ProductCreateInput, media: [CreateMediaInput!])`
   — title, descriptionHtml, vendor, productType, handle, status, tags,
   productOptions (max 3), metafields from `attribute_map`.
2. `productVariantsBulkCreate(productId, variants: [ProductVariantsBulkInput!])`
   — price (Money decimal string), optionValues[{optionName, name}],
   inventoryItem{sku, tracked: false}. NOTE: the bulk input has no
   top-level `sku`; the SKU lives under `inventoryItem`.

Deliberate v1 boundaries (see report.notes in every artifact):
- No `inventoryQuantities`: stock is never PIM-owned (locked decision).
- `tracked: false` on every inventory item for the same reason.
- `status` defaults to DRAFT: nothing goes live without a push decision.
- Media: only absolute http(s) URLs; the rest are counted, not emitted.
- The   auto-created initial variant from call 1 must be reused or deleted
  at push time (push-phase task, recorded in the artifact).
- Shopify `category` taxonomy IDs are not mapped (needs their taxonomy
  fetch); we emit merchant-defined `productType` only.
"""
import json

from django.utils.text import slugify

from .base import MAX_OPTIONS, humanize, is_absolute_url, money_str
from ..models import AttributeTypes

METAFIELD_TYPES = {
    AttributeTypes.TEXT: 'single_line_text_field',
    AttributeTypes.TEXTAREA: 'multi_line_text_field',
    AttributeTypes.URL: 'url',
    AttributeTypes.NUMBER: 'number_decimal',
    AttributeTypes.BOOLEAN: 'boolean',
    AttributeTypes.DATE: 'date',
    AttributeTypes.SELECT: 'single_line_text_field',
    AttributeTypes.MULTISELECT: 'list.single_line_text_field',
    AttributeTypes.JSON: 'json',
}
# Fallback when the payload carries no attribute_types map (hand-built
# inputs): infer from the Python value instead of the schema type.
_PYTHON_METAFIELD_TYPES = {
    str: 'single_line_text_field',
    int: 'number_integer',
    float: 'number_decimal',
    bool: 'boolean',
    list: 'list.single_line_text_field',
    dict: 'json',
}


def _metafield_type(code, value, attr_types):
    """Schema type wins (DATE->date, NUMBER->number_decimal); without the
    map, fall back to Python-type inference."""
    schema_type = (attr_types or {}).get(code)
    if schema_type in METAFIELD_TYPES:
        return METAFIELD_TYPES[schema_type]
    if isinstance(value, bool):
        return 'boolean'
    return _PYTHON_METAFIELD_TYPES.get(type(value), 'single_line_text_field')


def _metafield_value(value):
    """JSON-native form: dates isoformat, Decimals float; the artifact must
    json.dumps cleanly WITHOUT default=str (which would mask mistyped values)."""
    import datetime
    from decimal import Decimal
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def derive_options(variants):
    """Variant-axis codes -> ordered option list.

    Option values are distinct resolved values in first-seen variant order
    (variants arrive sku-ordered, so this is deterministic). Returns
    (options, axis_codes); options is None when the axis count exceeds
    Shopify's cap — the caller skips the product instead of guessing.
    """
    axis_codes = sorted({code for v in variants for code in v['attributes']})
    if len(axis_codes) > MAX_OPTIONS:
        return None, axis_codes
    options = []
    for code in axis_codes:
        seen, values = set(), []
        for variant in variants:
            value = variant['attributes'].get(code)
            if value is None:
                continue
            # Key on the string form: list-valued (MULTISELECT) axes are
            # unhashable, and a single unhashable value used to abort the
            # entire build with TypeError.
            key = json_key(value)
            if key in seen:
                continue
            seen.add(key)
            values.append({'name': str(value)})
        options.append({'name': humanize(code), 'values': values})
    return options, axis_codes


def json_key(value):
    """Stable hashable key for dedupe: JSON renders lists/dicts deterministically."""
    try:
        return json.dumps(value, sort_keys=True, default=str)
    except (TypeError, ValueError):
        return str(value)


def variant_price_str(variant, product_price):
    """Variant override wins; None means unpriceable (caller skips)."""
    price = variant.get('price')
    if price is None:
        price = product_price
    if price is None:
        return None
    return money_str(price)


def transform_item(item, profile):
    """One generic payload item -> (Shopify calls dict, media_skipped count),
    or (None, skip_reason)."""
    defaults = profile.defaults or {}
    if not item.get('name'):
        return None, 'no_title'
    variants = item.get('variants') or []
    if not variants:
        variants = [{'sku': item['sku'], 'is_default': True, 'attributes': {},
                     'price': item.get('price')}]
    options, axis_codes = derive_options(variants)
    if options is None:
        return None, 'too_many_options'
    option_names = {code: humanize(code) for code in axis_codes}
    bulk_variants = []
    for variant in variants:
        price = variant_price_str(variant, item.get('price'))
        if price is None:
            return None, 'missing_price'
        bulk_variants.append({
            'price': price,
            'optionValues': [
                {'optionName': option_names[code],
                 'name': str(variant['attributes'][code])}
                for code in axis_codes
                if code in variant['attributes']
            ],
            'inventoryItem': {'sku': variant['sku'], 'tracked': False},
        })
    categories = item.get('categories') or []
    product_type = None
    if categories:
        product_type = (profile.category_map or {}).get(categories[0])
    if product_type is None:
        product_type = defaults.get('product_type')
    namespace = defaults.get('metafield_namespace', 'custom')
    metafields = []
    # attribute_types rides along on builder items; hand-built inputs omit
    # it and fall back to Python-type inference (see _metafield_type).
    attr_types = item.get('attribute_types', {})
    for code, key in (profile.attribute_map or {}).items():
        if code in item.get('attributes', {}):
            value = item['attributes'][code]
            metafields.append({
                'namespace': namespace,
                'key': key,
                'value': _metafield_value(value),
                'type': _metafield_type(code, value, attr_types),
            })
    media, media_skipped = [], 0
    for row in item.get('media') or []:
        if is_absolute_url(row.get('url')):
            entry = {'originalSource': row['url']}
            if row.get('alt_text'):
                entry['alt'] = row['alt_text']
            media.append(entry)
        else:
            media_skipped += 1
    entry = {
        'sku': item['sku'],
        'productCreate': {
            'product': {
                'title': item['name'],
                'handle': slugify(item['sku']),
                'descriptionHtml': item.get('description') or '',
                'vendor': item.get('brand_name') or defaults.get('vendor', ''),
                'productType': product_type or '',
                'status': defaults.get('status', 'DRAFT'),
                'tags': list(defaults.get('tags', [])),
                'productOptions': options,
                'metafields': metafields,
            },
            'media': media,
        },
        'variantsBulkCreate': {'variants': bulk_variants},
    }
    return entry, media_skipped


def transform_shopify(payload, profile):
    """Full generic payload -> Shopify artifact dict (JSON-serializable)."""
    products, report = [], {'included': 0, 'skipped': {}, 'warnings': {},
                            'notes': [
        'productCreate builds exactly one initial variant; '
        'variantsBulkCreate carries the full variant list. At push time, '
        'reconcile (reuse or delete) the auto-created variant.',
        'inventoryItem.tracked is false: stock is never PIM-owned.',
        'No inventoryQuantities are emitted, ever.',
    ]}
    for item in payload.get('products', []):
        entry, outcome = transform_item(item, profile)
        if entry is None:
            report['skipped'].setdefault(outcome, []).append(item['sku'])
            continue
        if outcome:  # media_skipped count
            report['warnings'].setdefault('media_not_absolute', []).append(item['sku'])
        products.append(entry)
    report['included'] = len(products)
    return {
        'platform': 'shopify',
        'feed': payload.get('feed'),
        'channel': payload.get('channel'),
        'locale': payload.get('locale'),
        'generated_at': payload.get('generated_at'),
        'products': products,
        'report': report,
    }
