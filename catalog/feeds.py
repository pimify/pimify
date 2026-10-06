"""Phase 4: generic outbound feed builder (PIM -> commerce, pull model).

One resolved payload per product for an explicit (channel, locale) scope:
product-level attributes via the shared resolver, variant-axis attributes
resolved per variant the same way, in-scope media (same rule the values
endpoint uses: a row applies iff its channel/locale is unset or exact),
plus the completeness block when a rule exists for the scope+family.
Deterministic ordering throughout (sku / attribute code / media sort+pk)
so consecutive runs diff cleanly.

Scope notes: locale/channel scope applies to *attributes and media*.
Product name/description/price are plain (global) columns, not scoped
values, and are emitted as-is. Completeness counts a required attribute
satisfied when ANY in-scope set value exists at product level or on any
variant (axis placement is enforced in clean(), so levels can't mix).
"""
import csv
import io
import json

from django.db.models import Prefetch, Q
from django.utils import timezone

from .models import (
    CompletenessRule, Product, ProductCategory, ProductMedia, ProductValue,
    ProductVariant, VariantValue,
)
from .resolution import resolve_scoped_value
from .schemas import resolve_attribute_value

_MEDIA_QS = (ProductMedia.objects.select_related('variant', 'channel', 'locale')
             .order_by('sort', 'pk'))


def _resolved_attrs(rows, channel_id, locale_id):
    """{attribute_code: value} for winning rows only, codes sorted."""
    by_attr = {}
    for row in rows:
        by_attr.setdefault(row.attribute.code, (row.attribute, []))[1].append(row)
    out = {}
    for code in sorted(by_attr):
        attr, rs = by_attr[code]
        won = resolve_scoped_value(rs, attr, channel_id, locale_id)
        if won is not None:
            out[code] = resolve_attribute_value(won)
    return out


def _attribute_types(all_values):
    """{attribute_code: schema type} for the transformer (metafield typing).
    Zero queries: attributes are select_related on every value row."""
    return {row.attribute.code: row.attribute.type for row in all_values}


def _in_scope(media_rows, channel_id, locale_id):
    """Eligibility rule shared by media and the values endpoint: each axis
    unset or exact. Feed builders always pass both params, so the two agree."""
    return [m for m in media_rows
            if (m.channel_id is None or m.channel_id == channel_id)
            and (m.locale_id is None or m.locale_id == locale_id)]


def _all_values(product):
    """Product-level rows plus every variant's rows (axis placement is
    enforced in clean(), so a non-axis attr can never hide on a variant)."""
    rows = list(product.values.all())
    for variant in product.variants.all():
        rows.extend(variant.values.all())
    return rows


def _completeness(product, all_values, rules, channel_id, locale_id):
    """Completeness block for the scope, or None when undefined (no family
    or no rule). A feed spans families, so missing rules skip the block
    instead of failing the run."""
    if product.family_id is None:
        return None
    rule = rules.get(product.family_id)
    if rule is None:
        return None
    required = list(rule.required_attributes.all())
    missing = [a.code for a in required
               if resolve_scoped_value(all_values, a, channel_id, locale_id) is None]
    percent = round((len(required) - len(missing)) / len(required) * 100, 2) if required else 100.0
    return {'percent': percent, 'complete': percent == 100.0, 'missing': missing}


def _feed_rules(channel_id, locale_id):
    """All rules for the scope in ONE query, keyed by family (feed-scale:
    no per-product rule lookup)."""
    return {r.family_id: r
            for r in CompletenessRule.objects
            .filter(channel_id=channel_id, locale_id=locale_id)
            .prefetch_related('required_attributes')}


