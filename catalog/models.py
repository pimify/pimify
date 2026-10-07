"""Phase 2 (pure-PIM pivot): the pure product-information domain.

Ownership rules (see TODO.md Decisions Locked):
- PIM owns descriptive/product data + list_price (msrp). NEVER stock
  quantities, cost prices or lead times — those live in inventory/procurement.
- Attribute values use the hybrid typed-column store: one row per
  (owner, attribute, channel, locale) scope with typed value columns plus a
  JSON overflow. NOT pure EAV, NOT a single JSON blob. SQLite now (TEXT-backed
  JSONField), JSONB + GIN on Postgres later with zero code change.
- Hoy: channel/locale scoping columns exist but enforcement starts in
  Phase 3. Until then, values are product-level + variant-axis only.
"""
import os

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.db.models.signals import post_delete
from django.dispatch import receiver
from django.utils.text import slugify
from djmoney.models.fields import MoneyField
from simple_history.models import HistoricalRecords

from api.models import NanoIDField


# ---------------------------------------------------------------------------
# Reference data: locales, channels, brands
# ---------------------------------------------------------------------------

class Locale(models.Model):
    """A language/region code products can be translated into (e.g. en, hi)."""

    code = models.CharField(max_length=10, primary_key=True)
    name = models.CharField(max_length=100)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.code


class Channel(models.Model):
    """A sales/output channel with its own locale set (e.g. amazon-in, web)."""

    code = models.SlugField(max_length=40, primary_key=True)
    name = models.CharField(max_length=100)
    default_locale = models.ForeignKey(
        Locale, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    locales = models.ManyToManyField(Locale, related_name='channels', blank=True)
    default_currency = models.CharField(max_length=3, default='USD')

    def __str__(self):
        return self.code


class Brand(models.Model):
    """Lightweight manufacturer/brand entity. NOT a Supplier (no vendor terms)."""

    id = NanoIDField(primary_key=True)
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=100, unique=True, blank=True,
                            allow_unicode=True,
                            help_text="Stable key for feeds/URLs. Auto-filled from name.")

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = self._unique_slug()
        super().save(*args, **kwargs)

    def _unique_slug(self):
        """Slug candidate that can never collide or come out empty.

        allow_unicode keeps non-Latin names (hi/ta/...) as real slugs
        instead of '' (ASCII slugify strips them, and '' would collide on
        the unique constraint). A nanoid fallback covers names with no
        slugable characters at all; a numeric suffix disambiguates
        same-slug names ('Acme' vs 'ACME'). Only ever fills an empty
        slug, so renames never thrash feed keys.
        """
        max_len = self._meta.get_field('slug').max_length
        base = slugify(self.name, allow_unicode=True) or f"brand-{self.id}"
        slug, n = base[:max_len], 2
        while (Brand.objects.filter(slug=slug).exclude(pk=self.pk).exists()):
            suffix = f"-{n}"
            slug = base[:max_len - len(suffix)] + suffix
            n += 1
        return slug


# ---------------------------------------------------------------------------
# Taxonomy: categories (tree) + product membership
# ---------------------------------------------------------------------------

class CategoryKind(models.TextChoices):
    MASTER = 'master', 'Master'
    COLLECTION = 'collection', 'Collection'


class Category(models.Model):
    """Product taxonomy node. Multiple trees via kind (navigation vs merch)."""

    id = NanoIDField(primary_key=True)
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)
    parent = models.ForeignKey(
        'self', null=True, blank=True, on_delete=models.CASCADE, related_name='children')
    kind = models.CharField(max_length=12, choices=CategoryKind.choices, default=CategoryKind.MASTER)
    sort = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name_plural = 'Categories'
        indexes = [
            models.Index(fields=['id']),
            models.Index(fields=['name']),
        ]

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()
        if self.parent_id is not None and self.parent.kind != self.kind:
            raise ValidationError(
                {'parent': 'Parent must be of the same kind (master and collection trees must not interleave).'})
        # Guard against taxonomy cycles (A -> B -> A).
        seen = {self.pk} if self.pk else set()
        node = self.parent
        while node is not None:
            if node.pk in seen:
                raise ValidationError({'parent': 'Category parent would create a cycle.'})
            seen.add(node.pk)
            node = node.parent if node.pk else None


