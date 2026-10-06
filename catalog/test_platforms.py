"""Phase 4.2: Shopify profile transformer, validation, artifact path."""
import json
from decimal import Decimal
from types import SimpleNamespace

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from djmoney.money import Money
from ninja.testing import TestClient

from api.models import APIKey
from catalog.models import Attribute, Feed, FeedRun, PlatformProfile, ProductVariant
from catalog.platforms import get_transformer, supported_platforms
from catalog.platforms.shopify import (
    derive_options, transform_item, transform_shopify, variant_price_str,
)
from catalog.routers import router
from catalog.test_feeds import TempFeedsMixin, make_catalog, make_scope


def ns(**kw):
    kw.setdefault('defaults', {})
    kw.setdefault('attribute_map', {})
    kw.setdefault('category_map', {})
    return SimpleNamespace(**kw)


def item(**kw):
    base = {
        'sku': 'F-001', 'name': 'Shirt', 'description': 'A fine shirt.',
        'price': 29.99, 'currency': 'USD', 'brand': 'acme', 'brand_name': 'Acme',
        'categories': ['shirts'],
        'attributes': {'color': 'red'},
        'variants': [
            {'sku': 'F-001-M', 'is_default': True, 'price': 29.99,
             'attributes': {'size': 'M', 'color': 'red'}},
            {'sku': 'F-001-L', 'is_default': False, 'price': 31.99,
             'attributes': {'size': 'L', 'color': 'red'}},
        ],
        'media': [{'role': 'main', 'url': 'https://cdn.test/f.jpg',
                   'variant_sku': None, 'alt_text': 'Front'}],
        'completeness': {'percent': 100.0, 'complete': True, 'missing': []},
    }
    base.update(kw)
    return base


class DeriveOptionsTest(TestCase):
    def test_two_axes_derive_first_seen_order(self):
        options, codes = derive_options(item()['variants'])
        self.assertEqual(codes, ['color', 'size'])
        self.assertEqual(
            options,
            [{'name': 'Color', 'values': [{'name': 'red'}]},
             {'name': 'Size', 'values': [{'name': 'M'}, {'name': 'L'}]}])

    def test_over_cap_skips(self):
        variants = [{'sku': 'x', 'attributes': {'a': '1', 'b': '2', 'c': '3', 'd': '4'}}]
        options, codes = derive_options(variants)
        self.assertIsNone(options)
        self.assertEqual(codes, ['a', 'b', 'c', 'd'])


class VariantPriceTest(TestCase):
    def test_override_wins(self):
        self.assertEqual(
            variant_price_str({'price': 24.99}, 29.99), '24.99')

    def test_fallback_to_product(self):
        self.assertEqual(
            variant_price_str({'price': None}, 29.99), '29.99')

    def test_missing_price_is_none(self):
        self.assertIsNone(variant_price_str({'price': None}, None))


