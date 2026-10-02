from django.db.models import Count, Q


def dashboard_callback(request, context):
    from catalog.models import Attribute, Locale, Product

    # Navigation
    context['navigation'] = [
        {'title': 'API Docs', 'link': '/api/v1/docs', 'icon': 'link'},
    ]

    # KPI metrics — Phase 2.3: catalog metrics. Completeness % is the mean of
    # cached channel scores (the completeness endpoint is the only writer).
    total_products = Product.objects.count()
    active_products = Product.objects.filter(is_active=True).count()
    # A product has media if it owns any asset directly OR through a variant
    # (swatches, size-specific shots). Either side counts.
    missing_media = Product.objects.exclude(
        Q(media__isnull=False) | Q(variants__media__isnull=False)
    ).distinct().count()

    cached_scores = [
        pct
        for cache in Product.objects.values_list('completeness_cache', flat=True)
        for pct in (cache or {}).values()
    ]
    if cached_scores:
        completeness_metric = f"{sum(cached_scores) / len(cached_scores):.1f}%"
        completeness_footer = f"{len(cached_scores)} channel scores cached"
    else:
        completeness_metric = '—'
        completeness_footer = 'Open any product completeness endpoint to score'

    localizable_exists = Attribute.objects.filter(is_localizable=True).exists()
    active_locales = Locale.objects.filter(is_active=True).count()
    if localizable_exists and active_locales:
        # Products with no localized value at all (not merely ones that also
        # carry unscoped values).
        untranslated = Product.objects.exclude(values__locale__isnull=False).distinct().count()
        untranslated_footer = f"{active_locales} active locales"
    else:
        untranslated = '—'
        untranslated_footer = 'Configure locales + localizable attributes'

    context['kpi'] = [
        {
            'title': 'Total Products',
            'metric': total_products,
            'footer': f"{active_products} active products"
        },
        {
            'title': 'Catalog Completeness',
            'metric': completeness_metric,
            'footer': completeness_footer
        },
        {
            'title': 'Missing Media',
            'metric': missing_media,
            'footer': 'Products without images'
        },
        {
            'title': 'Untranslated',
            'metric': untranslated,
            'footer': untranslated_footer
        }
    ]

    # Progress metrics (catalog taxonomy)
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