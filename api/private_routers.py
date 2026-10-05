# Python standard library imports
from typing import List

# Django imports
from django.shortcuts import get_object_or_404
from django.db.models import Q

# Django Ninja imports
from ninja import Router, Query
from ninja.security import django_auth
from ninja.pagination import paginate, PageNumberPagination

# Local imports — Phase 1.4 cutover: read-only unmanaged mirrors sharing the
# api tables (same columns, so response schemas resolve unchanged).
from inventory.models import Stock, Warehouse
from procurement.models import ProductSupplier, Supplier
from .schemas import (
    SupplierListSchema,
    SupplierInfoSchema,
    WarehouseListSchema,
    WarehouseInfoSchema,
    StockDetailSchema,
    PprductSupplierDetails
)

# Initialize router
router = Router()

# Supplier endpoints
@router.get("/suppliers/", 
            auth=django_auth, 
            response={200: List[SupplierListSchema]}, 
            tags=["Supplier"])
@paginate(PageNumberPagination, page_size=20)
def list_suppliers(request):
    """Get paginated list of all suppliers."""
    suppliers = Supplier.objects.all()
    return suppliers


@router.get("/suppliers/{id}", 
            auth=django_auth, 
            response={200: SupplierInfoSchema}, 
            tags=["Supplier"])
def get_supplier(request, id: str):
    """Get detailed information about a specific supplier."""
    supplier = get_object_or_404(Supplier, id=id)
    return supplier


# Warehouse endpoints
@router.get("/warehouses/", 
            auth=django_auth, 
            response={200: List[WarehouseListSchema]}, 
            tags=["Warehouse"])
@paginate(PageNumberPagination, page_size=20)
def list_warehouses(request):
    """Get paginated list of all warehouses."""
    warehouses = Warehouse.objects.all()
    return warehouses


@router.get("/warehouses/{id}", 
            auth=django_auth, 
            response={200: WarehouseInfoSchema}, 
            tags=["Warehouse"])
def get_warehouse(request, id: str):
    """Get detailed information about a specific warehouse."""
    warehouse = get_object_or_404(Warehouse, id=id)
    return warehouse


# Stock endpoints
@router.get("/stocks/", 
            auth=django_auth, 
            response={200: List[StockDetailSchema]}, 
            tags=["Stock [Product <=> Warehouse]"])
@paginate(PageNumberPagination, page_size=20)
def list_stock_details(request):
    """Get paginated list of all stock details across warehouses."""
    stocks = Stock.objects.all()
    return stocks


# Product Supplier endpoints
@router.get("/product-supplier/", 
            auth=django_auth, 
            response={200: List[PprductSupplierDetails]}, 
            tags=["Product <=> Supplier"])
@paginate(PageNumberPagination, page_size=20)
def list_product_supplier_details(request):
    """Get paginated list of all product-supplier relationships."""
    data = ProductSupplier.objects.all()
    return data