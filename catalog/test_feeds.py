"""Phase 4: feed payload resolution, build command, runs API."""
import json
import tempfile
from decimal import Decimal
from pathlib import Path

from django.test import TestCase, override_settings
from ninja.testing import TestClient

from api.models import APIKey
from catalog.feeds import build_feed_payload, render_csv, render_json
from catalog.models import (
    Attribute,
    AttributeSet,
    AttributeTypes,
    Category,
    Channel,
    CompletenessRule,
    Feed,
    FeedRun,
    Locale,
    MediaRoles,
    Product,
    ProductCategory,
    ProductMedia,
    ProductValue,
    ProductVariant,
    VariantValue,
)
from catalog.routers import router


def make_scope():
    locale = Locale.objects.create(code='de', name='German')
    channel = Channel.objects.create(code='web', name='Web')
    channel.locales.add(locale)
    return channel, locale


def make_catalog(channel, locale):
    family = AttributeSet.objects.create(code='f', name='F')
    color = Attribute.objects.create(code='color', label='Color')
    size = Attribute.objects.create(
        code='size', label='Size', type=AttributeTypes.TEXT, is_variant_axis=True)
    desc = Attribute.objects.create(
        code='desc', label='Desc', type=AttributeTypes.TEXT,
        is_localizable=True, is_channel_scoped=True)
    family.attributes.add(color, size, desc)
    rule = CompletenessRule.objects.create(
        channel=channel, locale=locale, family=family)
    rule.required_attributes.add(color, size)
    product = Product.objects.create(
        sku='F-001', name='Shirt', description='A fine shirt.',
        list_price=Decimal('29.99'), family=family, is_active=True)
    ProductValue.objects.create(
        product=product, attribute=color, value_text='red')
    ProductValue.objects.create(
        product=product, attribute=desc, value_text='global')
    ProductValue.objects.create(
        product=product, attribute=desc, channel=channel, locale=locale,
        value_text='exact')
    variant = ProductVariant.objects.create(
        product=product, sku='F-001-M', is_default=True)
    VariantValue.objects.create(
        variant=variant, attribute=size, value_text='M')
    cat = Category.objects.create(name='Shirts', slug='shirts')
    ProductCategory.objects.create(product=product, category=cat, is_primary=True)
    ProductMedia.objects.create(product=product, role=MediaRoles.MAIN, file='')
    ProductMedia.objects.create(
        product=product, role=MediaRoles.GALLERY, file='', channel=channel)
    other_ch = Channel.objects.create(code='app', name='App')
    ProductMedia.objects.create(
        product=product, role=MediaRoles.GALLERY, file='', channel=other_ch)
    return product


class FeedPayloadTest(TestCase):
    def setUp(self):
        self.channel, self.locale = make_scope()
        self.product = make_catalog(self.channel, self.locale)
        self.feed = Feed.objects.create(
            name='web-de', channel=self.channel, locale=self.locale)

    def _payload(self):
        payload, skipped = build_feed_payload(self.feed)
        assert skipped == []
        return payload

    def test_product_attributes_resolve_exact(self):
        item = self._payload()['products'][0]
        self.assertEqual(item['attributes']['desc'], 'exact')
        self.assertEqual(item['attributes']['color'], 'red')

    def test_variant_axis_resolved_per_variant(self):
        item = self._payload()['products'][0]
        self.assertEqual(len(item['variants']), 1)
        self.assertEqual(item['variants'][0]['attributes'], {'size': 'M'})

    def test_media_limited_to_scope(self):
        item = self._payload()['products'][0]
        self.assertEqual(
            sorted(m['role'] for m in item['media']), ['gallery', 'main'])

    def test_variant_axis_counts_toward_completeness(self):
        item = self._payload()['products'][0]
        self.assertEqual(item['completeness']['percent'], 100.0)
        self.assertTrue(item['completeness']['complete'])
        self.assertEqual(item['completeness']['missing'], [])

    def test_price_description_present(self):
        item = self._payload()['products'][0]
        self.assertEqual(item['price'], 29.99)
        self.assertEqual(item['currency'], 'USD')
        self.assertEqual(item['description'], 'A fine shirt.')

    def test_only_complete_includes_complete_product(self):
        self.feed.only_complete = True
        self.feed.save()
        payload, skipped = build_feed_payload(self.feed)
        self.assertEqual(len(payload['products']), 1)
        self.assertEqual(skipped, [])

    def test_only_complete_skips_and_audits(self):
        VariantValue.objects.all().delete()  # re-open the size gap
        self.feed.only_complete = True
        self.feed.save()
        payload, skipped = build_feed_payload(self.feed)
        self.assertEqual(payload['products'], [])
        self.assertEqual(skipped, ['F-001'])

    def test_inactive_products_excluded(self):
        self.product.is_active = False
        self.product.save()
        payload, skipped = build_feed_payload(self.feed)
        self.assertEqual(payload['products'], [])
        self.assertEqual(skipped, [])  # inactive != skipped (not a candidate)

    def test_json_renders(self):
        payload = self._payload()
        doc = json.loads(render_json(payload))
        self.assertEqual(doc['channel'], 'web')
        self.assertEqual(doc['products'][0]['sku'], 'F-001')

    def test_csv_one_row_per_variant_no_double_encode(self):
        out = render_csv(self._payload()).strip().splitlines()
        self.assertEqual(len(out), 2)  # header + 1 variant row
        head = out[0].split(',')
        self.assertIn('product_sku', head)
        self.assertIn('price', head)
        self.assertIn('F-001-M', out[1])
        self.assertIn('red', out[1])
        self.assertNotIn('"red"', out[1])  # text cells are raw, not JSON-quoted


