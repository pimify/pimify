"""Phase 2 model tests: hybrid value validation matrix, placement/scope rules,
uniqueness (DB + NULL-safe clean), taxonomy guards, variant defaults,
media ownership, associations, and the api -> catalog backfill.
"""
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from api.models import Category as ApiCategory
from api.models import Product as ApiProduct
from catalog import backfill
from catalog.models import (
    AssociationTypes,
    Attribute,
    AttributeOption,
    AttributeSet,
    AttributeTypes,
    Brand,
    Category,
    Channel,
    CompletenessRule,
    Locale,
    MediaRoles,
    Product,
    ProductAssociation,
    ProductCategory,
    ProductMedia,
    ProductValue,
    ProductVariant,
    VariantValue,
)


def make_attr(code='color', type=AttributeTypes.TEXT, **kw):
    defaults = {'label': code, 'type': type}
    defaults.update(kw)
    return Attribute.objects.create(code=code, **defaults)


def make_product(sku='P-001'):
    return Product.objects.create(sku=sku, name=sku, list_price=Decimal('10.00'))


class AttributeValueTypeTest(TestCase):
    def setUp(self):
        self.product = make_product()

    def _value(self, attr, **kw):
        v = ProductValue(product=self.product, attribute=attr, **kw)
        v.full_clean()
        v.save()
        return v

    def test_text_ok_and_empty_rejected(self):
        attr = make_attr()
        self._value(attr, value_text='red')
        with self.assertRaises(ValidationError):
            self._value(make_attr('t2'), value_text='')

    def test_number_and_boolean_and_date(self):
        self._value(make_attr('n', AttributeTypes.NUMBER), value_decimal=Decimal('1.5'))
        with self.assertRaises(ValidationError):
            self._value(make_attr('n2', AttributeTypes.NUMBER))
        self._value(make_attr('b', AttributeTypes.BOOLEAN), value_bool=False)
        with self.assertRaises(ValidationError):
            self._value(make_attr('b2', AttributeTypes.BOOLEAN))
        from datetime import date
        self._value(make_attr('d', AttributeTypes.DATE), value_date=date(2026, 1, 1))

    def test_select_requires_own_option(self):
        attr = make_attr('size', AttributeTypes.SELECT)
        other = make_attr('material', AttributeTypes.SELECT)
        ok = AttributeOption.objects.create(attribute=attr, code='m', label='M')
        foreign = AttributeOption.objects.create(attribute=other, code='m', label='M')
        self._value(attr, option=ok)
        with self.assertRaises(ValidationError):
            self._value(attr)  # missing option
        with self.assertRaises(ValidationError):
            self._value(attr, option=foreign)  # other attribute's option

    def test_json_value(self):
        self._value(make_attr('j', AttributeTypes.JSON), value_json={'a': [1, 2]})

    def test_exactly_one_representation(self):
        attr = make_attr()
        v = ProductValue(product=self.product, attribute=attr,
                         value_text='x', value_decimal=Decimal('1'))
        with self.assertRaises(ValidationError):
            v.full_clean()


class AttributeScopePlacementTest(TestCase):
    def setUp(self):
        self.product = make_product()
        self.locale = Locale.objects.create(code='hi', name='Hindi')
        self.channel = Channel.objects.create(code='web', name='Web')

    def test_locale_channel_gated(self):
        attr = make_attr()  # neither localizable nor scoped
        for kw in ({'locale': self.locale}, {'channel': self.channel}):
            with self.assertRaises(ValidationError):
                v = ProductValue(product=self.product, attribute=attr, **kw)
                v.full_clean()
        ok_attr = make_attr('t2', is_localizable=True, is_channel_scoped=True)
        v = ProductValue(product=self.product, attribute=ok_attr,
                         locale=self.locale, channel=self.channel, value_text='x')
        v.full_clean()
        v.save()

    def test_axis_placement(self):
        axis = make_attr('ax', is_variant_axis=True)
        plain = make_attr()
        variant = ProductVariant.objects.create(product=self.product, sku='V-001')
        with self.assertRaises(ValidationError):
            ProductValue(product=self.product, attribute=axis, value_text='x').full_clean()
        with self.assertRaises(ValidationError):
            VariantValue(variant=variant, attribute=plain, value_text='x').full_clean()
        v = VariantValue(variant=variant, attribute=axis, value_text='m')
        v.full_clean()
        v.save()

    def test_null_safe_duplicate_guard(self):
        # Two identical unscoped rows: DB UNIQUE sees NULLs as distinct, clean() must catch it.
        attr = make_attr()
        v1 = ProductValue(product=self.product, attribute=attr, value_text='x')
        v1.full_clean()
        v1.save()
        with self.assertRaises(ValidationError):
            ProductValue(product=self.product, attribute=attr, value_text='y').full_clean()