class TransformItemTest(TestCase):
    def test_full_shape(self):
        profile = ns(defaults={'status': 'ACTIVE', 'tags': ['new']},
                     category_map={'shirts': 'Shirts'})
        entry, skipped_media = transform_item(item(), profile)
        self.assertEqual(skipped_media, 0)
        create = entry['productCreate']['product']
        self.assertEqual(
            (create['title'], create['vendor'], create['productType'],
             create['status'], create['tags']),
            ('Shirt', 'Acme', 'Shirts', 'ACTIVE', ['new']))
        self.assertEqual(len(create['productOptions']), 2)
        bulk = entry['variantsBulkCreate']['variants']
        self.assertEqual(len(bulk), 2)
        self.assertEqual(
            bulk[0],
            {'price': '29.99',
             'optionValues': [{'optionName': 'Color', 'name': 'red'},
                              {'optionName': 'Size', 'name': 'M'}],
             'inventoryItem': {'sku': 'F-001-M', 'tracked': False}})
        media = entry['productCreate']['media']
        self.assertEqual(
            media, [{'originalSource': 'https://cdn.test/f.jpg', 'alt': 'Front'}])

    def test_status_defaults_to_draft(self):
        entry, _ = transform_item(item(), ns())
        self.assertEqual(entry['productCreate']['product']['status'], 'DRAFT')

    def test_no_title_skipped(self):
        entry, reason = transform_item(item(name=''), ns())
        self.assertEqual((entry, reason), (None, 'no_title'))

    def test_no_variants_synthesized(self):
        entry, _ = transform_item(item(variants=[]), ns())
        bulk = entry['variantsBulkCreate']['variants']
        self.assertEqual(len(bulk), 1)
        self.assertEqual(bulk[0]['price'], '29.99')
        self.assertEqual(entry['productCreate']['product']['productOptions'], [])

    def test_relative_media_warned_not_emitted(self):
        media = [{'role': 'main', 'url': '/media/x.jpg',
                  'variant_sku': None, 'alt_text': None}]
        entry, skipped = transform_item(item(media=media), ns())
        self.assertEqual((entry['productCreate']['media'], skipped), ([], 1))

    def test_metafields_mapped_with_types(self):
        profile = ns(attribute_map={'color': 'color', 'weight': 'weight'})
        entry, _ = transform_item(
            item(attributes={'color': 'red', 'weight': 1.5, 'other': 'x'}), profile)
        self.assertEqual(
            entry['productCreate']['product']['metafields'],
            [{'namespace': 'custom', 'key': 'color', 'value': 'red',
              'type': 'single_line_text_field'},
             {'namespace': 'custom', 'key': 'weight', 'value': 1.5,
              'type': 'number_decimal'}])

    def test_too_many_options_skipped(self):
        variants = [{'sku': 'x', 'price': 1.0,
                     'attributes': {'a': '1', 'b': '2', 'c': '3', 'd': '4'}}]
        entry, reason = transform_item(item(variants=variants), ns())
        self.assertEqual((entry, reason), (None, 'too_many_options'))


class TransformReportTest(TestCase):
    def test_report_shape(self):
        artifact = transform_shopify(
            {'feed': 'f', 'channel': 'web', 'locale': 'de',
             'generated_at': 't', 'products': [item()]}, ns())
        self.assertEqual(artifact['platform'], 'shopify')
        self.assertEqual(artifact['report']['included'], 1)
        self.assertTrue(any('initial variant' in n for n in artifact['report']['notes']))
        json.dumps(artifact)  # serializable


class RegistryTest(TestCase):
    def test_shopify_resolves(self):
        self.assertIn('shopify', supported_platforms())
        self.assertTrue(callable(get_transformer('shopify')))

    def test_unimplemented_raises(self):
        with self.assertRaises(ValueError):
            get_transformer('amazon')


class ProfileValidationTest(TestCase):
    def setUp(self):
        self.channel, self.locale = make_scope()
        Attribute.objects.create(code='color', label='Color')

    def test_unknown_attribute_code_rejected(self):
        profile = PlatformProfile(
            name='p', platform='shopify', channel=self.channel,
            attribute_map={'nope': 'x'})
        with self.assertRaises(ValidationError):
            profile.full_clean()

    def test_unique_platform_channel(self):
        PlatformProfile.objects.create(
            name='p1', platform='shopify', channel=self.channel)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                PlatformProfile.objects.create(
                    name='p2', platform='shopify', channel=self.channel)

    def test_csv_profile_rejected(self):
        feed = Feed(name='f', channel=self.channel, locale=self.locale,
                    format='csv',
                    profile=PlatformProfile.objects.create(
                        name='p', platform='shopify', channel=self.channel))
        with self.assertRaises(ValidationError):
            feed.full_clean()