# ---------------------------------------------------------------------------
# Attributes: groups, definitions, options, families
# ---------------------------------------------------------------------------

class AttributeGroup(models.Model):
    """Named bucket of attributes inside a family (drives admin fieldsets)."""

    code = models.SlugField(max_length=80, primary_key=True)
    name = models.CharField(max_length=120)
    sort = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['sort']

    def __str__(self):
        return self.name


class AttributeTypes(models.TextChoices):
    TEXT = 'text', 'Text'
    TEXTAREA = 'textarea', 'Textarea'
    NUMBER = 'number', 'Number'
    BOOLEAN = 'boolean', 'Boolean'
    DATE = 'date', 'Date'
    URL = 'url', 'URL'
    SELECT = 'select', 'Select'
    MULTISELECT = 'multiselect', 'Multiselect'
    JSON = 'json', 'JSON'


class Attribute(models.Model):
    """A product specification definition (e.g. color, screen_size_in)."""

    code = models.SlugField(max_length=80, primary_key=True)
    label = models.CharField(max_length=120)
    type = models.CharField(max_length=12, choices=AttributeTypes.choices)
    group = models.ForeignKey(
        AttributeGroup, null=True, blank=True, on_delete=models.SET_NULL, related_name='attributes')
    is_required = models.BooleanField(default=False)
    is_localizable = models.BooleanField(default=False)
    is_channel_scoped = models.BooleanField(default=False)
    is_variant_axis = models.BooleanField(
        default=False,
        help_text="Axis attributes define variants (size, color) and live on VariantValue only.")
    sort = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['sort']

    def __str__(self):
        return self.code


class AttributeOption(models.Model):
    """One allowed value for a SELECT/MULTISELECT attribute."""

    attribute = models.ForeignKey(Attribute, on_delete=models.CASCADE, related_name='options')
    code = models.SlugField(max_length=80)
    label = models.CharField(max_length=120)
    sort = models.PositiveSmallIntegerField(default=0)

    class Meta:
        unique_together = ('attribute', 'code')
        ordering = ['sort']

    def __str__(self):
        return f"{self.attribute_id}:{self.code}"


class AttributeSet(models.Model):
    """A product family: the attribute contract products of one kind fulfil."""

    code = models.SlugField(max_length=80, primary_key=True)
    name = models.CharField(max_length=120)
    groups = models.ManyToManyField(AttributeGroup, related_name='families', blank=True)
    attributes = models.ManyToManyField(Attribute, related_name='families', blank=True)

    def __str__(self):
        return self.code


# ---------------------------------------------------------------------------
# Products, variants, hybrid attribute values
# ---------------------------------------------------------------------------

class Product(models.Model):
    """The buying decision (model code). Sellable SKUs live on ProductVariant."""

    id = NanoIDField(primary_key=True)
    sku = models.CharField(max_length=150, unique=True)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    family = models.ForeignKey(
        AttributeSet, null=True, blank=True, on_delete=models.SET_NULL, related_name='products')
    brand = models.ForeignKey(
        Brand, null=True, blank=True, on_delete=models.SET_NULL, related_name='products')
    list_price = MoneyField(max_digits=14, decimal_places=2, default_currency='USD')
    is_active = models.BooleanField(default=False)
    is_published = models.BooleanField(
        default=False,
        help_text="Approved for feeds. is_active = exists in PIM; "
                  "is_published = may leave the building.")
    published_at = models.DateTimeField(
        null=True, blank=True,
        help_text="First build that shipped this product (frozen; the Studio "
                  "diff baseline).")
    last_shipped_at = models.DateTimeField(
        null=True, blank=True,
        help_text="Most recent build that shipped this product.")
    categories = models.ManyToManyField(
        Category, through='ProductCategory', related_name='products')
    completeness_cache = models.JSONField(
        default=dict,
        help_text="Denormalized {channel_code: percent} completeness. Recomputed, never hand-edited.")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    history = HistoricalRecords()

    class Meta:
        indexes = [
            models.Index(fields=['id']),
            models.Index(fields=['name']),
            models.Index(fields=['sku']),
        ]

    def __str__(self):
        return self.sku


