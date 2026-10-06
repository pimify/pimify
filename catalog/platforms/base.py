"""Shared helpers for platform transformers."""

MAX_OPTIONS = 3


def money_str(amount, currency=None):
    """Shopify Money decimal string, always 2dp ("29.90", never "29.9").

    The live builder emits floats, so quantize — Decimal(str()) alone keeps
    trailing-zero loss (float 29.90 -> "29.9"). Currency is shop-level on
    Shopify, so it is not emitted per variant.
    """
    from decimal import Decimal, ROUND_HALF_UP
    return format(
        Decimal(str(amount)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP), 'f')


def humanize(code):
    """Attribute code -> option label ('material_type' -> 'Material Type')."""
    return code.replace('_', ' ').title()


def is_absolute_url(url):
    return isinstance(url, str) and url.startswith(('http://', 'https://'))
