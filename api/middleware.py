"""Phase 1 (pure-PIM pivot): deprecation headers for non-PIM endpoints.

The listed endpoints still work but are NOT part of the pure-PIM surface
(WMS/procurement/pricing-engine). They will be removed in a later phase
once consumers migrate. See TODO.md Phase 1.
"""

# Path prefixes (after domain) of deprecated endpoints. Matched with
# str.startswith, so both list and detail URLs are covered.
DEPRECATED_PREFIXES = (
    "/api/v1/private/suppliers",
    "/api/v1/private/warehouses",
    "/api/v1/private/stocks",
    "/api/v1/private/product-supplier",
    "/api/v1/public/exchange-rate",
    "/api/v1/public/convert-product-price",
)

# RFC 8594 Sunset: date after which these endpoints may be removed.
SUNSET_HTTP_DATE = "Thu, 01 Apr 2027 00:00:00 GMT"


class DeprecationMiddleware:
    """Adds Deprecation/Sunset headers to deprecated endpoint responses."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.path.startswith(DEPRECATED_PREFIXES):
            response["Deprecation"] = "true"
            response["Sunset"] = SUNSET_HTTP_DATE
        return response