class ProductCategory(models.Model):
    """Product <-> Category membership with one primary category."""

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='category_links')
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='product_links')
    is_primary = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['product', 'category'], name='uniq_product_category'),
            # Exactly one primary category per product. NULL-free column, fully enforced.
            models.UniqueConstraint(
                fields=['product'], condition=Q(is_primary=True),
                name='uniq_primary_category_per_product'),
        ]


class BaseAttributeValue(models.Model):
    """Hybrid typed value store, one row per (owner, attribute, channel, locale).

    Exactly one representation column is populated, dictated by
    Attribute.type. Uniqueness within a scope is enforced twice: a DB
    UniqueConstraint (works when channel+locale are set) plus a NULL-safe
    duplicate check in clean() (NULLs are never equal in SQL).
    """

    attribute = models.ForeignKey(Attribute, on_delete=models.PROTECT, related_name='+')
    channel = models.ForeignKey(
        Channel, null=True, blank=True, on_delete=models.PROTECT, related_name='+')
    locale = models.ForeignKey(
        Locale, null=True, blank=True, on_delete=models.PROTECT, related_name='+')

    value_text = models.TextField(null=True, blank=True)
    value_decimal = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    value_bool = models.BooleanField(null=True, blank=True)
    value_date = models.DateField(null=True, blank=True)
    option = models.ForeignKey(
        AttributeOption, null=True, blank=True, on_delete=models.PROTECT, related_name='+')
    options = models.ManyToManyField(AttributeOption, blank=True, related_name='+')
    value_json = models.JSONField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Concrete subclasses set these.
    variant_level = False
    owner_field = 'product'

    # Attribute.type -> representation column.
    _TYPE_COLUMN = {
        AttributeTypes.TEXT: 'value_text',
        AttributeTypes.TEXTAREA: 'value_text',
        AttributeTypes.URL: 'value_text',
        AttributeTypes.NUMBER: 'value_decimal',
        AttributeTypes.BOOLEAN: 'value_bool',
        AttributeTypes.DATE: 'value_date',
        AttributeTypes.SELECT: 'option',
        AttributeTypes.MULTISELECT: 'options',
        AttributeTypes.JSON: 'value_json',
    }

    class Meta:
        abstract = True

    def clean(self):
        super().clean()
        attr = self.attribute
        if attr is None:
            raise ValidationError({'attribute': 'Attribute is required.'})

        # Axis placement: axis attributes live on variants only and vice versa.
        if self.variant_level != attr.is_variant_axis:
            where = 'variant' if self.variant_level else 'product'
            kind = 'a variant-axis' if attr.is_variant_axis else 'not a variant-axis'
            raise ValidationError(
                {'attribute': f"'{attr.code}' is {kind} attribute and cannot be set at {where} level."})

        # Scope: locale/channel may only be set when the attribute allows it.
        if self.locale_id is not None and not attr.is_localizable:
            raise ValidationError({'locale': f"'{attr.code}' is not localizable."})
        if self.channel_id is not None and not attr.is_channel_scoped:
            raise ValidationError({'channel': f"'{attr.code}' is not channel-scoped."})
        # Membership: a value scoped to both must name a locale the channel
        # actually offers — the locales M2M plus the default locale, which is
        # implicitly offered (Phase 4.3: default_locale was previously ignored
        # here, so a value scoped to a channel's own default locale was
        # rejected when the M2M was empty). Either side alone (or neither) is
        # always allowed.
        if self.locale_id is not None and self.channel_id is not None:
            offered = (self.channel.locales.filter(pk=self.locale_id).exists()
                       or self.channel.default_locale_id == self.locale_id)
            if not offered:
                raise ValidationError(
                    {'locale': f"'{self.locale_id}' is not offered on channel '{self.channel_id}'."})

        column = self._TYPE_COLUMN[attr.type]

        # The mapped representation must be present...
        if column == 'option':
            if self.option_id is None:
                raise ValidationError({'option': f"'{attr.code}' requires an option."})
            if self.option.attribute_id != attr.pk:
                raise ValidationError({'option': 'Option does not belong to this attribute.'})
        elif column == 'options':
            # Presence needs a pk (M2M is assigned after first save), so
            # emptiness can only be enforced on saved rows — see below.
            pass
        elif column == 'value_bool':
            if self.value_bool is None:
                raise ValidationError({column: f"'{attr.code}' requires a value."})
        elif getattr(self, column) in (None, ''):
            raise ValidationError({column: f"'{attr.code}' requires a value."})

        # ...and every other representation must be empty (exactly one source of truth).
        for other in ('value_text', 'value_decimal', 'value_bool', 'value_date', 'value_json'):
            if other == column:
                continue
            if getattr(self, other) not in (None, ''):
                raise ValidationError({other: 'Only one value representation may be set.'})
        if column != 'option' and self.option_id is not None:
            raise ValidationError({'option': 'Only one value representation may be set.'})
        if self.pk is not None:
            if column != 'options' and self.options.exists():
                raise ValidationError({'options': 'Only one value representation may be set.'})
            if column == 'options':
                if self.options.exclude(attribute=attr).exists():
                    raise ValidationError({'options': 'All options must belong to this attribute.'})
                if not self.options.exists():
                    raise ValidationError(
                        {'options': f"'{attr.code}' requires at least one option."})

        # NULL-safe duplicate guard (DB constraint can't see NULL scope as equal).
        owner_id = getattr(self, f"{self.owner_field}_id", None)
        if owner_id is not None and attr.pk is not None:
            dupes = type(self)._default_manager.filter(
                attribute=attr, channel=self.channel, locale=self.locale,
                **{f"{self.owner_field}_id": owner_id},
            )
            if self.pk is not None:
                dupes = dupes.exclude(pk=self.pk)
            if dupes.exists():
                raise ValidationError('Duplicate value for this owner/attribute/channel/locale scope.')


