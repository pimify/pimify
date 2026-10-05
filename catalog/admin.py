"""Phase 2.3: Unfold admin for the pure-PIM catalog.

House style follows api/admin.py (compressed fields, submit-on-filter,
import/export everywhere). Product change form groups inlines into tabs;
value rows adapt their widgets to the row's attribute type.
"""
from django import forms
from django.contrib import admin
from django.contrib.admin.widgets import AdminDateWidget
from django.db import models

from image_uploader_widget.widgets import ImageUploaderWidget
from import_export.admin import ImportExportModelAdmin
from simple_history.admin import SimpleHistoryAdmin
from unfold.admin import ModelAdmin, TabularInline
from unfold.contrib.filters.admin import (
    ChoicesDropdownFilter,
    RangeDateFilter,
)
from unfold.contrib.forms.widgets import WysiwygWidget
from unfold.contrib.import_export.forms import (
    ImportForm,
    SelectableFieldsExportForm,
)

from .models import (
    Attribute,
    AttributeGroup,
    AttributeOption,
    AttributeSet,
    AttributeTypes,
    Brand,
    Category,
    Channel,
    CompletenessRule,
    Feed,
    FeedRun,
    Locale,
    Product,
    ProductAssociation,
    ProductCategory,
    ProductMedia,
    ProductValue,
    ProductVariant,
    VariantValue,
)


# Value forms: widgets adapt to the row's attribute type ---------------------