def feed_products_qs():
    """Active products with everything the builder needs prefetched (values,
    variants+values, product/variant media). Feed-scale: no per-row queries."""
    return (Product.objects.filter(is_active=True)
            .select_related('family', 'brand')
            .prefetch_related(
                Prefetch('category_links',
                         queryset=ProductCategory.objects
                         .select_related('category').order_by('-is_primary', 'category__slug')),
                Prefetch('values',
                         queryset=ProductValue.objects
                         .select_related('attribute', 'option', 'channel', 'locale')
                         .prefetch_related('options')),
                Prefetch('variants',
                         queryset=ProductVariant.objects
                         .prefetch_related(Prefetch(
                             'values',
                             queryset=VariantValue.objects
                             .select_related('attribute', 'option', 'channel', 'locale')
                             .prefetch_related('options')))
                         .prefetch_related(Prefetch('media', queryset=_MEDIA_QS))
                         .order_by('sort')),
                Prefetch('media', queryset=_MEDIA_QS),
            ).order_by('sku'))


def build_feed_payload(feed):
    """Full feed document (JSON-serializable dict) for feed.channel/locale.

    Only `is_active AND is_published` products ship. Returns
    (payload, skipped, shipped_ids) where skipped is {reason: [skus]} with
    reasons unpublished / incomplete / no_rule — exclusions stay auditable.
    Stamping happens in run_feed AFTER the file lands on disk, so a failed
    write never marks products shipped.
    """
    channel_id, locale_id = feed.channel_id, feed.locale_id
    rules = _feed_rules(channel_id, locale_id)
    items, skipped = [], {'unpublished': [], 'incomplete': [], 'no_rule': []}
    shipped_ids = []
    for product in feed_products_qs():
        if not product.is_published:
            skipped['unpublished'].append(product.sku)
            continue
        all_values = _all_values(product)
        completeness = _completeness(product, all_values, rules, channel_id, locale_id)
        if feed.only_complete:
            if completeness is None:
                skipped['no_rule'].append(product.sku)
                continue
            if not completeness['complete']:
                skipped['incomplete'].append(product.sku)
                continue
        variants = [{
            'sku': v.sku,
            'is_default': v.is_default,
            'price': (float(v.list_price.amount) if v.list_price is not None
                      else float(product.list_price.amount)),
            'price_is_override': v.list_price is not None,
            'attributes': _resolved_attrs(list(v.values.all()), channel_id, locale_id),
        } for v in product.variants.all()]
        media_rows = list(product.media.all())
        for v in product.variants.all():
            media_rows.extend(v.media.all())
        media_rows.sort(key=lambda m: (m.sort, m.pk))
        media = [{
            'role': m.role,
            'url': m.file.url if m.file else None,
            'variant_sku': m.variant.sku if m.variant_id else None,
            'alt_text': m.alt_text,
        } for m in _in_scope(media_rows, channel_id, locale_id)]
        items.append({
            'sku': product.sku,
            'name': product.name,
            'description': product.description,
            'price': float(product.list_price.amount),
            'currency': str(product.list_price.currency),
            'brand': product.brand.slug if product.brand_id else None,
            'brand_name': product.brand.name if product.brand_id else None,
            'categories': [link.category.slug for link in product.category_links.all()],
            'attributes': _resolved_attrs(list(product.values.all()), channel_id, locale_id),
            'attribute_types': _attribute_types(all_values),
            'variants': variants,
            'media': media,
            'completeness': completeness,
        })
        shipped_ids.append(product.pk)
    if shipped_ids:
        Product.objects.filter(pk__in=shipped_ids).update(published_at=timezone.now())
    payload = {
        'feed': feed.name,
        'channel': channel_id,
        'locale': locale_id,
        'generated_at': timezone.now().isoformat(),
        'products': items,
    }
    return payload, skipped, shipped_ids


def stamp_shipped(shipped_ids, when=None):
    """Mark products shipped: published_at frozen on first ship (the Studio
    diff baseline), last_shipped_at bumped every time. Queryset updates —
    no history rows, mirroring completeness_cache."""
    when = when or timezone.now()
    shipped = Product.objects.filter(pk__in=shipped_ids)
    shipped.filter(published_at__isnull=True).update(published_at=when)
    shipped.update(last_shipped_at=when)