class ProductValue(BaseAttributeValue):
    """Attribute value at product (model) level. Axis attributes forbidden here."""

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='values')

    variant_level = False
    owner_field = 'product'

    history = HistoricalRecords()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['product', 'attribute', 'channel', 'locale'],
                name='uniq_product_value_scope'),
        ]


class ProductVariant(models.Model):
    """A sellable SKU under a Product (size/color axis combination)."""

    id = NanoIDField(primary_key=True)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='variants')
    sku = models.CharField(max_length=150, unique=True)
    is_default = models.BooleanField(default=False)
    list_price = MoneyField(
        max_digits=14, decimal_places=2, null=True, blank=True,
        help_text="Per-variant MSRP override; falls back to Product.list_price. "
                  "Never cost — PIM owns list price only.")
    sort = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    history = HistoricalRecords()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['product'], condition=Q(is_default=True),
                name='uniq_default_variant_per_product'),
        ]
        ordering = ['sort']

    def __str__(self):
        return self.sku


class VariantValue(BaseAttributeValue):
    """Attribute value at variant level. Only variant-axis attributes allowed."""

    variant = models.ForeignKey(ProductVariant, on_delete=models.CASCADE, related_name='values')

    variant_level = True
    owner_field = 'variant'

    history = HistoricalRecords()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['variant', 'attribute', 'channel', 'locale'],
                name='uniq_variant_value_scope'),
        ]


# ---------------------------------------------------------------------------
# Media, associations, completeness rules
# ---------------------------------------------------------------------------

class MediaRoles(models.TextChoices):
    MAIN = 'main', 'Main'
    GALLERY = 'gallery', 'Gallery'
    SWATCH = 'swatch', 'Swatch'
    MANUAL = 'manual', 'Manual'


