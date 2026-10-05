"""Phase 3: scoped-resolution unit tests (fallback chain + tiebreak).

Uses plain ORM fixtures (objects.create skips clean(), which is what we want
here — resolution must cope with whatever rows exist, valid or legacy).
"""
from django.test import TestCase

from catalog.models import (
    Attribute,
    AttributeOption,
    AttributeTypes,
    Channel,
    Locale,
    Product,
    ProductValue,
)
from catalog.resolution import resolve_scoped_value


def make_product(sku='R-001'):
    from decimal import Decimal
    return Product.objects.create(sku=sku, name=sku, list_price=Decimal('1'))


class ResolveScoredValueTest(TestCase):
    def setUp(self):
        self.product = make_product()
        self.locale = Locale.objects.create(code='de', name='German')
        self.channel = Channel.objects.create(code='web', name='Web')
        self.channel.locales.add(self.locale)
        self.attr = Attribute.objects.create(
            code='t', label='T', type=AttributeTypes.TEXT,
            is_localizable=True, is_channel_scoped=True)

    def _row(self, **kw):
        kw.setdefault('value_text', 'v')
        return ProductValue.objects.create(
            product=self.product, attribute=self.attr, **kw)

    def _resolve(self, **scope):
        rows = list(ProductValue.objects.filter(product=self.product))
        return resolve_scoped_value(rows, self.attr,
                                    scope.get('channel'), scope.get('locale'))

    def test_exact_beats_global(self):
        self._row(value_text='global')
        exact = self._row(channel=self.channel, locale=self.locale, value_text='exact')
        self.assertEqual(self._resolve(channel='web', locale='de'), exact)

    def test_channel_only_beats_locale_only(self):
        # Documented tiebreak: channel-exact wins over locale-exact.
        loc_only = self._row(locale=self.locale, value_text='loc')
        chan_only = self._row(channel=self.channel, value_text='chan')
        self.assertEqual(self._resolve(channel='web', locale='de'), chan_only)
        self.assertEqual(loc_only.value_text, 'loc')  # fixture sanity

    def test_locale_only_beats_global(self):
        self._row(value_text='global')
        loc_only = self._row(locale=self.locale, value_text='loc')
        self.assertEqual(self._resolve(channel='web', locale='de'), loc_only)

    def test_out_of_scope_rows_ignored(self):
        other_ch = Channel.objects.create(code='other', name='O')
        other_loc = Locale.objects.create(code='fr', name='French')
        self._row(channel=other_ch, locale=other_loc, value_text='wrong')
        self.assertIsNone(self._resolve(channel='web', locale='de'))

    def test_nothing_set_returns_none(self):
        self.assertIsNone(self._resolve(channel='web', locale='de'))

    def test_empty_multiselect_skipped_in_favor_of_global(self):
        ms = Attribute.objects.create(
            code='ms', label='MS', type=AttributeTypes.MULTISELECT,
            is_localizable=True, is_channel_scoped=True)
        self.channel.locales.add(self.locale)
        empty_exact = ProductValue.objects.create(
            product=self.product, attribute=ms,
            channel=self.channel, locale=self.locale)  # no options
        opt = AttributeOption.objects.create(attribute=ms, code='a', label='A')
        glob = ProductValue.objects.create(product=self.product, attribute=ms)
        glob.options.add(opt)
        rows = list(ProductValue.objects.filter(product=self.product))
        self.assertEqual(
            resolve_scoped_value(rows, ms, 'web', 'de'), glob)
        self.assertTrue(empty_exact.pk is not None)  # fixture sanity
