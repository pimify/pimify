# Django core imports
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.admin import GroupAdmin as BaseGroupAdmin
from django.contrib.auth.models import User, Group
from django.db import models

# Third-party imports
from unfold.admin import ModelAdmin
from unfold.forms import (
    UserChangeForm,
    UserCreationForm,
    AdminPasswordChangeForm
)
from unfold.contrib.import_export.forms import (
    ExportForm,
    ImportForm,
    SelectableFieldsExportForm
)
from unfold.contrib.filters.admin import (
    FieldTextFilter,
    ChoicesDropdownFilter,
    RangeDateFilter
)
from unfold.contrib.forms.widgets import WysiwygWidget
from import_export.admin import ImportExportModelAdmin, ExportMixin
from image_uploader_widget.widgets import ImageUploaderWidget
from login_history.models import LoginHistory
from django_apscheduler.models import DjangoJob, DjangoJobExecution

# Local imports
from .models import (
    Product,
    Category,
    Supplier,
    ProductSupplier,
    ProductImage,
    Warehouse,
    Stock,
    Organization,
    APIKey
)

# Unregister default admin models to customize them
admin.site.unregister(User)
admin.site.unregister(Group)
admin.site.unregister(LoginHistory)
admin.site.unregister(DjangoJob)
admin.site.unregister(DjangoJobExecution)
admin.site.site_url = None


@admin.register(LoginHistory)
class LoginHistoryAdmin(ExportMixin, ModelAdmin):
    """Admin interface for login history tracking."""
    list_display = ('user', 'date_time', 'ip', 'user_agent', 'is_logged_in')
    export_form_class = SelectableFieldsExportForm

    def has_add_permission(self, request):
        """Prevent manual creation of login history records."""
        return False


@admin.register(DjangoJob)
class DjangoJobAdmin(ExportMixin, ModelAdmin):
    """Custom admin interface for Job Scheduler model with Unfold theme integration."""
    compressed_fields = True

@admin.register(DjangoJobExecution)
class DjangoJobExecutionAdmin(ExportMixin, ModelAdmin):
    """Custom admin interface for Job Execution model with Unfold theme integration."""
    compressed_fields = True

    def has_add_permission(self, request):
        """Prevent manual creation of login history records."""
        return False


@admin.register(User)
class UserAdmin(BaseUserAdmin, ModelAdmin):
    """Custom admin interface for User model with Unfold theme integration."""
    compressed_fields = True
    form = UserChangeForm
    add_form = UserCreationForm
    change_password_form = AdminPasswordChangeForm


@admin.register(Group)
class GroupAdmin(BaseGroupAdmin, ModelAdmin):
    """Custom admin interface for Group model with Unfold theme integration."""
    compressed_fields = True


@admin.register(Product)
class ProductAdmin(ModelAdmin, ImportExportModelAdmin):
    """Admin interface for managing products with import/export functionality."""
    compressed_fields = True
    warn_unsaved_form = True
    list_filter_submit = True
    list_display = ('sku', 'name', 'price', 'is_active', 'created_at', 'updated_at')
    list_filter = (
        ('name', ChoicesDropdownFilter),
        ('sku', FieldTextFilter),
        'is_active',
        ('categories', ChoicesDropdownFilter),
        ('created_at', RangeDateFilter)
    )
    search_fields = ['name', 'sku', 'categories']

    # Import/Export configuration
    import_form_class = ImportForm
    export_form_class = SelectableFieldsExportForm

    # Use WYSIWYG editor for text fields
    formfield_overrides = {
        models.TextField: {"widget": WysiwygWidget}
    }


@admin.register(Category)
class CategoryAdmin(ModelAdmin, ImportExportModelAdmin):
    """Admin interface for managing product categories."""
    compressed_fields = True
    warn_unsaved_form = True
    list_filter_submit = True
    list_display = ('name', 'slug')
    list_filter = (
        ('name', ChoicesDropdownFilter),
        ('slug', ChoicesDropdownFilter)
    )
    search_fields = ['name']

    # Import/Export configuration
    import_form_class = ImportForm
    export_form_class = SelectableFieldsExportForm