class ProductMedia(models.Model):
    """Generic product asset (image/video/doc). Same upload dir as legacy images."""

    product = models.ForeignKey(
        Product, null=True, blank=True, on_delete=models.CASCADE, related_name='media')
    variant = models.ForeignKey(
        ProductVariant, null=True, blank=True, on_delete=models.CASCADE, related_name='media')
    file = models.ImageField(upload_to='product_images/')
    role = models.CharField(max_length=12, choices=MediaRoles.choices, default=MediaRoles.GALLERY)
    sort = models.PositiveIntegerField(default=0)
    channel = models.ForeignKey(
        Channel, null=True, blank=True, on_delete=models.PROTECT, related_name='+')
    locale = models.ForeignKey(
        Locale, null=True, blank=True, on_delete=models.PROTECT, related_name='+')
    alt_text = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        ordering = ['sort']
        constraints = [
            # At most one global main + one main per channel, separately for
            # product- and variant-owned media. NULL owner/channel rows never
            # collide (SQL NULL semantics), which is exactly the scoping we
            # want: variant-owned rows are invisible to product constraints.
            models.UniqueConstraint(
                fields=['product'], condition=Q(role='main', channel__isnull=True),
                name='uniq_main_media_product'),
            models.UniqueConstraint(
                fields=['product', 'channel'],
                condition=Q(role='main', channel__isnull=False),
                name='uniq_main_media_product_channel'),
            models.UniqueConstraint(
                fields=['variant'], condition=Q(role='main', channel__isnull=True),
                name='uniq_main_media_variant'),
            models.UniqueConstraint(
                fields=['variant', 'channel'],
                condition=Q(role='main', channel__isnull=False),
                name='uniq_main_media_variant_channel'),
        ]

    def __str__(self):
        return f"{self.role}:{self.pk}"

    def clean(self):
        super().clean()
        if self.product_id is None and self.variant_id is None:
            raise ValidationError('Media must belong to a product or a variant.')


@receiver(post_delete, sender=ProductMedia)
def delete_media_file(sender, instance, **kwargs):
    """Clean up the asset file when a ProductMedia row is deleted."""
    if instance.file and os.path.isfile(instance.file.path):
        os.remove(instance.file.path)


class AssociationTypes(models.TextChoices):
    UPSELL = 'upsell', 'Upsell'
    CROSS_SELL = 'cross-sell', 'Cross-sell'
    BUNDLE = 'bundle', 'Bundle'
    ACCESSORY = 'accessory', 'Accessory'


class ProductAssociation(models.Model):
    """Merchandising relation between two products (upsell, bundle, ...)."""

    from_product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name='associations_from')
    to_product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name='associations_to')
    type = models.CharField(max_length=12, choices=AssociationTypes.choices)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['from_product', 'to_product', 'type'], name='uniq_association'),
        ]

    def __str__(self):
        return f"{self.from_product_id} -{self.type}-> {self.to_product_id}"

    def clean(self):
        super().clean()
        if (self.from_product_id is not None and self.from_product_id == self.to_product_id):
            raise ValidationError('A product cannot be associated with itself.')


class CompletenessRule(models.Model):
    """Which attributes a family must have per channel+locale to be publishable."""

    channel = models.ForeignKey(Channel, on_delete=models.CASCADE, related_name='completeness_rules')
    locale = models.ForeignKey(Locale, on_delete=models.CASCADE, related_name='completeness_rules')
    family = models.ForeignKey(
        AttributeSet, on_delete=models.CASCADE, related_name='completeness_rules')
    required_attributes = models.ManyToManyField(Attribute, related_name='completeness_rules')

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['channel', 'locale', 'family'], name='uniq_completeness_rule'),
        ]

    def __str__(self):
        return f"{self.family_id}/{self.channel_id}/{self.locale_id}"


class FeedFormat(models.TextChoices):
    JSON = 'json', 'JSON'
    CSV = 'csv', 'CSV'


