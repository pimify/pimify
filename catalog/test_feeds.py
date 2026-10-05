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
        list_price=Decimal('29.99'), family=family, is_active=True,
        is_published=True)
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
        payload, skipped, _ = build_feed_payload(self.feed)
        assert skipped == {'unpublished': [], 'incomplete': [], 'no_rule': []}
        return payload

    def test_unpublished_products_gated(self):
        self.product.is_published = False
        self.product.save()
        payload, skipped, _ = build_feed_payload(self.feed)
        self.assertEqual(payload['products'], [])
        self.assertEqual(skipped['unpublished'], ['F-001'])

    def test_publish_action_writes_history(self):
        from django.contrib import admin
        from catalog.admin import ProductAdmin
        from catalog.models import Product
        pa = ProductAdmin(Product, admin.site)
        pa.publish_selected(None, Product.objects.filter(pk=self.product.pk))
        self.product.refresh_from_db()
        self.assertTrue(self.product.is_published)
        self.assertTrue(self.product.history.first().is_published)

    def test_published_at_frozen_last_shipped_bumped(self):        # Stamping is run_feed's job (after the write); build only collects.
        from datetime import timedelta
        from django.utils import timezone
        from catalog.feeds import stamp_shipped
        first = timezone.now() - timedelta(days=1)
        self.product.published_at = first
        self.product.save()
        stamp_shipped([self.product.pk])
        self.product.refresh_from_db()
        self.assertEqual(self.product.published_at, first)  # frozen
        self.assertGreater(self.product.last_shipped_at, first)  # bumped

    def test_no_rule_skipped_only_when_gated(self):
        self.product.family = None
        self.product.save()
        payload, skipped, _ = build_feed_payload(self.feed)
        self.assertEqual(len(payload['products']), 1)  # shipped, null block
        self.assertEqual(skipped['no_rule'], [])
        self.feed.only_complete = True
        self.feed.save()
        payload, skipped, _ = build_feed_payload(self.feed)
        self.assertEqual(payload['products'], [])
        self.assertEqual(skipped['no_rule'], ['F-001'])

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
        payload, skipped, _ = build_feed_payload(self.feed)
        self.assertEqual(len(payload['products']), 1)
        self.assertEqual(
            skipped, {'unpublished': [], 'incomplete': [], 'no_rule': []})

    def test_only_complete_skips_and_audits(self):
        VariantValue.objects.all().delete()  # re-open the size gap
        self.feed.only_complete = True
        self.feed.save()
        payload, skipped, _ = build_feed_payload(self.feed)
        self.assertEqual(payload['products'], [])
        self.assertEqual(skipped['incomplete'], ['F-001'])

    def test_inactive_products_excluded_silently(self):
        self.product.is_active = False
        self.product.save()
        payload, skipped, _ = build_feed_payload(self.feed)
        self.assertEqual(payload['products'], [])
        # Inactive products aren't candidates at all (no skip reason).
        self.assertEqual(
            skipped, {'unpublished': [], 'incomplete': [], 'no_rule': []})

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
        self.product = make_catalog(self.channel, self.locale)
        self.feed = Feed.objects.create(
            name='web-de', channel=self.channel, locale=self.locale)

    def test_failed_build_stamps_nothing(self):
        from unittest.mock import patch
        from catalog.feeds import run_feed
        with patch('catalog.feeds.build_feed_payload',
                   side_effect=RuntimeError('disk on fire')):
            with self.assertRaises(RuntimeError):
                run_feed(self.feed)
        run = FeedRun.objects.get()
        self.assertEqual(run.status, 'failed')
        self.product.refresh_from_db()
        self.assertIsNone(self.product.published_at)
        self.assertIsNone(self.product.last_shipped_at)

    def test_successful_build_stamps_shipped(self):
        from io import StringIO
        from django.core.management import call_command
        call_command('build_feed', 'web-de', stdout=StringIO())
        self.product.refresh_from_db()
        self.assertIsNotNone(self.product.published_at)
        self.assertIsNotNone(self.product.last_shipped_at)

    def test_success_logs_run_and_writes_file(self):
        from io import StringIO
        from django.core.management import call_command
        call_command('build_feed', 'web-de', stdout=StringIO())
        run = FeedRun.objects.get()
        self.assertEqual(run.status, 'success')
        self.assertEqual(run.items, 1)
        self.assertEqual(
            run.skipped, {'unpublished': [], 'incomplete': [], 'no_rule': []})
        self.assertTrue((self.feeds_root() / run.file).is_file())

    def test_skipped_recorded_on_run(self):
        from io import StringIO
        from django.core.management import call_command
        VariantValue.objects.all().delete()
        self.feed.only_complete = True
        self.feed.save()
        call_command('build_feed', 'web-de', stdout=StringIO())
        run = FeedRun.objects.get()
        self.assertEqual(run.status, 'success')
        self.assertEqual(run.items, 0)
        self.assertEqual(run.skipped['incomplete'], ['F-001'])

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
        self.product = make_catalog(self.channel, self.locale)
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
        self.assertEqual(only_ok['items'][0]['skipped'], {})

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

    def test_product_history_endpoint(self):
        self.product.name = 'Shirt v2'
        self.product.save()
        body = self.client.get(
            f'/products/{self.product.id}/history/', headers=self.h).json()
        self.assertGreaterEqual(body['count'], 2)
        latest = body['items'][0]
        self.assertEqual(latest['name'], 'Shirt v2')
        self.assertIn('is_published', latest)


