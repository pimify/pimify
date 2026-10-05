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

# Local imports — NOTE (Phase 1.4 cutover, option A): Supplier,
# ProductSupplier, Warehouse and Stock were retired from api state (their
# tables live on via unmanaged mirrors). Product/Category/ProductImage stay
# as read-only legacy (catalog owns the write surface).
from .models import (
    Product,
    Category,
    ProductImage,
    Organization,
    APIKey
)


class LegacyReadOnlyMixin:
    """Makes a legacy api ModelAdmin view-only: the catalog app owns writes.

    Add is blocked, delete is blocked, and every field renders read-only, so
    the change form can display rows but never mutate them.
    """

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_readonly_fields(self, request, obj=None):
        return [f.name for f in self.model._meta.fields]

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
class ProductAdmin(LegacyReadOnlyMixin, ModelAdmin, ImportExportModelAdmin):
    """Legacy product admin — READ-ONLY (catalog owns the write surface)."""
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
class CategoryAdmin(LegacyReadOnlyMixin, ModelAdmin, ImportExportModelAdmin):
    """Legacy category admin — READ-ONLY (catalog owns the write surface)."""
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


@admin.register(ProductImage)
class ProductImageAdmin(LegacyReadOnlyMixin, ModelAdmin, ImportExportModelAdmin):
    """Legacy product-image admin — READ-ONLY (catalog media owns writes)."""
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


@admin.register(APIKey)
class APIKeyAdmin(ModelAdmin):
    """Admin interface for managing API keys."""
    compressed_fields = True
    warn_unsaved_form = True
    list_display = ('name', 'api_key', 'organization', 'is_active', 'created_at', 'updated_at')
    list_filter = (('name'), ('is_active'), ('organization'))
    search_fields = ['name']


@admin.register(Organization)
class OrganizationAdmin(ModelAdmin):
    """Admin interface for managing organization details."""
    compressed_fields = True
    warn_unsaved_form = True
    list_display = ('name', 'email', 'website', 'key_count', 'created_at', 'updated_at')
    list_filter = (('name'),)
    search_fields = ['name']

    @admin.display(description='API keys')
    def key_count(self, obj):
        return obj.api_keys.count()

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
