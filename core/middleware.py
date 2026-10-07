"""WhiteNoise media serving (WhiteNoise 6.12 specifics).

WHITENOISE_ROOT alone cannot serve media correctly in 6.12:
  1. It is registered via add_files(root) with prefix=None, so files would
     be served at the URL root (/product_images/...) instead of /media/...
     (there is no WHITENOISE_PREFIX setting — only WHITENOISE_STATIC_PREFIX,
     which applies to STATIC_ROOT).
  2. `autorefresh` defaults to settings.DEBUG, so production would snapshot
     the directory at startup and 404 anything uploaded later.
  3. It must not register at all when media lives on S3 — the bucket/CDN
     serves then, and a local dir scan would be pointless.

This middleware registers MEDIA_ROOT under MEDIA_URL with autorefresh
forced on, and only when the default storage is local (no S3 in its
backend path) and the directory actually exists.
"""
from django.conf import settings as django_settings
from whitenoise.middleware import WhiteNoiseMiddleware


class WhiteNoiseMediaMiddleware(WhiteNoiseMiddleware):
    def __init__(self, get_response, settings=django_settings):
        super().__init__(get_response, settings)
        backend = str(
            getattr(settings, 'STORAGES', {})
            .get('default', {}).get('BACKEND', '')
        )
        root = getattr(settings, 'MEDIA_ROOT', None)
        # Autorefresh's add_files registers the directory without touching the
        # filesystem, so NO isdir guard here: requiring the dir to exist at
        # boot would make media silently unservable if the (volume-mounted)
        # directory isn't ready yet. S3 stays a no-op (bucket serves instead).
        if root and not backend.endswith('S3Storage'):
            # autorefresh: media grows at runtime (uploads), so re-stat on
            # each request instead of snapshotting at startup. Must be set
            # BEFORE add_files: it decides snapshot-vs-live internally.
            self.autorefresh = True
            prefix = getattr(settings, 'MEDIA_URL', None) or '/media/'
            self.add_files(root, prefix=prefix)