class FeedScheduleTest(TempFeedsMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.channel, self.locale = make_scope()

    def _feed(self, **kw):
        kw.setdefault('channel', self.channel)
        kw.setdefault('locale', self.locale)
        return Feed(name='sched', **kw)

    def test_blank_cron_valid(self):
        self._feed().full_clean()  # no raise

    def test_valid_cron_accepted(self):
        self._feed(schedule_cron='0 6 * * *').full_clean()  # no raise

    def test_invalid_cron_rejected(self):
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            self._feed(schedule_cron='not a cron').full_clean()

    def test_scheduler_registers_only_scheduled_feeds(self):
        from api.management.commands.scheduler import (
            build_scheduler, scheduled_feeds,
        )
        cron = Feed.objects.create(name='cron', channel=self.channel,
                                   locale=self.locale, schedule_cron='0 6 * * *')
        Feed.objects.create(name='manual', channel=self.channel,
                            locale=self.locale)
        Feed.objects.create(name='off', channel=self.channel,
                            locale=self.locale, schedule_cron='0 6 * * *',
                            is_active=False)
        self.assertEqual(
            sorted(f.name for f in scheduled_feeds()), ['cron'])
        scheduler = build_scheduler()  # built, never started (non-blocking)
        job_ids = sorted(j.id for j in scheduler.get_jobs())
        self.assertIn('db_backup', job_ids)
        self.assertEqual(
            [j for j in job_ids if j.startswith('feed_')], [f'feed_{cron.pk}'])

    def test_build_scheduled_feed_skips_dead_feed(self):
        from api.management.commands.scheduler import build_scheduled_feed
        build_scheduled_feed(424242)  # gone feed id: prints, no raise/run
        self.assertEqual(FeedRun.objects.count(), 0)

    def test_build_scheduled_feed_runs_live_feed(self):
        from api.management.commands.scheduler import build_scheduled_feed
        feed = Feed.objects.create(name='cron', channel=self.channel,
                                   locale=self.locale, schedule_cron='0 6 * * *')
        build_scheduled_feed(feed.pk)  # no catalog rows: empty but successful
        run = FeedRun.objects.get()
        self.assertEqual((run.status, run.items), ('success', 0))
        self.assertTrue((self.feeds_root() / run.file).is_file())

    def test_scheduler_skips_invalid_cron(self):
        from api.management.commands.scheduler import build_scheduler
        bad = Feed.objects.create(name='bad', channel=self.channel,
                                  locale=self.locale, schedule_cron='garbage')
        scheduler = build_scheduler()  # must not raise (backups must survive)
        job_ids = [j.id for j in scheduler.get_jobs()]
        self.assertIn('db_backup', job_ids)
        self.assertNotIn(f'feed_{bad.pk}', job_ids)

    def test_scheduler_purges_stale_feed_jobs(self):
        from api.management.commands.scheduler import build_scheduler
        feed = Feed.objects.create(name='cron', channel=self.channel,
                                   locale=self.locale, schedule_cron='0 6 * * *')
        scheduler = build_scheduler()
        self.assertIn(f'feed_{feed.pk}', [j.id for j in scheduler.get_jobs()])
        feed.schedule_cron = ''  # back to manual: job must go away
        feed.save()
        scheduler = build_scheduler()
        self.assertNotIn(f'feed_{feed.pk}', [j.id for j in scheduler.get_jobs()])

    def test_legacy_list_skipped_converted(self):
        import importlib
        from django.apps import apps
        migration = importlib.import_module(
            'catalog.migrations.0008_feed_schedule_cron_'
            'historicalproduct_is_published_and_more')
        run = FeedRun.objects.create(feed=self.cron_feed(), status='success',
                                     items=0, file='')
        FeedRun.objects.filter(pk=run.pk).update(skipped=['F-001'])
        migration._wrap_legacy_skipped(apps, None)
        run.refresh_from_db()
        self.assertEqual(run.skipped, {'incomplete': ['F-001']})
        migration._unwrap_legacy_skipped(apps, None)
        run.refresh_from_db()
        self.assertEqual(run.skipped, ['F-001'])

    def cron_feed(self):
        return Feed.objects.create(name='cronx', channel=self.channel,
                                   locale=self.locale)