@admin.register(Supplier)
class SupplierAdmin(ModelAdmin, ImportExportModelAdmin):
    """Admin interface for managing suppliers."""
    compressed_fields = True
    warn_unsaved_form = True
    list_filter_submit = True
    list_display = ('name', 'email', 'phone')
    list_filter = (('name', ChoicesDropdownFilter),)
    search_fields = ['name', 'email']

    # Import/Export configuration
    import_form_class = ImportForm
    export_form_class = SelectableFieldsExportForm

    # Use WYSIWYG editor for text fields
    formfield_overrides = {
        models.TextField: {"widget": WysiwygWidget}
    }


@admin.register(ProductSupplier)
class ProductSupplierAdmin(ModelAdmin, ImportExportModelAdmin):
    """Admin interface for managing product-supplier relationships."""
    compressed_fields = True
    warn_unsaved_form = True
    list_filter_submit = True
    list_display = ('product', 'supplier', 'cost_price', 'lead_time')
    list_filter = (
        ('product', ChoicesDropdownFilter),
        ('supplier', ChoicesDropdownFilter)
    )
    search_fields = ['product', 'supplier']

    # Import/Export configuration
    import_form_class = ImportForm
    export_form_class = SelectableFieldsExportForm


@admin.register(ProductImage)
class ProductImageAdmin(ModelAdmin, ImportExportModelAdmin):
    """Admin interface for managing product images."""
    compressed_fields = True
    warn_unsaved_form = True
    list_filter_submit = True
    list_display = ('product', 'image')
    list_filter = (('product', ChoicesDropdownFilter),)
    search_fields = ['product']

    # Import/Export configuration
    import_form_class = ImportForm
    export_form_class = SelectableFieldsExportForm

    # Use image uploader widget for image fields
    formfield_overrides = {
        models.ImageField: {'widget': ImageUploaderWidget}
    }


@admin.register(Warehouse)
class WarehouseAdmin(ModelAdmin, ImportExportModelAdmin):
    """Admin interface for managing warehouses."""
    compressed_fields = True
    warn_unsaved_form = True
    list_filter_submit = True
    list_display = ('name',)
    list_filter = (('name', ChoicesDropdownFilter),)
    search_fields = ['name']

    # Import/Export configuration
    import_form_class = ImportForm
    export_form_class = SelectableFieldsExportForm

    # Use WYSIWYG editor for text fields
    formfield_overrides = {
        models.TextField: {"widget": WysiwygWidget}
    }


@admin.register(Stock)
class StockAdmin(ModelAdmin, ImportExportModelAdmin):
    """Admin interface for managing product stock levels."""
    compressed_fields = True
    warn_unsaved_form = True
    list_filter_submit = True
    list_display = ('product', 'quantity', 'warehouse')
    list_filter = (('product', ChoicesDropdownFilter),)
    search_fields = ['product']

    # Import/Export configuration
    import_form_class = ImportForm
    export_form_class = SelectableFieldsExportForm


@admin.register(APIKey)
class APIKeyAdmin(ModelAdmin):
    """Admin interface for managing API keys."""
    compressed_fields = True
    warn_unsaved_form = True
    list_display = ('name', 'api_key', 'is_active', 'created_at', 'updated_at')
    list_filter = (('name'), ('is_active'))
    search_fields = ['name']


@admin.register(Organization)
class OrganizationAdmin(ModelAdmin):
    """Admin interface for managing organization details."""
    compressed_fields = True
    warn_unsaved_form = True
    list_display = ('name', 'email', 'website', 'api_keys', 'created_at', 'updated_at')
    list_filter = (('name'),)
    search_fields = ['name']

    # Use WYSIWYG editor for text fields
    formfield_overrides = {
        models.TextField: {"widget": WysiwygWidget}
    }

    def has_add_permission(self, request):
        # Disallow adding if at least one Organization instance exists
        if Organization.objects.exists():
            return False
        return super().has_add_permission(request)

    def has_delete_permission(self, request, obj=None):
        # Optionally disable delete permission to keep the single instance
        return False
