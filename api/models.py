# Standard library imports
import os
import secrets
import string
import time

# Django imports
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.signals import post_delete
from django.dispatch import receiver

# Third-party imports
from djmoney.models.fields import MoneyField
from fastnanoid import generate

# Custom utility functions
def generate_nanoid():
    """Generate a unique NanoID string of length 21."""
    return generate(size=21)


def generate_secure_api_key(prefix='sk', size=32):
    """
    Generate a highly secure API key combining NanoID with additional entropy.
    
    Args:
        prefix (str): Prefix for the API key (default: 'sk')
        size (int): Size of the NanoID component (default: 32)
    
    Returns:
        str: Format: prefix_timestamp_nanoid_entropy
    """
    timestamp = hex(int(time.time()))[2:]
    nano_component = generate(size=16)
    entropy_chars = string.ascii_letters + string.digits + '_-#@^!'
    entropy = ''.join(secrets.choice(entropy_chars) for _ in range(16))
    return f"{prefix}_{timestamp}_{nano_component}_{entropy}"


# Custom field types
class NanoIDField(models.CharField):
    """Custom field type that automatically generates a NanoID as the default value."""
    def __init__(self, *args, **kwargs):
        kwargs['max_length'] = kwargs.get('max_length', 21)
        kwargs['default'] = generate_nanoid
        kwargs['editable'] = False
        super().__init__(*args, **kwargs)


# Core models
class Product(models.Model):
    """
    Represents a product in the inventory system with pricing, stock, and category information.
    """
    id = NanoIDField(primary_key=True)
    name = models.CharField(max_length=100)
    sku = models.CharField(max_length=150, unique=True)
    description = models.TextField(blank=True, null=True)
    price = MoneyField(max_digits=14, decimal_places=2, default_currency='USD')
    is_active = models.BooleanField(default=False)
    categories = models.ManyToManyField('Category', related_name='products')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'Products'
        verbose_name_plural = 'Products'
        indexes = [
            models.Index(fields=['id']),
            models.Index(fields=['name']),
            models.Index(fields=['sku']),
        ]

    def __str__(self):
        return self.sku


class Category(models.Model):
    """
    Represents a product category for organizing products.
    """
    id = NanoIDField(primary_key=True)
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)

    class Meta:
        db_table = 'Categories'
        verbose_name_plural = 'Categories'
        indexes = [
            models.Index(fields=['id']),
            models.Index(fields=['name']),
        ]

    def __str__(self):
        return self.name


# NOTE (Phase 1.4 cutover, option A): Supplier, ProductSupplier, Warehouse and
# Stock were deleted from api state via SeparateDatabaseAndState (migration
# api.0003) — their TABLES stay intact for the unmanaged inventory/procurement
# mirrors. ProductImage stays: catalog backfill reads it on fresh installs.


class ProductImage(models.Model):
    """
    Stores product images with associated metadata.
    """
    id = models.AutoField(primary_key=True)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to='product_images/')
    alt_text = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        db_table = 'Product Images'
        verbose_name_plural = 'Product Images'

    def __str__(self):
        return str(self.id)


@receiver(post_delete, sender=ProductImage)
def delete_image_file(sender, instance, **kwargs):
    """Signal handler to clean up image files when a ProductImage instance is deleted."""
    if instance.image and os.path.isfile(instance.image.path):
        os.remove(instance.image.path)


class APIKey(models.Model):
    """
    Manages API authentication keys for external access to the system.
    """
    id = models.AutoField(primary_key=True)
    api_key = models.CharField(max_length=100, unique=True, editable=False)
    name = models.CharField(max_length=100)
    is_active = models.BooleanField(default=True)
    organization = models.ForeignKey(
        'Organization', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='api_keys',
        help_text="Owning organization (one org has many keys). Null = unassigned legacy key.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'API Keys'
        verbose_name_plural = 'API Keys'
        indexes = [
            models.Index(fields=['api_key'])
        ]

    def save(self, *args, **kwargs):
        """Generate a unique API key if one doesn't exist."""
        if not self.api_key:
            while True:
                generated_key = generate_secure_api_key()
                if not APIKey.objects.filter(api_key=generated_key).exists():
                    self.api_key = generated_key
                    break
        super().save(*args, **kwargs)

    def clean(self):
        """Ensure the API key has a name."""
        if not self.name:
            raise ValidationError({'name': 'Name is required'})

    def __str__(self):
        return f"{self.name} - {self.api_key[:12]}..."

    @classmethod
    def create_key(cls, name):
        """Helper method to create a new API key."""
        api_key = cls(name=name)
        api_key.full_clean()
        api_key.save()
        return api_key


class Organization(models.Model):
    """
    Stores organization details and their associated API keys.
    """
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, null=True)
    founded_date = models.DateField(blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    website = models.URLField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'Organization Details'
        verbose_name_plural = 'Organization Details'

    def __str__(self):
        return str(self.id)
        