class Feed(models.Model):
    """A named outbound channel feed: resolved product payload for one scope.

    Pull model only: `build_feed` renders the file, consumers fetch it via
    the runs API. Direction is strictly PIM -> commerce; ERP/WMS remain
    read-only sources outside PIM ownership (Phase 4 decision).
    """

    name = models.CharField(max_length=100, unique=True)
    channel = models.ForeignKey(Channel, on_delete=models.PROTECT, related_name='feeds')
    locale = models.ForeignKey(Locale, on_delete=models.PROTECT, related_name='feeds')
    format = models.CharField(
        max_length=4, choices=FeedFormat.choices, default=FeedFormat.JSON)
    is_active = models.BooleanField(default=True)
    only_complete = models.BooleanField(
        default=False,
        help_text="Exclude products below 100% completeness for this scope.")
    schedule_cron = models.CharField(
        max_length=100, blank=True, default='',
        help_text="Crontab cadence (e.g. '0 6 * * *'); blank = manual builds only.")
    profile = models.ForeignKey(
        'PlatformProfile', null=True, blank=True, on_delete=models.PROTECT,
        related_name='feeds',
        help_text="Platform transform rendered instead of the generic payload.")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} [{self.channel_id}/{self.locale_id}.{self.format}]"

    def clean(self):
        super().clean()
        if self.schedule_cron:
            from apscheduler.triggers.cron import CronTrigger  # local: avoid hard dep at import
            try:
                CronTrigger.from_crontab(self.schedule_cron)
            except ValueError as exc:
                from django.core.exceptions import ValidationError
                raise ValidationError({'schedule_cron': f'Invalid crontab: {exc}'})
        if self.profile_id is not None and self.format == FeedFormat.CSV:
            from django.core.exceptions import ValidationError
            raise ValidationError(
                {'profile': 'Platform artifacts are JSON; unset the profile for CSV feeds.'})
        # Phase 4.3: publishing to a deactivated locale is refused. Admin
        # surfaces this via full_clean; run_feed enforces it on the build
        # path (the scheduler bypasses clean()).
        if self.locale_id is not None and not self.locale.is_active:
            from django.core.exceptions import ValidationError
            raise ValidationError(
                {'locale': f"Locale {self.locale_id!r} is inactive; "
                           'deactivate the feed instead.'})


class PlatformChoices(models.TextChoices):
    SHOPIFY = 'shopify', 'Shopify'
    AMAZON = 'amazon', 'Amazon'
    FLIPKART = 'flipkart', 'Flipkart'


class PlatformProfile(models.Model):
    """How one platform consumes the generic feed payload for a channel.

    Transformers are pure functions over the generic payload (file-artifact
    v1, no network); `attribute_map` is {pim_attribute_code: platform key}
    and `category_map` is {pim_category_slug: platform product type}.
    """

    platform = models.CharField(
        max_length=8, choices=PlatformChoices.choices, default=PlatformChoices.SHOPIFY)
    name = models.CharField(max_length=100, unique=True)
    channel = models.ForeignKey(
        Channel, on_delete=models.PROTECT, related_name='platform_profiles')
    attribute_map = models.JSONField(
        default=dict,
        help_text="{pim_attribute_code: platform metafield key}.")
    category_map = models.JSONField(
        default=dict,
        help_text="{pim_category_slug: platform product type}.")
    defaults = models.JSONField(
        default=dict,
        help_text="{vendor, status, tags[], product_type, metafield_namespace}.")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['platform', 'channel'], name='uniq_platform_profile_channel'),
        ]

    def __str__(self):
        return f"{self.name} [{self.platform}/{self.channel_id}]"

    def clean(self):
        super().clean()
        from django.core.exceptions import ValidationError
        unknown = sorted(
            code for code in (self.attribute_map or {})
            if not Attribute.objects.filter(pk=code).exists())
        if unknown:
            raise ValidationError(
                {'attribute_map': f'Unknown attribute codes: {unknown}.'})


class FeedRunStatus(models.TextChoices):
    SUCCESS = 'success', 'Success'
    FAILED = 'failed', 'Failed'


class FeedRun(models.Model):
    """Append-only log of feed builds. Files live under FEEDS_ROOT, served
    by the runs download endpoint. Never edited (audit trail)."""

    feed = models.ForeignKey(Feed, on_delete=models.CASCADE, related_name='runs')
    status = models.CharField(max_length=7, choices=FeedRunStatus.choices)
    items = models.PositiveIntegerField(default=0)
    skipped = models.JSONField(
        default=dict,
        help_text="{reason: [skus]} excluded from this build "
                  "(unpublished / incomplete / no_rule / platform reasons).")
    report = models.JSONField(
        default=dict,
        help_text="Platform transform report (warnings/notes); {} for generic feeds.")
    file = models.CharField(
        max_length=255, blank=True, default='',
        help_text="Path relative to FEEDS_ROOT; empty when the run failed.")
    error = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.feed_id} {self.created_at:%Y-%m-%d %H:%M} {self.status} ({self.items})"
