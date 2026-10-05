"""Phase 2.2 API tests: auth, response shapes, filters, completeness math
(incl. empty-multiselect-unset), tree nesting. Uses Ninja TestClient.
"""
from decimal import Decimal

from django.test import TestCase
from ninja.testing import TestClient

from api.models import APIKey
from catalog.models import (
    AssociationTypes,
    Attribute,
    AttributeOption,
    AttributeSet,
    AttributeTypes,
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
from catalog.routers import router


class CatalogApiTest(TestCase):
    def setUp(self):
        self.client = TestClient(router)
        key = APIKey.objects.create(name='t')
        self.h = {'X-API-Key': key.api_key}

        self.locale = Locale.objects.create(code='en', name='English')
        self.channel = Channel.objects.create(code='web', name='Web')
        self.family = AttributeSet.objects.create(code='f', name='F')
        self.color = Attribute.objects.create(code='color', label='Color')
        self.size = Attribute.objects.create(
            code='size', label='Size', type=AttributeTypes.TEXT, is_variant_axis=True)
        self.family.attributes.add(self.color, self.size)
        self.rule = CompletenessRule.objects.create(
            channel=self.channel, locale=self.locale, family=self.family)
        self.rule.required_attributes.add(self.color, self.size)

        self.product = Product.objects.create(
            sku='T-001', name='Tee', list_price=Decimal('9.99'),
            family=self.family, is_active=True)
        ProductValue.objects.create(
            product=self.product, attribute=self.color, value_text='red')
        self.variant = ProductVariant.objects.create(
            product=self.product, sku='T-001-M', is_default=True)
        VariantValue.objects.create(
            variant=self.variant, attribute=self.size, value_text='M')
        root = Category.objects.create(name='Root', slug='root')
        child = Category.objects.create(name='Child', slug='child', parent=root)
        ProductCategory.objects.create(
            product=self.product, category=child, is_primary=True)
        ProductMedia.objects.create(product=self.product, role=MediaRoles.MAIN, file='')
        ProductMedia.objects.create(
            variant=self.variant, role=MediaRoles.GALLERY, file='')
        other = Product.objects.create(sku='T-002', name='Cap', list_price=Decimal('5'))
        ProductAssociation.objects.create(
            from_product=self.product, to_product=other, type=AssociationTypes.UPSELL)

    # Auth ---------------------------------------------------------------

    def test_unauthorized_without_key(self):
        assert self.client.get('/products/').status_code == 401

    def test_deactivated_key_rejected(self):
        dead = APIKey.objects.create(name='dead', is_active=False)
        h = {'X-API-Key': dead.api_key}
        assert self.client.get('/products/', headers=h).status_code == 401
        assert self.client.get('/families/', headers=h).status_code == 401

    def test_organization_now_requires_key(self):
        from api.main import app
        c = TestClient(app)
        assert c.get('/public/organization').status_code == 401

    # Products ------------------------------------------------------------

    def test_list_shape_has_no_stock_quantity(self):
        r = self.client.get('/products/', headers=self.h)
        assert r.status_code == 200, r.content[:200]
        item = r.json()['items'][0]
        assert item['sku'] == 'T-001'
        assert item['price'] == 9.99 and item['currency'] == 'USD'
        assert 'stock_quantity' not in item
        assert item['family'] == 'f'

    def test_list_filters(self):
        assert self.client.get('/products/?search=tee', headers=self.h).json()['count'] == 1
        assert self.client.get('/products/?search=nope', headers=self.h).json()['count'] == 0
        assert self.client.get('/products/?is_active=false', headers=self.h).json()['count'] == 1
        assert self.client.get('/products/?family=f', headers=self.h).json()['count'] == 1
        assert self.client.get('/products/?family=zz', headers=self.h).json()['count'] == 0

    def test_detail_nests_everything(self):
        r = self.client.get(f'/products/{self.product.id}/', headers=self.h)
        assert r.status_code == 200, r.content[:200]
        d = r.json()
        assert d['categories'][0]['is_primary'] is True
        assert d['categories'][0]['category']['slug'] == 'child'
        assert {'attribute': 'color', 'value': 'red'} == {
            k: v for k, v in d['values'][0].items() if k in ('attribute', 'value')}
        assert d['variants'][0]['sku'] == 'T-001-M'
        assert d['variants'][0]['values'][0]['value'] == 'M'
        assert len(d['media']) == 1  # product-owned only in detail
        assert 'stock_quantity' not in d

    # Families / attributes / refdata -------------------------------------

    def test_families(self):
        items = self.client.get('/families/', headers=self.h).json()['items']
        assert items[0]['code'] == 'f'
        d = self.client.get('/families/f/', headers=self.h).json()
        assert sorted(d['attributes']) == ['color', 'size']

    def test_attributes_with_options(self):
        size = Attribute.objects.create(code='sz', label='Sz', type=AttributeTypes.SELECT)
        AttributeOption.objects.create(attribute=size, code='s', label='S')
        d = self.client.get('/attributes/sz/', headers=self.h).json()
        assert d['options'][0]['code'] == 's'
        assert self.client.get('/attributes/', headers=self.h).json()['count'] >= 3

    def test_channels_locales(self):
        assert self.client.get('/channels/', headers=self.h).json()['items'][0]['code'] == 'web'
        assert self.client.get('/locales/', headers=self.h).json()['items'][0]['code'] == 'en'

    def test_tree_nests_children(self):
        roots = self.client.get('/categories/tree/', headers=self.h).json()
        assert len(roots) == 1 and roots[0]['slug'] == 'root'
        assert roots[0]['children'][0]['slug'] == 'child'
        assert self.client.get('/categories/tree/?kind=collection', headers=self.h).json() == []

    def test_tree_rejects_unknown_kind(self):
        r = self.client.get('/categories/tree/?kind=bogus', headers=self.h)
        assert r.status_code == 400
        assert set(r.json()) == {'error'}

    def test_cross_kind_parenting_rejected(self):
        from django.core.exceptions import ValidationError
        root = Category.objects.create(name='R', slug='xk-root')
        with self.assertRaises(ValidationError):
            Category(name='X', slug='xk-child', kind='collection', parent=root).full_clean()

    # Variants / media / relations ------------------------------------------

    def test_variants(self):
        items = self.client.get(
            f'/products/{self.product.id}/variants/', headers=self.h).json()
        assert items[0]['sku'] == 'T-001-M' and items[0]['is_default'] is True
        d = self.client.get('/variants/T-001-M/', headers=self.h).json()
        assert d['values'][0] == {
            'id': d['values'][0]['id'], 'attribute': 'size', 'type': 'text',
            'channel': None, 'locale': None, 'value': 'M'}

    def test_media_feed_combines_product_and_variant_rows(self):
        items = self.client.get(
            f'/products/{self.product.id}/media/', headers=self.h).json()
        by_role = {m['role']: m for m in items}
        assert by_role['main']['variant'] is None
        assert by_role['gallery']['variant'] == 'T-001-M'

    def test_relations_and_type_filter(self):
        items = self.client.get(
            f'/products/{self.product.id}/relations/', headers=self.h).json()
        assert items[0] == {'id': items[0]['id'], 'to_product': 'T-002', 'type': 'upsell'}
        assert self.client.get(
            f'/products/{self.product.id}/relations/?type=bundle',
            headers=self.h).json() == []

    def test_relations_rejects_unknown_type(self):
        r = self.client.get(
            f'/products/{self.product.id}/relations/?type=bogus', headers=self.h)
        assert r.status_code == 400
        assert set(r.json()) == {'error'}

    # Completeness ------------------------------------------------------------

    def test_completeness_math_and_cache_write(self):
        # color satisfied at product level, size satisfied on the variant —
        # variant-axis attributes count when any variant carries them.
        r = self.client.get(
            f'/products/{self.product.id}/completeness/?channel=web&locale=en',
            headers=self.h)
        assert r.status_code == 200, r.content[:200]
        d = r.json()
        assert d['percent'] == 100.0 and d['complete'] is True
        assert d['missing'] == [] and d['total_required'] == 2
        self.product.refresh_from_db()
        assert self.product.completeness_cache == {'web': 100.0}

    def test_completeness_truly_missing_variant_value(self):
        # Deleting the variant value re-opens the gap (proves variants count).
        VariantValue.objects.all().delete()
        d = self.client.get(
            f'/products/{self.product.id}/completeness/?channel=web&locale=en',
            headers=self.h).json()
        assert d['percent'] == 50.0 and d['missing'] == ['size']

    def test_completeness_empty_multiselect_counts_as_unset(self):
        ms = Attribute.objects.create(
            code='tags', label='Tags', type=AttributeTypes.MULTISELECT)
        self.rule.required_attributes.add(ms)
        ProductValue.objects.create(product=self.product, attribute=ms)  # no options
        d = self.client.get(
            f'/products/{self.product.id}/completeness/?channel=web&locale=en',
            headers=self.h).json()
        assert 'tags' in d['missing']

    def test_completeness_no_family_and_no_rule_are_404(self):
        bare = Product.objects.create(sku='BARE', name='B', list_price=Decimal('1'))
        r = self.client.get(
            f'/products/{bare.id}/completeness/?channel=web&locale=en', headers=self.h)
        assert r.status_code == 404
        self.rule.delete()
        r = self.client.get(
            f'/products/{self.product.id}/completeness/?channel=web&locale=en', headers=self.h)
        assert r.status_code == 404

    # Error envelope + schema ---------------------------------------------

    def test_404s_use_error_envelope(self):
        for path in ('/families/zz/', '/attributes/zz/',
                     '/products/zzz/', '/variants/zzz/',
                     '/products/zzz/media/', '/products/zzz/relations/',
                     '/products/zzz/completeness/?channel=web&locale=en'):
            r = self.client.get(path, headers=self.h)
            assert r.status_code == 404, path
            assert set(r.json()) == {'error'}, (path, r.json())

    def test_openapi_schema_builds_with_catalog_paths(self):
        from api.main import app
        schema = app.get_openapi_schema()
        paths = schema['paths']
        assert '/api/v1/catalog/products/{id}/' in paths
        assert '/api/v1/catalog/categories/tree/' in paths
        assert '/api/v1/catalog/products/{id}/completeness/' in paths
        # Exchange paths are gone (1.4 removal, Sunset lapsed in-app).
        assert not any('exchange-rate' in p or 'convert-product-price' in p
                       for p in paths)


class PublicCutoverTest(TestCase):
    """Phase 1.4: legacy /public/ paths serve catalog data (api models untouched)."""

    def setUp(self):
        from api.main import app
        self.client = TestClient(app)
        key = APIKey.objects.create(name='cut')
        self.h = {'X-API-Key': key.api_key}
        self.product = Product.objects.create(
            sku='CUT-001', name='Cut', list_price=Decimal('20.00'), is_active=True)
        root = Category.objects.create(name='R', slug='r')
        self.root_id = root.id
        ProductCategory.objects.create(product=self.product, category=root)
        ProductMedia.objects.create(product=self.product, role=MediaRoles.MAIN, file='')

    def _get(self, path):
        # NOTE: TestClient(app) resolves router-relative paths (no /api/v1/).
        return self.client.get(f'/public{path}', headers=self.h)

    def test_products_list_serves_catalog_without_stock(self):
        d = self._get('/products/').json()
        assert d['count'] >= 1
        item = next(i for i in d['items'] if i['sku'] == 'CUT-001')
        assert 'stock_quantity' not in item
        assert item['price'] == 20.0 and item['currency'] == 'USD'

    def test_products_filters_still_work(self):
        assert self._get('/products/?search=cut').json()['count'] == 1
        assert self._get('/products/?search=nope').json()['count'] == 0
        assert self._get('/products/?min_price=10&max_price=30').json()['count'] == 1
        assert self._get('/products/?min_price=100').json()['count'] == 0

    def test_product_detail_and_images_and_categories(self):
        d = self._get(f'/products/{self.product.id}/').json()
        assert d['sku'] == 'CUT-001' and 'stock_quantity' not in d
        media = self._get(f'/products/{self.product.id}/images/').json()
        assert len(media) == 1 and media[0]['role'] == 'main'
        cats = self._get('/categories/').json()
        assert any(c['slug'] == 'r' and 'kind' in c for c in cats['items'])
        by_cat = self._get(f'/categories/{self.root_id}/products/').json()
        assert any(i['sku'] == 'CUT-001' for i in by_cat['items'])

    def test_exchange_endpoints_are_gone(self):
        # Removed routes don't resolve at all in TestClient (real HTTP would 404).
        with self.assertRaises(Exception):
            self._get('/exchange-rate/?to_currency=EUR')
        with self.assertRaises(Exception):
            self._get('/convert-product-price/?product_sku=x&to_currency=EUR')


class OrganizationInversionTest(TestCase):
    """Phase 1.4: one org has many keys (was: org pointed at one key)."""

    def test_key_points_at_org_and_reverse_accessor(self):
        from api.models import Organization
        org = Organization.objects.create(name='Acme')
        key = APIKey.objects.create(name='k', organization=org)
        assert key.organization_id == org.pk
        assert list(org.api_keys.all()) == [key]

    def test_legacy_key_without_org_still_authenticates(self):
        from api.auth import header_key
        key = APIKey.objects.create(name='loose')
        assert key.organization_id is None
        # authenticate() only filters api_key + is_active (unchanged).
        assert header_key.authenticate(None, key.api_key) is not None


class ScopedReadsTest(TestCase):
    """Phase 3: resolved values endpoint + media scope filters."""

    def setUp(self):
        self.client = TestClient(router)
        key = APIKey.objects.create(name='s')
        self.h = {'X-API-Key': key.api_key}
        self.locale = Locale.objects.create(code='de', name='German')
        self.channel = Channel.objects.create(code='web', name='Web')
        self.channel.locales.add(self.locale)
        self.attr = Attribute.objects.create(
            code='t', label='T', type=AttributeTypes.TEXT,
            is_localizable=True, is_channel_scoped=True)
        self.product = Product.objects.create(
            sku='S-001', name='S', list_price=Decimal('1'))
        ProductValue.objects.create(
            product=self.product, attribute=self.attr, value_text='global')
        ProductMedia.objects.create(product=self.product, role=MediaRoles.GALLERY, file='')
        ch_media = ProductMedia.objects.create(
            product=self.product, role=MediaRoles.GALLERY, file='',
            channel=self.channel)
        self.ch_media_id = ch_media.id

    def test_resolved_values_exact_wins(self):
        ProductValue.objects.create(
            product=self.product, attribute=self.attr, channel=self.channel,
            locale=self.locale, value_text='exact')
        rows = self.client.get(
            f'/products/{self.product.id}/values/?channel=web&locale=de',
            headers=self.h).json()
        assert [(r['attribute'], r['value']) for r in rows] == [('t', 'exact')]

    def test_resolved_values_falls_back_to_global(self):
        rows = self.client.get(
            f'/products/{self.product.id}/values/?channel=web&locale=de',
            headers=self.h).json()
        assert [(r['attribute'], r['value']) for r in rows] == [('t', 'global')]

    def test_resolved_values_missing_product_404(self):
        r = self.client.get('/products/zzz/values/?channel=web&locale=de', headers=self.h)
        assert r.status_code == 404
        assert set(r.json()) == {'error'}

    def test_media_scope_filters(self):
        base = f'/products/{self.product.id}/media/'
        assert len(self.client.get(base, headers=self.h).json()) == 2
        scoped = self.client.get(base + '?channel=web', headers=self.h).json()
        assert len(scoped) == 2  # global + web-scoped
        other = self.client.get(base + '?channel=nope', headers=self.h).json()
        assert len(other) == 1  # only the global row survives
        loc_only = self.client.get(base + '?locale=de', headers=self.h).json()
        # Both rows: global matches everything, and the web-scoped row is
        # locale-generic (locale NULL matches any requested locale).
        assert len(loc_only) == 2