def run_feed(feed):
    """Build one feed end-to-end: render file under FEEDS_ROOT, log the run.

    Shared by the `build_feed` command and the scheduler (single path).
    A feed with `profile` set renders that platform's artifact instead of
    the generic payload (platform artifacts are JSON; Feed.clean rejects
    profile + CSV). Raises on failure AFTER recording a failed run; returns
    the success run.
    """
    from pathlib import Path

    from django.conf import settings

    from .models import FeedRun, FeedRunStatus
    from .platforms import get_transformer

    root = Path(settings.FEEDS_ROOT)
    root.mkdir(parents=True, exist_ok=True)
    stamp = timezone.now().strftime('%Y%m%d-%H%M%S')
    if feed.profile_id:
        filename = f"{feed.id}_{stamp}.{feed.profile.platform}.json"
    else:
        filename = f"{feed.id}_{stamp}.{feed.format}"
    try:
        payload, skipped, shipped_ids = build_feed_payload(feed)
        report = {}
        if feed.profile_id:
            artifact = get_transformer(feed.profile.platform)(payload, feed.profile)
            for reason, skus in artifact['report']['skipped'].items():
                skipped.setdefault(reason, []).extend(skus)
            report = artifact['report']
            body = render_json(artifact)
            count = artifact['report']['included']
        else:
            body = render_json(payload) if feed.format == 'json' else render_csv(payload)
            count = len(payload['products'])
        (root / filename).write_text(body, encoding='utf-8')
    except Exception as exc:  # noqa: BLE001 — must log, then fail loudly
        FeedRun.objects.create(
            feed=feed, status=FeedRunStatus.FAILED,
            error=f'{type(exc).__name__}: {exc}')
        raise
    stamp_shipped(shipped_ids)  # after the write: failed builds stamp nothing
    return FeedRun.objects.create(
        feed=feed, status=FeedRunStatus.SUCCESS,
        items=count, skipped=skipped, report=report, file=filename)


def render_json(payload) -> str:
    return json.dumps(payload, indent=2, default=str)


def _csv_cell(value):
    """CSV cells are raw strings; only non-strings get JSON encoding (the
    csv writer already quotes correctly — json.dumps('red') would bake in
    literal quotes)."""
    if value is None:
        return ''
    if isinstance(value, str):
        return value
    return json.dumps(value, default=str)


def render_csv(payload) -> str:
    """One row per variant (variant-less products get a single empty-variant
    row). Attribute columns are the union of codes across the feed."""
    products = payload['products']
    attr_codes, var_codes = set(), set()
    for p in products:
        attr_codes.update(p['attributes'])
        for v in p['variants']:
            var_codes.update(v['attributes'])
    attr_codes, var_codes = sorted(attr_codes), sorted(var_codes)
    head = (['product_sku', 'product_name', 'description', 'price', 'currency',
             'brand', 'categories', 'completeness_percent', 'complete']
            + [f'attr_{c}' for c in attr_codes]
            + ['variant_sku', 'variant_default', 'variant_price']
            + [f'var_{c}' for c in var_codes]
            + ['media_urls'])
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(head)
    for p in products:
        comp = p['completeness'] or {}
        base = [p['sku'], p['name'], p['description'] or '', p['price'],
                p['currency'], p['brand'] or '',
                '|'.join(p['categories']),
                comp.get('percent', ''),
                comp.get('complete', '')]
        pattrs = [_csv_cell(p['attributes'].get(c)) for c in attr_codes]
        urls = '|'.join(u for u in (m['url'] for m in p['media']) if u)
        rows = p['variants'] or [{'sku': '', 'is_default': '', 'price': '',
                                   'attributes': {}}]
        for v in rows:
            w.writerow(base + pattrs + [v['sku'], v['is_default'], v.get('price', '')]
                       + [_csv_cell(v['attributes'].get(c))
                          for c in var_codes] + [urls])
    return buf.getvalue()