class TaxonomyVariantAssociationTest(TestCase):
    def test_category_cycle_rejected(self):
        a = Category.objects.create(name='A', slug='a')
        b = Category.objects.create(name='B', slug='b', parent=a)
        a.parent = b
        with self.assertRaises(ValidationError):
            a.full_clean()

    def test_single_default_variant(self):
        p = make_product()
        ProductVariant.objects.create(product=p, sku='V-1', is_default=True)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ProductVariant.objects.create(product=p, sku='V-2', is_default=True)

    def test_association_self_ref_rejected(self):
        p = make_product()
        with self.assertRaises(ValidationError):
            ProductAssociation(
                from_product=p, to_product=p, type=AssociationTypes.UPSELL).full_clean()

    def test_media_requires_owner(self):
        with self.assertRaises(ValidationError):
            ProductMedia(role=MediaRoles.GALLERY, sort=0).full_clean()

    def test_brand_and_completeness_rule(self):
        brand = Brand.objects.create(name='Acme')
        p = make_product()
        p.brand = brand
        p.save()
        self.assertEqual(p.brand.name, 'Acme')
        fam = AttributeSet.objects.create(code='f', name='F')
        ch = Channel.objects.create(code='c', name='C')
        loc = Locale.objects.create(code='en', name='English')
        rule = CompletenessRule.objects.create(channel=ch, locale=loc, family=fam)
        attr = make_attr()
        rule.required_attributes.add(attr)
        self.assertEqual(rule.required_attributes.count(), 1)


class BackfillTest(TestCase):
    def test_forward_and_reverse(self):
        api_cat = ApiCategory.objects.create(name='C', slug='c')
        api_p = ApiProduct.objects.create(
            name='P', sku='BACK-001', description='d', price=Decimal('19.99'), is_active=True)
        api_p.categories.add(api_cat)

        backfill.forward()
        p = Product.objects.get(id=api_p.id)
        self.assertEqual(p.sku, 'BACK-001')
        self.assertEqual(p.list_price.amount, Decimal('19.99'))
        self.assertEqual(str(p.list_price.currency), 'USD')
        self.assertTrue(p.is_active)
        self.assertEqual(p.description, 'd')
        self.assertEqual(Category.objects.get(id=api_cat.id).kind, 'master')
        link = ProductCategory.objects.get(product=p, category_id=api_cat.id)
        self.assertFalse(link.is_primary)
        # Idempotent: second run changes nothing.
        backfill.forward()
        self.assertEqual(Product.objects.filter(id=api_p.id).count(), 1)

        backfill.reverse()
        self.assertFalse(Product.objects.filter(id=api_p.id).exists())
        self.assertFalse(Category.objects.filter(id=api_cat.id).exists())


class UniquenessConstraintsTest(TestCase):
    def setUp(self):
        self.product = make_product('U-001')
        self.other = make_product('U-002')

    def test_single_primary_category(self):
        c1 = Category.objects.create(name='C1', slug='u-c1')
        c2 = Category.objects.create(name='C2', slug='u-c2')
        ProductCategory.objects.create(product=self.product, category=c1, is_primary=True)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ProductCategory.objects.create(
                    product=self.product, category=c2, is_primary=True)
        # Non-primary second membership is fine; primary on another product is fine.
        ProductCategory.objects.create(product=self.product, category=c2)
        ProductCategory.objects.create(
            product=self.other, category=c1, is_primary=True)

    def _main(self, **kw):
        kw.setdefault('role', MediaRoles.MAIN)
        kw.setdefault('file', '')
        return ProductMedia.objects.create(**kw)

    def test_product_main_scoping(self):
        ch1 = Channel.objects.create(code='ch1', name='C1')
        ch2 = Channel.objects.create(code='ch2', name='C2')
        self._main(product=self.product)  # global main
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self._main(product=self.product)  # second global main
        self._main(product=self.product, channel=ch1)  # per-channel main coexists
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self._main(product=self.product, channel=ch1)  # same channel twice
        self._main(product=self.product, channel=ch2)  # different channel fine
        self._main(product=self.other)  # other product unaffected

    def test_variant_main_scoping(self):
        v = ProductVariant.objects.create(product=self.product, sku='U-V1')
        self._main(variant=v)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self._main(variant=v)


class MultiselectNonEmptyTest(TestCase):
    def test_saved_empty_multiselect_rejected(self):
        p = make_product('M-001')
        var = ProductVariant.objects.create(product=p, sku='M-V1')
        attr = make_attr('msx', AttributeTypes.MULTISELECT, is_variant_axis=True)
        v = VariantValue(variant=var, attribute=attr)
        v.save()  # creation can't check M2M (no pk yet) — allowed
        with self.assertRaises(ValidationError):
            v.full_clean()  # ...but a saved empty row must fail validation
        opt = AttributeOption.objects.create(attribute=attr, code='a', label='A')
        v.options.add(opt)
        v.full_clean()  # passes once an option exists (asserts no raise)
