import brotli

class BrotliMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        # Check if client accepts brotli compression
        if 'br' not in request.META.get('HTTP_ACCEPT_ENCODING', ''):
            return response

        # Streaming responses (WhiteNoise static files, FileResponse
        # downloads) have no .content — touching it raises AttributeError
        # and 500s the response. Never compress those.
        if response.streaming:
            return response

        # Don't compress errors/redirects (and never an empty body).
        if response.status_code != 200 or not response.content:
            return response

        # Don't compress if response is already compressed
        if response.has_header('Content-Encoding'):
            return response

        # Only compress text responses
        if not response.get('Content-Type', '').startswith(('text/', 'application/json')):
            return response

        # Compress content
        compressed_content = brotli.compress(response.content)
        response.content = compressed_content
        response['Content-Length'] = str(len(compressed_content))
        response['Content-Encoding'] = 'br'

        return response