"""Phase 4.2: platform transforms over the generic feed payload.

Pure functions, zero network (file-artifact v1). Each transformer takes one
generic payload item (or the full payload) plus a PlatformProfile and returns
platform-shaped inputs plus a per-SKU report. Push (OAuth/SigV4/token
storage) is a later phase; the artifact's `report.notes` records what the
push implementation must still reconcile.
"""
from .shopify import transform_shopify

_TRANSFORMERS = {
    'shopify': transform_shopify,
}


def get_transformer(platform):
    """Transformer callable for a platform code; raises for unimplemented ones."""
    try:
        return _TRANSFORMERS[platform]
    except KeyError:
        raise ValueError(
            f'No transformer for platform {platform!r} yet '
            f'(implemented: {sorted(_TRANSFORMERS)}).') from None


def supported_platforms():
    return sorted(_TRANSFORMERS)
