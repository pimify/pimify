# Python standard library imports
from datetime import date
from typing import List, Optional

# Third-party imports
from ninja import Schema

# Basic message schema
class Message(Schema):
    """Schema for simple message responses."""
    message: str

# Basic error schema
class Error(Schema):
    """Schema for simple error responses."""
    error: str


# Schema for organization details
class OrganizationDetailSchema(Schema):
    id: int
    name: str
    description: Optional[str] = None
    founded_date: Optional[date] = None
    email: Optional[str] = None
    phone_number: Optional[str] = None
    website: Optional[str] = None


# Product-related schemas
class ProductFilterSchema(Schema):
    """
    Schema for product filtering parameters.
    Supports filtering by active status, search term, and price range.
    """
    is_active: Optional[bool] = None
    search: Optional[str] = None
    min_price: Optional[float] = None
    max_price: Optional[float] = None


class ProductListSchema(Schema):
    """Schema for basic product information in list views."""
    id: str
    name: str
    sku: str
    description: Optional[str] = None
    price: float
    currency: str
    is_active: bool

    @staticmethod
    def resolve_price(obj):
        return float(obj.price.amount)
    
    @staticmethod
    def resolve_currency(obj):
        return str(obj.price.currency)


# Category schemas
class CategorySchema(Schema):
    """Schema for product categories."""
    id: str 
    name: str
    slug: str


# Supplier schemas
class SupplierListSchema(Schema):
    """Schema for basic supplier information in list views."""
    id: str
    name: str
    email: str


class SupplierInfoSchema(Schema):
    """Schema for detailed supplier information."""
    id: str
    name: str
    email: str
    phone: str
    address: str


# Warehouse schemas
class WarehouseListSchema(Schema):
    """Schema for basic warehouse information in list views."""
    id: str
    name: str


class WarehouseInfoSchema(Schema):
    """Schema for detailed warehouse information."""
    id: str
    name: str
    address: str


# Relationship schemas
class StockDetailSchema(Schema):
    """
    Schema for stock details.
    Represents the relationship between products and warehouses.
    """
    id: str
    product: ProductListSchema
    quantity: int
    warehouse: WarehouseInfoSchema


class PprductSupplierDetails(Schema):
    """
    Schema for product-supplier relationship details.
    Includes cost and lead time information.
    """
    id: str
    product: ProductListSchema
    supplier: SupplierInfoSchema
    cost_price: float
    lead_time: int
    