class TempFeedsMixin:
    """Hermetic FEEDS_ROOT per test (auto-removed); no /tmp litter."""

    def setUp(self):
        super().setUp()
        self._tmp = tempfile.TemporaryDirectory(prefix='pimify-feeds-')
        self.addCleanup(self._tmp.cleanup)
        self._override = override_settings(FEEDS_ROOT=self._tmp.name)
        self._override.enable()
        self.addCleanup(self._override.disable)

    def feeds_root(self):
        return Path(self._tmp.name)


class BuildFeedCommandTest(TempFeedsMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.channel, self.locale = make_scope()
        make_catalog(self.channel, self.locale)
        self.feed = Feed.objects.create(
            name='web-de', channel=self.channel, locale=self.locale)

    def test_success_logs_run_and_writes_file(self):
        from io import StringIO
        from django.core.management import call_command
        call_command('build_feed', 'web-de', stdout=StringIO())
        run = FeedRun.objects.get()
        self.assertEqual(run.status, 'success')
        self.assertEqual(run.items, 1)
        self.assertEqual(run.skipped, [])
        self.assertTrue((self.feeds_root() / run.file).is_file())

    def test_skipped_recorded_on_run(self):
        from io import StringIO
        from django.core.management import call_command
        VariantValue.objects.all().delete()
        self.feed.only_complete = True
        self.feed.save()
        call_command('build_feed', 'web-de', stdout=StringIO())
        run = FeedRun.objects.get()
        self.assertEqual((run.status, run.items, run.skipped),
                         ('success', 0, ['F-001']))

    def test_unknown_feed_raises_without_run(self):
        from django.core.management import call_command
        from django.core.management.base import CommandError
        with self.assertRaises(CommandError):
            call_command('build_feed', 'nope')
        self.assertEqual(FeedRun.objects.count(), 0)

    def test_inactive_feed_refused_without_run(self):
        from django.core.management import call_command
        from django.core.management.base import CommandError
        self.feed.is_active = False
        self.feed.save()
        with self.assertRaises(CommandError):
            call_command('build_feed', 'web-de')
        self.assertEqual(FeedRun.objects.count(), 0)


class FeedRunsApiTest(TempFeedsMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.client = TestClient(router)
        key = APIKey.objects.create(name='f')
        self.h = {'X-API-Key': key.api_key}
        self.channel, self.locale = make_scope()
        make_catalog(self.channel, self.locale)
        self.feed = Feed.objects.create(
            name='web-de', channel=self.channel, locale=self.locale)
        self.run = FeedRun.objects.create(feed=self.feed, status='success',
                                           items=1, file='x.json')
        FeedRun.objects.create(feed=self.feed, status='failed', error='boom')

    def test_list_feeds(self):
        body = self.client.get('/feeds/?channel=web', headers=self.h).json()
        self.assertEqual(body['count'], 1)
        self.assertEqual(body['items'][0]['name'], 'web-de')

    def test_list_runs_with_filters(self):
        body = self.client.get('/feeds/runs/', headers=self.h).json()
        self.assertEqual(body['count'], 2)
        only_ok = self.client.get('/feeds/runs/?status=success',
                                  headers=self.h).json()
        self.assertEqual([r['status'] for r in only_ok['items']], ['success'])
        self.assertEqual(only_ok['items'][0]['feed_name'], 'web-de')
        self.assertEqual(only_ok['items'][0]['skipped'], [])

    def test_download_missing_file_404(self):
        r = self.client.get(f'/feeds/runs/{self.run.id}/download/',
                            headers=self.h)
        self.assertEqual(r.status_code, 404)
        self.assertEqual(set(r.json()), {'error'})

    def test_download_success(self):
        (self.feeds_root() / 'x.json').write_text('{"a":1}')
        r = self.client.get(f'/feeds/runs/{self.run.id}/download/',
                            headers=self.h)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.content, b'{"a":1}')

    def test_failed_run_has_no_download(self):
        failed = FeedRun.objects.get(status='failed')
        r = self.client.get(f'/feeds/runs/{failed.id}/download/',
                            headers=self.h)
        self.assertEqual(r.status_code, 404)
