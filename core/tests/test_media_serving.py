"""WhiteNoise media serving tests.

Phase 4 media hosting: product images are served from MEDIA_ROOT at
MEDIA_URL out of the box; S3 deployments serve from the bucket instead.
"""
import tempfile
from pathlib import Path

from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase, override_settings

from core.middleware import WhiteNoiseMediaMiddleware

_FALLBACK = HttpResponse('pass-through', status=404)


def _mw():
    return WhiteNoiseMediaMiddleware(lambda request: _FALLBACK)


class WhiteNoiseMediaTest(SimpleTestCase):
    def setUp(self):
        self.rf = RequestFactory()
        self._tmp = tempfile.TemporaryDirectory(prefix='pimify-media-')
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def _get(self, path):
        with override_settings(MEDIA_ROOT=str(self.root)):
            return _mw()(self.rf.get(path))

    def test_serves_file_under_media_prefix(self):
        (self.root / 'x.jpg').write_bytes(b'\xff\xd8fakejpeg')
        response = self._get('/media/x.jpg')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(b''.join(response.streaming_content), b'\xff\xd8fakejpeg')
        self.assertIn('image/jpeg', response['Content-Type'])

    def test_bare_path_not_served(self):
        # WhiteNoise 6.12 registers WHITENOISE_ROOT with NO prefix; this
        # middleware must serve at /media/*, never at the URL root.
        (self.root / 'x.jpg').write_bytes(b'\xff\xd8fakejpeg')
        response = self._get('/x.jpg')
        self.assertIs(response, _FALLBACK)

    def test_file_created_after_init_is_served(self):
        # Regression: with autorefresh off, WhiteNoise snapshots the dir at
        # startup and 404s anything uploaded later — media grows at runtime.
        middleware = None
        with override_settings(MEDIA_ROOT=str(self.root)):
            middleware = _mw()
        (self.root / 'late.jpg').write_bytes(b'\xff\xd8late')
        with override_settings(MEDIA_ROOT=str(self.root)):
            response = middleware(self.rf.get('/media/late.jpg'))
        self.assertEqual(response.status_code, 200)

    def test_media_url_override_respected(self):
        # Prefix follows settings: a deployment serving uploads under /assets/
        # gets them there, not hardcoded at /media/.
        (self.root / 'x.jpg').write_bytes(b'\xff\xd8fakejpeg')
        with override_settings(MEDIA_ROOT=str(self.root), MEDIA_URL='/assets/'):
            response = _mw()(self.rf.get('/assets/x.jpg'))
        self.assertEqual(response.status_code, 200)
        with override_settings(MEDIA_ROOT=str(self.root), MEDIA_URL='/assets/'):
            response = _mw()(self.rf.get('/media/x.jpg'))
        self.assertIs(response, _FALLBACK)

    def test_missing_file_passes_through(self):
        response = self._get('/media/nope.jpg')
        self.assertIs(response, _FALLBACK)

    def test_s3_backend_registers_nothing(self):
        from django.conf import settings
        (self.root / 'x.jpg').write_bytes(b'\xff\xd8fakejpeg')
        storages = {
            'staticfiles': settings.STORAGES['staticfiles'],
            'default': {
                'BACKEND': 'storages.backends.s3.S3Storage',
                'OPTIONS': {'bucket_name': 'b', 'querystring_auth': False},
            },
        }
        with override_settings(MEDIA_ROOT=str(self.root), STORAGES=storages):
            response = _mw()(self.rf.get('/media/x.jpg'))
        # File exists on local disk but the bucket serves it instead.
        self.assertIs(response, _FALLBACK)
