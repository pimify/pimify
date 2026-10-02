# Standard library imports
# None required

# Django imports
from django.contrib.admin.views.decorators import staff_member_required

# Third-party imports
import orjson
from ninja import NinjaAPI
from ninja.parser import Parser
from ninja.renderers import BaseRenderer
from ninja.throttling import AnonRateThrottle, AuthRateThrottle

# Local imports
from .public_routers import router as public_router
from .private_routers import router as private_router
from catalog.routers import router as catalog_router


class ORJSONParser(Parser):
    """
    Custom parser that uses orjson for faster JSON parsing.
    orjson is a fast, correct JSON library for Python.
    It's significantly faster than Python's standard json module.
    """
    def parse_body(self, request):
        """
        Parse the request body using orjson.
        
        Args:
            request: The HTTP request object
            
        Returns:
            dict: Parsed JSON data
        """
        return orjson.loads(request.body)


class ORJSONRenderer(BaseRenderer):
    """
    Custom renderer that uses orjson for faster JSON serialization.
    Implements the BaseRenderer interface for Django Ninja.
    """
    media_type = "application/json"

    def render(self, request, data, *, response_status):
        """
        Serialize data to JSON using orjson.
        
        Args:
            request: The HTTP request object
            data: The data to be serialized
            response_status: HTTP response status code
            
        Returns:
            bytes: JSON-encoded data
        """
        return orjson.dumps(data)


# Initialize the Django Ninja API with custom configuration
app = NinjaAPI(
    # Use custom ORJSON parser and renderer for better performance
    parser=ORJSONParser(),
    renderer=ORJSONRenderer(),

    # Throttling public and private endpoints
    throttle=[
        AnonRateThrottle('10/s'),
        AuthRateThrottle('100/s'),
    ],
    
    # Restrict API documentation access to staff members only
    docs_decorator=staff_member_required,
    
    # API metadata
    title="Pimify",
    description="Pimify: Open-Source Product Information Management",
    version="v1"
)

# Register routers with their respective URL prefixes
app.add_router("public/", public_router)   # Public endpoints (legacy api models)
app.add_router("private/", private_router) # Private/authenticated endpoints (deprecated in Phase 1)
app.add_router("catalog/", catalog_router) # Phase 2: pure-PIM catalog surface