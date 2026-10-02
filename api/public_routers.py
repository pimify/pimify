# Python standard library imports
from typing import List

# Django imports
from django.shortcuts import get_object_or_404
from django.db.models import Q

# Django Ninja imports
from ninja import Router, Query
from ninja.pagination import paginate, PageNumberPagination
from ninja.security import APIKeyHeader

# Djnago Money imports
from djmoney.contrib.exchange.models import Rate
from djmoney.contrib.exchange.models import convert_money

# Local imports
from .models import Product, ProductImage, Category, APIKey, Organization
from .schemas import (
    Message,
    Error,
    ProductListSchema,
    ProductInfoSchema,
    ProductImageSchema,
    CategorySchema,
    ProductFilterSchema,
    OrganizationDetailSchema,
    ExchangeRateResponseSchema,
    ProductPriceResponseSchema
)

# Initialize router
router = Router()

# Custom API Key authentication
class ApiKey(APIKeyHeader):
    """Custom API Key authentication using header."""
    param_name = "X-API-Key"

    def authenticate(self, request, key):
        """Validate API key against database."""
        try:
            return APIKey.objects.get(api_key=key)
        except APIKey.DoesNotExist:
            pass

# Initialize API key authentication
header_key = ApiKey()

# Health check endpoint
@router.get("/health",
            response={200: Message, 204: None}, 
            tags=["Product"])
def health_check(request):
    """Simple health check endpoint to verify API status."""
    return 200, {'message': 'success'}


# Retrieve organization details endpoint
@router.get("/organization",
            response={200: OrganizationDetailSchema, 404: Error},
            tags=["Organization"])
def get_organization_details(request):
    # Get organization from database
    organization = Organization.objects.first()

    if organization:
        return organization

    # Handle case when no organization is found
    return 404, {'error': 'Organization details not found'}


# Product endpoints
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
            | Q(description__icontains=filter_data.search)
        )

    # Price range filter — MoneyField amount column is `price`, so plain
    # numeric comparison is correct (verified against djmoney 3.6.1).
    if filter_data.min_price is not None or filter_data.max_price is not None:
        if filter_data.min_price is not None:
            products = products.filter(price__gte=filter_data.min_price)
        if filter_data.max_price is not None:
            products = products.filter(price__lte=filter_data.max_price)

    return products


@router.get("/products/{id}/", 
            auth=header_key, 
            response={200: ProductInfoSchema}, 
            tags=["Product"])
def retrieve_product(request, id: str):
    """Get detailed information about a specific product."""
    product = get_object_or_404(Product, id=id)
    return product


@router.get("/products/{id}/images/", 
            auth=header_key, 
            response={200: List[ProductImageSchema]}, 
            tags=["Product"])
def retrieve_product_images(request, id: str):
    """Get all images associated with a specific product."""
    product = get_object_or_404(Product, id=id)
    images = ProductImage.objects.filter(product=product)
    return images


# Category endpoints
@router.get("/categories/", 
            auth=header_key, 
            response={200: List[CategorySchema]}, 
            tags=["Product"])
@paginate(PageNumberPagination, page_size=20)
def list_categories(request):
    """Get paginated list of all product categories."""
    categories = Category.objects.all()
    return categories


@router.get("/categories/{category_id}/products/", 
            auth=header_key, 
            response={200: List[ProductListSchema]}, 
            tags=["Product"])
@paginate(PageNumberPagination, page_size=20)
def list_products_by_category(request, category_id: str):
    """Get paginated list of products in a specific category."""
    category = get_object_or_404(Category, id=category_id)
    products = Product.objects.filter(categories=category)
    return products


# Exchange rate endpoints
@router.get("/exchange-rate/",
            auth=header_key,
            response={200: ExchangeRateResponseSchema, 404: Error},
            tags=["Exchange Rate"])
def get_exchange_rate_only(request, to_currency: str, from_currency: str = "USD"):
    """
    Endpoint to fetch the exchange rate between two currencies.
    Default 'from_currency' is set to 'USD'.
    """
    rate = Rate.objects.filter(currency=to_currency).first()
    
    if rate:
        return {
            "rate": float(rate.value),
            "from_currency": from_currency,
            "to_currency": to_currency
        }
    return 404, {'error': f'Exchange rate for {to_currency} not found.'}


@router.get(
    "/convert-product-price/",
    auth=header_key,
    response={200: ProductPriceResponseSchema, 400: Error},
    tags=["Exchange Rate"]
)
def get_converted_product_price(request, product_sku: str, to_currency: str):
    """
    Endpoint to fetch product price in another currency.
    """
    # Fetch product or return 404 if not found
    product = get_object_or_404(Product, sku=product_sku)

    # Convert price
    try:
        converted_price = convert_money(product.price, to_currency)
    except Exception as e:
        return 400, {'error': f'Conversion failed: {str(e)}'}

    # Return response
    return {
        "product": product.name,
        "price": str(converted_price),
    }