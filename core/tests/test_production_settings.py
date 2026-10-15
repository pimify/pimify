"""Production proxy settings: TRUST_PROXY_HEADERS / SECURE_HSTS_SECONDS wiring.

NOTE: core.settings.production is never imported at module level here.
Executing it requires a production-grade SECRET_KEY (the boot guard in
core/settings/env.py), which the test runner doesn't have — every test
(re)loads it under a controlled env via _reload() instead.
"""
import importlib
import os
import sys
from unittest import mock

from django.test import TestCase


class TrustProxyHeadersTest(TestCase):
    # importlib.reload re-executes in the SAME namespace, so conditionally
    # set names would leak between reloads without an explicit pop.
    _CONDITIONAL = ('SECURE_SSL_REDIRECT', 'SECURE_PROXY_SSL_HEADER')
    # NOTE: 64-char key — production refuses to boot on short/dummy
    # secrets (see core/settings/env.py), so tests must use a long one.
    _BASE_ENV = {"SECRET_KEY": "t" * 64, "DOMAIN": "https://x.example.com"}

    def _reload(self, env):
        with mock.patch.dict(os.environ, {**self._BASE_ENV, **env}, clear=False):
            import core.settings.production as prod  # first import runs here
            for attr in self._CONDITIONAL:
                prod.__dict__.pop(attr, None)
            importlib.reload(prod)
        self.addCleanup(self._restore)
        return prod

    def _restore(self):
        prod = sys.modules.get("core.settings.production")
        if prod is None:
            return
        for attr in self._CONDITIONAL:
            prod.__dict__.pop(attr, None)
        with mock.patch.dict(os.environ, self._BASE_ENV, clear=False):
            importlib.reload(prod)

    def test_trust_proxy_enables_redirect_and_header(self):
        prod = self._reload({"TRUST_PROXY_HEADERS": "True"})
        self.assertTrue(prod.SECURE_SSL_REDIRECT)
        self.assertEqual(prod.SECURE_PROXY_SSL_HEADER,
                         ('HTTP_X_FORWARDED_PROTO', 'https'))

    def test_direct_exposure_leaves_redirect_off(self):
        prod = self._reload({})  # default false: no proxy headers to trust
        self.assertFalse(getattr(prod, 'SECURE_SSL_REDIRECT', False))
        self.assertFalse(hasattr(prod, 'SECURE_PROXY_SSL_HEADER'))

    def test_hsts_seconds_env_settable(self):
        prod = self._reload({"SECURE_HSTS_SECONDS": "0"})
        self.assertEqual(prod.SECURE_HSTS_SECONDS, 0)
