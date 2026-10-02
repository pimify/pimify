import json
from django.db.models import Count
from datetime import timedelta
from django.utils import timezone


def dashboard_callback(request, context):
    from .models import Product, ProductImage

    # Navigation
    context['navigation'] = [
        {'title': 'API Docs', 'link': '/api/v1/docs', 'icon': 'link'},
    ]

    # Get date ranges for metrics
    today = timezone.now()
    last_7_days = today - timedelta(days=7)
    last_28_days = today - timedelta(days=28)
    last_month_start = (today.replace(day=1) - timedelta(days=1)).replace(day=1)
    this_month_start = today.replace(day=1)

    # KPI metrics — Phase 1 (pure-PIM pivot): WMS KPIs (stock value, low
    # stock) replaced with catalog stubs. Completeness % lands in Phase 2.
    total_products = Product.objects.count()
    active_products = Product.objects.filter(is_active=True).count()
    missing_media = Product.objects.filter(images__isnull=True).count()

    context['kpi'] = [
        {
            'title': 'Total Products',
            'metric': total_products,
            'footer': f"{active_products} active products"
        },
        {
            'title': 'Catalog Completeness',
            'metric': '—',
            'footer': 'Per-channel completeness lands in Phase 2'
        },
        {
            'title': 'Missing Media',
            'metric': missing_media,
            'footer': 'Products without images'
        }
    ]

    # Progress metrics
    category_distribution = Product.objects.values('categories__name').annotate(
        count=Count('id')
    ).order_by('-count')

    context['progress'] = [
        {
            'title': cat['categories__name'],
            'description': f"{cat['count']} products",
            'value': int((cat['count'] / total_products) * 100)
        } for cat in category_distribution[:8]
    ]

    return context