class ProfileArtifactTest(TempFeedsMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.channel, self.locale = make_scope()
        self.product = make_catalog(self.channel, self.locale)
        variant = ProductVariant.objects.get(sku='F-001-M')
        variant.list_price = Money(Decimal('24.99'), 'USD')
        variant.save()
        self.profile = PlatformProfile.objects.create(
            name='shop', platform='shopify', channel=self.channel,
            category_map={'shirts': 'Shirts'},
            defaults={'status': 'ACTIVE'})
        self.feed = Feed.objects.create(
            name='web-de', channel=self.channel, locale=self.locale,
            profile=self.profile)

    def test_run_writes_shopify_artifact(self):
        from io import StringIO
        from django.core.management import call_command
        call_command('build_feed', 'web-de', stdout=StringIO())
        run = self.feed.runs.get()
        self.assertTrue(run.file.endswith('.shopify.json'))
        doc = json.loads((self.feeds_root() / run.file).read_text())
        self.assertEqual(doc['platform'], 'shopify')
        self.assertEqual(doc['products'][0]['variantsBulkCreate']['variants'][0]['price'],
                         '24.99')
        self.assertEqual(run.items, 1)

    def test_profiles_endpoint(self):
        client = TestClient(router)
        key = APIKey.objects.create(name='p')
        h = {'X-API-Key': key.api_key}
        body = client.get('/profiles/?platform=shopify', headers=h).json()
        self.assertEqual(body['count'], 1)
        self.assertEqual(body['items'][0]['name'], 'shop')
        self.assertEqual(
            client.get('/profiles/?platform=amazon', headers=h).json()['count'], 0)


class ListAxisTest(TestCase):
    def test_multiselect_axis_dedupes_instead_of_crashing(self):
        # Regression: a list-valued axis used to abort the whole build with
        # TypeError (unhashable) — now it resolves and dedupes by content.
        variants = [
            {'sku': 'a', 'price': 1.0, 'attributes': {'tags': ['x', 'y']}},
            {'sku': 'b', 'price': 1.0, 'attributes': {'tags': ['x', 'y']}},
            {'sku': 'c', 'price': 1.0, 'attributes': {'tags': ['y', 'z']}},
        ]
        options, codes = derive_options(variants)
        self.assertEqual(codes, ['tags'])
        self.assertEqual(
            options,
            [{'name': 'Tags',
              'values': [{'name': "['x', 'y']"}, {'name': "['y', 'z']"}]}])


class MoneyFormatTest(TestCase):
    def test_trailing_zeros_kept(self):
        # Regression: the live builder emits floats, so 29.90 arrived as
        # 29.9 and shipped as '29.9' instead of '29.90'.
        from decimal import Decimal
        from catalog.platforms.base import money_str
        self.assertEqual(money_str(29.9), '29.90')
        self.assertEqual(money_str(Decimal('29.90')), '29.90')
        self.assertEqual(money_str(30), '30.00')
        self.assertEqual(money_str(Decimal('29.99')), '29.99')


class SchemaTypedMetafieldsTest(TestCase):
    def test_date_number_types_and_strict_json(self):
        import datetime
        from decimal import Decimal
        profile = ns(attribute_map={'launch': 'launch', 'weight': 'w'},
                     category_map={})
        payload = {'products': [item(
            attributes={'launch': datetime.date(2026, 1, 2),
                        'weight': Decimal('1.5')},
            attribute_types={'launch': 'date', 'weight': 'number'})]}
        artifact = transform_shopify(payload, profile)
        fields = {m['key']: m for m in
                  artifact['products'][0]['productCreate']['product']['metafields']}
        self.assertEqual(fields['launch']['type'], 'date')
        self.assertEqual(fields['launch']['value'], '2026-01-02')
        self.assertEqual(fields['w']['type'], 'number_decimal')
        self.assertEqual(fields['w']['value'], 1.5)
        json.dumps(artifact)  # strict: no default=str masking

    def test_handle_emitted(self):
        entry, _ = transform_item(item(), ns())
        self.assertEqual(entry['productCreate']['product']['handle'], 'f-001')


class PlatformAuditTest(TempFeedsMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.channel, self.locale = make_scope()
        make_catalog(self.channel, self.locale)
        self.profile = PlatformProfile.objects.create(
            name='shop', platform='shopify', channel=self.channel)
        self.feed = Feed.objects.create(
            name='web-de', channel=self.channel, locale=self.locale,
            profile=self.profile)

    def test_platform_skips_land_in_run(self):
        from io import StringIO
        from django.core.management import call_command
        from catalog.models import Product
        # Force a platform skip: strip the product name at DB level so the
        # generic gate passes but the Shopify transform drops it.
        Product.objects.filter(sku='F-001').update(name='')
        call_command('build_feed', 'web-de', stdout=StringIO())
        run = FeedRun.objects.get()
        self.assertEqual((run.status, run.items), ('success', 0))
        self.assertEqual(run.skipped.get('no_title'), ['F-001'])
        self.assertIn('notes', run.report)
        self.assertEqual(run.report['included'], 0)
