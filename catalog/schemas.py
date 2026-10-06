"""Phase 2.2: Ninja schemas for the pure-PIM catalog surface.

Same class names as api/schemas.py on purpose — these shapes prefigure the
1.4 cutover, when catalog querysets replace the legacy api ones.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

from ninja import Schema

from .models import AttributeTypes


# Reference data ------------------------------------------------------------

class LocaleSchema(Schema):
    code: str
    name: str
    is_active: bool


class ChannelSchema(Schema):
    code: str
    name: str
    default_currency: str
    default_locale: Optional[str] = None
    locales: List[str] = []

    @staticmethod
    def resolve_default_locale(obj):
        return obj.default_locale_id

    @staticmethod
    def resolve_locales(obj):
        return [loc.code for loc in obj.locales.all()]


class BrandSchema(Schema):
    id: str
    name: str


# Attributes ----------------------------------------------------------------

class AttributeOptionSchema(Schema):
    id: int
    code: str
    label: str
    sort: int


class AttributeSchema(Schema):
    code: str
    label: str
    type: str
    group: Optional[str] = None
    is_required: bool
    is_localizable: bool
    is_channel_scoped: bool
    is_variant_axis: bool
    options: List[AttributeOptionSchema] = []

    @staticmethod
    def resolve_group(obj):
        return obj.group_id


class FamilyListSchema(Schema):
    code: str
    name: str


class FamilyDetailSchema(Schema):
    code: str
    name: str
    groups: List[str] = []
    attributes: List[str] = []

    @staticmethod
    def resolve_groups(obj):
        return [g.code for g in obj.groups.all()]

    @staticmethod
    def resolve_attributes(obj):
        return [a.code for a in obj.attributes.all()]


# Categories ----------------------------------------------------------------

class CategorySchema(Schema):
    id: str
    name: str
    slug: str
    kind: str
    sort: int
    parent: Optional[str] = None

    @staticmethod
    def resolve_parent(obj):
        return obj.parent_id


class CategoryTreeSchema(Schema):
    id: str
    name: str
    slug: str
    kind: str
    sort: int
    children: List['CategoryTreeSchema'] = []


CategoryTreeSchema.model_rebuild()


class ProductCategorySchema(Schema):
    category: CategorySchema
    is_primary: bool


# Values, variants, products -------------------------------------------------

def resolve_attribute_value(obj) -> Any:
    """Single consumer-friendly representation for a hybrid value row."""
    t = obj.attribute.type
    if t == AttributeTypes.SELECT:
        return obj.option.code if obj.option_id else None
    if t == AttributeTypes.MULTISELECT:
        return [o.code for o in obj.options.all()]
    if t == AttributeTypes.NUMBER:
        return float(obj.value_decimal) if obj.value_decimal is not None else None
    if t == AttributeTypes.BOOLEAN:
        return obj.value_bool
    if t == AttributeTypes.DATE:
        return obj.value_date
    if t == AttributeTypes.JSON:
        return obj.value_json
    return obj.value_text


class AttributeValueSchema(Schema):
    id: int
    attribute: str
    type: str
    channel: Optional[str] = None
    locale: Optional[str] = None
    value: Any = None

    @staticmethod
    def resolve_attribute(obj):
        return obj.attribute_id

    @staticmethod
    def resolve_type(obj):
        return obj.attribute.type

    @staticmethod
    def resolve_channel(obj):
        return obj.channel_id

    @staticmethod
    def resolve_locale(obj):
        return obj.locale_id

    @staticmethod
    def resolve_value(obj):
        return resolve_attribute_value(obj)


class VariantSchema(Schema):
    id: str
    sku: str
    is_default: bool
    sort: int
    price: Optional[float] = None
    values: List[AttributeValueSchema] = []

    @staticmethod
    def resolve_price(obj):
        return float(obj.list_price.amount) if obj.list_price is not None else None


class MediaSchema(Schema):
    id: int
    file: str
    role: str
    sort: int
    channel: Optional[str] = None
    locale: Optional[str] = None
    alt_text: Optional[str] = None
    variant: Optional[str] = None

    @staticmethod
    def resolve_file(obj):
        return obj.file.url if obj.file else ''

    @staticmethod
    def resolve_channel(obj):
        return obj.channel_id

    @staticmethod
    def resolve_locale(obj):
        return obj.locale_id

    @staticmethod
    def resolve_variant(obj):
        return obj.variant.sku if obj.variant_id else None


class ProductListSchema(Schema):
    id: str
    name: str
    sku: str
    description: Optional[str] = None
    price: float
    currency: str
    is_active: bool
    is_published: bool = False
    brand: Optional[str] = None
    family: Optional[str] = None

    @staticmethod
    def resolve_price(obj):
        return float(obj.list_price.amount)

    @staticmethod
    def resolve_currency(obj):
        return str(obj.list_price.currency)

    @staticmethod
    def resolve_brand(obj):
        return obj.brand.name if obj.brand_id else None

    @staticmethod
    def resolve_family(obj):
        return obj.family_id


class ProductDetailSchema(ProductListSchema):
    """Catalog product detail. NOTE: no stock_quantity — stock is WMS-owned
    and deliberately absent from the PIM surface (see api schemas for legacy)."""
    categories: List[ProductCategorySchema] = []
    values: List[AttributeValueSchema] = []
    variants: List[VariantSchema] = []
    media: List[MediaSchema] = []
    created_at: datetime = None
    updated_at: datetime = None

    @staticmethod
    def resolve_categories(obj):
        # Through rows carry is_primary; the raw M2M would lose it.
        return list(obj.category_links.all())


# Relations + completeness ----------------------------------------------------

class AssociationSchema(Schema):
    id: int
    to_product: str
    type: str

    @staticmethod
    def resolve_to_product(obj):
        return obj.to_product.sku


class ProductHistorySchema(Schema):
    history_id: int
    history_date: Optional[datetime] = None
    history_type: Optional[str] = None
    history_user_id: Optional[int] = None
    name: Optional[str] = None
    is_active: bool = False
    is_published: bool = False
    published_at: Optional[datetime] = None
    last_shipped_at: Optional[datetime] = None


class FeedSchema(Schema):
    id: int
    name: str
    channel: str
    locale: str
    format: str
    is_active: bool
    only_complete: bool = False
    schedule_cron: str = ''
    profile: Optional[int] = None
    profile_platform: Optional[str] = None

    @staticmethod
    def resolve_channel(obj):
        return obj.channel_id

    @staticmethod
    def resolve_locale(obj):
        return obj.locale_id

    @staticmethod
    def resolve_profile(obj):
        return obj.profile_id

    @staticmethod
    def resolve_profile_platform(obj):
        return obj.profile.platform if obj.profile_id else None


class ProfileSchema(Schema):
    id: int
    name: str
    platform: str
    channel: str
    is_active: bool

    @staticmethod
    def resolve_channel(obj):
        return obj.channel_id


class FeedRunSchema(Schema):
    id: int
    feed: int
    feed_name: str = None
    status: str
    items: int
    skipped: Dict[str, List[str]] = {}
    report: Dict[str, Any] = {}
    file: str = ''
    error: str = ''
    created_at: datetime = None

    @staticmethod
    def resolve_feed(obj):
        return obj.feed_id

    @staticmethod
    def resolve_feed_name(obj):
        return obj.feed.name


class CompletenessSchema(Schema):
    product: str
    channel: str
    locale: str
    family: Optional[str] = None
    percent: Optional[float] = None
    complete: bool = False
    missing: List[str] = []
    total_required: int = 0