class BaseValueForm(forms.ModelForm):
    """Conditionally adapts widgets/choices to the row's attribute type.

    Unvalidated (extra) rows fall back to generic widgets; model clean()
    still enforces the one-representation rule on save.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        attr = getattr(self.instance, 'attribute', None)
        if attr is None or attr.pk is None:
            return
        if 'option' in self.fields:
            self.fields['option'].queryset = attr.options.order_by('sort')
        column = {
            AttributeTypes.TEXT: 'value_text',
            AttributeTypes.TEXTAREA: 'value_text',
            AttributeTypes.URL: 'value_text',
            AttributeTypes.NUMBER: 'value_decimal',
            AttributeTypes.BOOLEAN: 'value_bool',
            AttributeTypes.DATE: 'value_date',
            AttributeTypes.SELECT: 'option',
            AttributeTypes.MULTISELECT: 'options',
            AttributeTypes.JSON: 'value_json',
        }[attr.type]
        if column == 'value_date':
            self.fields['value_date'].widget = AdminDateWidget()
        elif column == 'value_text' and attr.type == AttributeTypes.TEXTAREA:
            self.fields['value_text'].widget = forms.Textarea(attrs={'rows': 3})
        if column in self.fields:
            self.fields[column].help_text = (
                f"Value for '{attr.code}' ({attr.label}) — leave other value columns empty.")


class ProductValueForm(BaseValueForm):
    class Meta:
        model = ProductValue
        fields = '__all__'


class VariantValueForm(BaseValueForm):
    class Meta:
        model = VariantValue
        fields = '__all__'


# Inlines (tabbed on the product / variant change forms) ----------------------

class ProductCategoryInline(TabularInline):
    model = ProductCategory
    extra = 0
    tab = True
    autocomplete_fields = ['category']


class ProductValueInline(TabularInline):
    model = ProductValue
    form = ProductValueForm
    extra = 1
    tab = True
    per_page = 10
    autocomplete_fields = ['attribute']

    def get_queryset(self, request):
        # Deterministic order for paginated inline (model has no Meta.ordering).
        return super().get_queryset(request).order_by('attribute__code')


class ProductVariantInline(TabularInline):
    model = ProductVariant
    extra = 0
    tab = True
    per_page = 10
    show_change_link = True


class ProductMediaInline(TabularInline):
    model = ProductMedia
    extra = 0
    tab = True
    formfield_overrides = {
        models.ImageField: {'widget': ImageUploaderWidget}
    }


class VariantValueInline(TabularInline):
    model = VariantValue
    form = VariantValueForm
    extra = 1
    tab = True
    per_page = 10
    autocomplete_fields = ['attribute']

    def get_queryset(self, request):
        # Deterministic order for paginated inline (model has no Meta.ordering).
        return super().get_queryset(request).order_by('attribute__code')


class AttributeOptionInline(TabularInline):
    model = AttributeOption
    extra = 1
    tab = True


# Reference data ---------------------------------------------------------------

@admin.register(Locale)
class LocaleAdmin(ModelAdmin, ImportExportModelAdmin):
    compressed_fields = True
    list_display = ('code', 'name', 'is_active')
    list_filter = ('is_active',)
    search_fields = ['code', 'name']
    import_form_class = ImportForm
    export_form_class = SelectableFieldsExportForm


@admin.register(Channel)
class ChannelAdmin(ModelAdmin, ImportExportModelAdmin):
    compressed_fields = True
    warn_unsaved_form = True
    list_display = ('code', 'name', 'default_currency')
    search_fields = ['code', 'name']
    filter_horizontal = ('locales',)
    import_form_class = ImportForm
    export_form_class = SelectableFieldsExportForm


@admin.register(Brand)
class BrandAdmin(ModelAdmin, ImportExportModelAdmin):
    compressed_fields = True
    list_display = ('name', 'slug')
    search_fields = ['name', 'slug']
    import_form_class = ImportForm
    export_form_class = SelectableFieldsExportForm


@admin.register(AttributeGroup)
class AttributeGroupAdmin(ModelAdmin, ImportExportModelAdmin):
    compressed_fields = True
    list_display = ('code', 'name', 'sort')
    search_fields = ['code', 'name']
    import_form_class = ImportForm
    export_form_class = SelectableFieldsExportForm


@admin.register(Attribute)
class AttributeAdmin(ModelAdmin, ImportExportModelAdmin):
    compressed_fields = True
    warn_unsaved_form = True
    list_filter_submit = True
    list_display = ('code', 'label', 'type', 'group', 'is_variant_axis')
    list_filter = (
        ('type', ChoicesDropdownFilter),
        'is_variant_axis',
        'is_localizable',
        'is_channel_scoped',
    )
    search_fields = ['code', 'label']
    inlines = [AttributeOptionInline]
    import_form_class = ImportForm
    export_form_class = SelectableFieldsExportForm


@admin.register(AttributeSet)
class AttributeSetAdmin(ModelAdmin, ImportExportModelAdmin):
    compressed_fields = True
    warn_unsaved_form = True
    list_display = ('code', 'name')
    search_fields = ['code', 'name']
    filter_horizontal = ('groups', 'attributes')
    import_form_class = ImportForm
    export_form_class = SelectableFieldsExportForm


@admin.register(Category)
class CategoryAdmin(ModelAdmin, ImportExportModelAdmin):
    compressed_fields = True
    warn_unsaved_form = True
    list_filter_submit = True
    list_display = ('name', 'slug', 'kind', 'parent', 'sort')
    list_filter = (('kind', ChoicesDropdownFilter),)
    search_fields = ['name', 'slug']
    import_form_class = ImportForm
    export_form_class = SelectableFieldsExportForm


# Products ----------------------------------------------------------------------

@admin.register(Product)
class ProductAdmin(ModelAdmin, SimpleHistoryAdmin, ImportExportModelAdmin):
    """Catalog product studio: values, variants, media and categories as tabs."""
    compressed_fields = True
    warn_unsaved_form = True
    list_filter_submit = True
    list_display = ('sku', 'name', 'brand', 'family', 'list_price',
                    'is_active', 'is_published', 'updated_at')
    list_filter = (
        'is_active',
        'is_published',
        'family',
        'brand',
        ('created_at', RangeDateFilter),
    )
    search_fields = ['sku', 'name']
    actions = ['publish_selected', 'unpublish_selected']

    @admin.action(description='Publish selected (approve for feeds)')
    def publish_selected(self, request, queryset):
        # Per-object save (not queryset.update) so the publish event lands
        # in simple_history — the audit endpoint must show it.
        for product in queryset:
            product.is_published = True
            product.save(update_fields=['is_published'])

    @admin.action(description='Unpublish selected (hold back from feeds)')
    def unpublish_selected(self, request, queryset):
        for product in queryset:
            product.is_published = False
            product.save(update_fields=['is_published'])
    inlines = [
        ProductCategoryInline,
        ProductValueInline,
        ProductVariantInline,
        ProductMediaInline,
    ]
    import_form_class = ImportForm
    export_form_class = SelectableFieldsExportForm
    formfield_overrides = {
        models.TextField: {"widget": WysiwygWidget}
    }


@admin.register(ProductVariant)
class ProductVariantAdmin(ModelAdmin, SimpleHistoryAdmin, ImportExportModelAdmin):
    compressed_fields = True
    warn_unsaved_form = True
    list_filter_submit = True
    list_display = ('sku', 'product', 'is_default', 'sort')
    list_filter = ('is_default',)
    search_fields = ['sku']
    inlines = [VariantValueInline]
    import_form_class = ImportForm
    export_form_class = SelectableFieldsExportForm


@admin.register(ProductMedia)
class ProductMediaAdmin(ModelAdmin, ImportExportModelAdmin):
    compressed_fields = True
    warn_unsaved_form = True
    list_filter_submit = True
    list_display = ('id', 'product', 'variant', 'role', 'channel', 'locale')
    list_filter = (('role', ChoicesDropdownFilter),)
    search_fields = ['alt_text']
    import_form_class = ImportForm
    export_form_class = SelectableFieldsExportForm
    formfield_overrides = {
        models.ImageField: {'widget': ImageUploaderWidget}
    }


@admin.register(ProductAssociation)
class ProductAssociationAdmin(ModelAdmin, ImportExportModelAdmin):
    compressed_fields = True
    list_display = ('from_product', 'to_product', 'type')
    list_filter = (('type', ChoicesDropdownFilter),)
    search_fields = ['from_product__sku', 'to_product__sku']
    import_form_class = ImportForm
    export_form_class = SelectableFieldsExportForm


@admin.register(CompletenessRule)
class CompletenessRuleAdmin(ModelAdmin, ImportExportModelAdmin):
    compressed_fields = True
    warn_unsaved_form = True
    list_display = ('family', 'channel', 'locale')
    list_filter = ('channel', 'locale')
    filter_horizontal = ('required_attributes',)
    import_form_class = ImportForm
    export_form_class = SelectableFieldsExportForm


@admin.register(Feed)
class FeedAdmin(ModelAdmin, ImportExportModelAdmin):
    compressed_fields = True
    warn_unsaved_form = True
    list_display = ('name', 'channel', 'locale', 'format', 'is_active',
                    'only_complete', 'schedule_cron')
    list_filter = ('channel', 'locale', 'format', 'is_active')
    search_fields = ['name']
    import_form_class = ImportForm
    export_form_class = SelectableFieldsExportForm


@admin.register(FeedRun)
class FeedRunAdmin(ModelAdmin):
    """Append-only audit log: no add/change/delete through admin."""

    list_display = ('feed', 'created_at', 'status', 'items', 'file')
    list_filter = ('status', 'feed')
    readonly_fields = ('feed', 'status', 'items', 'skipped', 'file', 'error', 'created_at')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
