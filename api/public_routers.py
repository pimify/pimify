# Python standard library imports
from typing import List

# Django imports
from django.shortcuts import get_object_or_404
from django.db.models import Prefetch, Q

# Django Ninja imports
from ninja import Router, Query, Status
from ninja.pagination import paginate, PageNumberPagination

# Local imports
from .auth import header_key
from .models import Organization
from .schemas import (
    Message,
    Error,
    ProductFilterSchema,
    OrganizationDetailSchema
)

# Phase 1.4 cutover: public product surface now serves catalog models.
# Query params are unchanged (zero client breakage); shapes follow catalog
# schemas (notably: no stock_quantity — see catalog/schemas.py).
from catalog.models import (
    Category, Product, ProductCategory, ProductMedia, ProductValue, ProductVariant, VariantValue,
)
from catalog.routers import or_404
from catalog.schemas import (
    CategorySchema,
    MediaSchema,
    ProductDetailSchema,
    ProductListSchema,
)

# Initialize router
router = Router()

# Health check endpoint
@router.get("/health",
            response={200: Message, 204: None}, 
            tags=["Product"])
def health_check(request):
    """Simple health check endpoint to verify API status."""
    return 200, {'message': 'success'}


# Retrieve organization details endpoint
@router.get("/organization",
            auth=header_key,
            response={200: OrganizationDetailSchema, 404: Error},
            tags=["Organization"])
def get_organization_details(request):
    # Get organization from database
    organization = Organization.objects.first()

    if organization:
        return organization

    # Handle case when no organization is found
    return 404, {'error': 'Organization details not found'}


# Product endpoints (Phase 1.4: catalog-backed)
@router.get("/products/", 
            auth=header_key, 
            response={200: List[ProductListSchema]}, 
            tags=["Product"])
@paginate(PageNumberPagination, page_size=20)
def list_products(request, filter_data: ProductFilterSchema = Query(...)):
    """
    Get paginated list of products with optional filtering.
    Supports filtering by active status, price range, and search term.
    """
    # Base query with active status filter
    products = (Product.objects.filter(is_active=filter_data.is_active)
               if filter_data.is_active is not None
               else Product.objects.all())

    # Search filter — narrows the base queryset (previously discarded all
    # other filters and forced is_active=True).
    if filter_data.search:
        products = products.filter(
            Q(name__icontains=filter_data.search)
            | Q(sku__icontains=filter_data.search)
            | Q(description__icontains=filter_data.search)
        )

    # Price range filter on list_price amount (MoneyField amount column).
    if filter_data.min_price is not None or filter_data.max_price is not None:
        if filter_data.min_price is not None:
            products = products.filter(list_price__gte=filter_data.min_price)
        if filter_data.max_price is not None:
            products = products.filter(list_price__lte=filter_data.max_price)

    return products


@router.get("/products/{id}/", 
            auth=header_key, 
            response={200: ProductDetailSchema, 404: Error}, 
            tags=["Product"])
def retrieve_product(request, id: str):
    """Get detailed information about a specific product."""
    return or_404(
        lambda: get_object_or_404(
            Product.objects.select_related('family', 'brand').prefetch_related(
                Prefetch('category_links',
                         queryset=ProductCategory.objects.select_related('category')),
                Prefetch('values',
                         queryset=ProductValue.objects.select_related(
                             'attribute', 'option', 'channel', 'locale'
                         ).prefetch_related('options').order_by('attribute__code')),
                Prefetch('variants',
                         queryset=ProductVariant.objects.prefetch_related(
                             Prefetch('values',
                                      queryset=VariantValue.objects.select_related(
                                          'attribute', 'option', 'channel', 'locale'
                                      ).prefetch_related('options').order_by('attribute__code'))
                         ).order_by('sort')),
                Prefetch('media',
                         queryset=ProductMedia.objects.select_related(
                             'variant', 'channel', 'locale').order_by('sort')),
            ),
            id=id,
        ),
        f'Product {id} not found.')


@router.get("/products/{id}/images/", 
            auth=header_key, 
            response={200: List[MediaSchema], 404: Error}, 
            tags=["Product"])
def retrieve_product_images(request, id: str):
    """Get all media associated with a specific product (incl. variant rows)."""
    product = or_404(
        lambda: get_object_or_404(Product, id=id), f'Product {id} not found.')
    if isinstance(product, Status):
        return product
    return (ProductMedia.objects
            .filter(Q(product=product) | Q(variant__product=product))
            .select_related('variant', 'channel', 'locale').order_by('sort'))


# Category endpoints
@router.get("/categories/", 
            auth=header_key, 
            response={200: List[CategorySchema]}, 
            tags=["Product"])
@paginate(PageNumberPagination, page_size=20)
def list_categories(request):
    """Get paginated list of all product categories."""
    categories = Category.objects.order_by('sort', 'name')
    return categories


@router.get("/categories/{category_id}/products/", 
            auth=header_key, 
            response={200: List[ProductListSchema]}, 
            tags=["Product"])
@paginate(PageNumberPagination, page_size=20)
def list_products_by_category(request, category_id: str):
    """Get paginated list of products in a specific category."""
    # NOTE: bare get_object_or_404 (legacy {"detail"} 404 shape) is deliberate:
    # @paginate cannot return non-200 statuses (proven in Phase 2.2), so the
    # catalog-style {"error"} envelope can't apply to this paginated endpoint.
    category = get_object_or_404(Category, id=category_id)
    products = Product.objects.filter(categories=category)
    return products