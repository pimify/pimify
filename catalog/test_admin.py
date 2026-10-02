"""Phase 2.3 admin smoke: every catalog changelist + key changeforms render.

Catches bad sidebar reverse_lazy names, broken inlines/value forms, and
SimpleHistoryAdmin MRO issues — all of which fail loudly (500/NoReverseMatch)
instead of silently.
"""
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import Client, TestCase

from catalog.models import MediaRoles, Product, ProductMedia, ProductVariant

CHANGELISTS = [
    '/dashboard/catalog/product/',
    '/dashboard/catalog/productvariant/',
    '/dashboard/catalog/productmedia/',
    '/dashboard/catalog/productassociation/',
    '/dashboard/catalog/category/',
    '/dashboard/catalog/attribute/',
    '/dashboard/catalog/attributeset/',
    '/dashboard/catalog/attributegroup/',
    '/dashboard/catalog/channel/',
    '/dashboard/catalog/locale/',
    '/dashboard/catalog/brand/',
    '/dashboard/catalog/completenessrule/',
    '/dashboard/',  # sidebar reverse_lazy + dashboard_callback
    '/dashboard/api/product/',  # legacy api admin still renders
]


class CatalogAdminSmokeTest(TestCase):
    def setUp(self):
        self.client = Client(HTTP_USER_AGENT='admin-smoke')
        User.objects.create_superuser('admin', 'a@x.com', 'pw')
        # Real form login (not force_login/client.login): dj-user-login-history's
        # post_login receiver reads HTTP_USER_AGENT, which the login() helpers
        # don't put on their synthetic request. Full POST goes through properly.
        self.client.post(
            '/dashboard/login/', {'username': 'admin', 'password': 'pw'}, follow=True)
        self.product = Product.objects.create(sku='ADM-001', name='Adm', list_price=Decimal('1'))
        self.variant = ProductVariant.objects.create(product=self.product, sku='ADM-V1')

    def test_changelists_and_dashboard_render(self):
        for url in CHANGELISTS:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_product_add_and_change_render(self):
        # Change form exercises all four tabbed inlines + the value form.
        self.assertEqual(
            self.client.get('/dashboard/catalog/product/add/').status_code, 200)
        self.assertEqual(
            self.client.get(f'/dashboard/catalog/product/{self.product.pk}/change/').status_code, 200)
        self.assertEqual(
            self.client.get(f'/dashboard/catalog/productvariant/{self.variant.pk}/change/').status_code, 200)

    def test_history_views_render(self):
        # Exercises the SimpleHistoryAdmin mixin (MRO risk).
        self.assertEqual(
            self.client.get(f'/dashboard/catalog/product/{self.product.pk}/history/').status_code, 200)
        self.assertEqual(
            self.client.get(f'/dashboard/catalog/productvariant/{self.variant.pk}/history/').status_code, 200)

    def test_sidebar_marks_legacy_section(self):
        # Phase 2.3 audit: legacy api.* links must not masquerade as catalog.
        content = self.client.get('/dashboard/').content
        self.assertIn(b'Legacy (deprecated)', content)
        self.assertIn(b'Catalog', content)


class DashboardKpiTest(TestCase):
    def setUp(self):
        self.product = Product.objects.create(sku='KPI-001', name='Kpi', list_price=Decimal('1'))
        self.variant = ProductVariant.objects.create(product=self.product, sku='KPI-V1')

    def test_missing_media_counts_variant_only_media_as_present(self):
        # Regression: the old query only joined product-level media, so a
        # product whose assets live entirely on variants read as "missing".
        # Each product below isolates one case, so old and new queries differ.
        from api.views import dashboard_callback

        direct = Product.objects.create(sku='KPI-DIRECT', name='D', list_price=Decimal('1'))
        ProductMedia.objects.create(product=direct, role=MediaRoles.MAIN, file='')
        ProductMedia.objects.create(
            variant=self.variant, role=MediaRoles.GALLERY, file='')
        Product.objects.create(sku='KPI-BARE', name='Bare', list_price=Decimal('1'))

        context = dashboard_callback(None, {})
        missing = next(kpi for kpi in context['kpi'] if kpi['title'] == 'Missing Media')
        # setUp product has variant-only media, DIRECT has product media,
        # BARE has none -> only BARE counts. Old query returned 2.
        self.assertEqual(missing['metric'], 1)
