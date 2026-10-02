"""Shared API-key authentication (X-API-Key header -> api.APIKey row).

Single home for the auth object so api/ and catalog/ routers share one
mechanism. Moved here from api.public_routers during Phase 2.2 (no behavior
change).
"""
from ninja.security import APIKeyHeader

from .models import APIKey


class ApiKey(APIKeyHeader):
    """Custom API Key authentication using header."""
    param_name = "X-API-Key"

    def authenticate(self, request, key):
        """Validate API key against database. Deactivated keys are rejected."""
        try:
            return APIKey.objects.get(api_key=key, is_active=True)
        except APIKey.DoesNotExist:
            pass


# Shared instance used as `auth=header_key` on protected endpoints.
header_key = ApiKey()
