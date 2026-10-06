"""BrotliMiddleware regression tests.

Incident: the middleware touched response.content unconditionally, which
raises AttributeError on streaming responses (WhiteNoise static files,
FileResponse downloads) and 500'd every /static/* request — unstyled admin.
"""
import brotli
import io

from django.http import FileResponse, HttpResponse
from django.test import RequestFactory, SimpleTestCase

from core.compressor.middleware import BrotliMiddleware


def _mw(response):
    return BrotliMiddleware(lambda request: response)


class BrotliMiddlewareTest(SimpleTestCase):
    def setUp(self):
        self.rf = RequestFactory(HTTP_ACCEPT_ENCODING='gzip, br')

    def test_html_compressed_when_accepted(self):
        resp = _mw(HttpResponse('<html>x</html>', content_type='text/html'))(
            self.rf.get('/'))
        self.assertEqual(resp['Content-Encoding'], 'br')
        self.assertEqual(brotli.decompress(resp.content), b'<html>x</html>')

    def test_no_accept_encoding_passthrough(self):
        resp = _mw(HttpResponse('<html>x</html>', content_type='text/html'))(
            self.rf.get('/', HTTP_ACCEPT_ENCODING='gzip'))
        self.assertFalse(resp.has_header('Content-Encoding'))

    def test_streaming_response_untouched(self):
        inner = FileResponse(io.BytesIO(b'x'), content_type='text/css')
        resp = _mw(inner)(self.rf.get('/static/unfold/css/styles.css'))
        self.assertIs(resp, inner)
        self.assertFalse(resp.has_header('Content-Encoding'))
        self.assertEqual(b''.join(resp.streaming_content), b'x')

    def test_non_200_untouched(self):
        resp = _mw(HttpResponse('nope', status=404, content_type='text/html'))(
            self.rf.get('/'))
        self.assertFalse(resp.has_header('Content-Encoding'))

    def test_empty_body_untouched(self):
        resp = _mw(HttpResponse('', content_type='text/html'))(self.rf.get('/'))
        self.assertFalse(resp.has_header('Content-Encoding'))

    def test_non_text_untouched(self):
        resp = _mw(HttpResponse(b'\x89PNG', content_type='image/png'))(
            self.rf.get('/'))
        self.assertFalse(resp.has_header('Content-Encoding'))

    def test_already_encoded_untouched(self):
        inner = HttpResponse('x', content_type='text/html')
        inner['Content-Encoding'] = 'gzip'
        resp = _mw(inner)(self.rf.get('/'))
        self.assertEqual(resp['Content-Encoding'], 'gzip')
