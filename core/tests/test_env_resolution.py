"""core/settings/env.py: per-environment resolution (.env.dev / .env.prod)."""
import importlib
import os
import tempfile
from pathlib import Path
from unittest import mock

from django.core.exceptions import ImproperlyConfigured
from django.test import TestCase

import core.settings.env as env_mod


def _write(directory, name, content):
    path = Path(directory) / name
    path.write_text(content)
    return str(path)


class EnvResolutionTest(TestCase):
    def _reload(self, environ):
        """Re-execute env.py under a fully controlled OS environment.

        The patch stays active for the whole test (stopped at cleanup):
        Config reads os.environ LIVE on every call, so asserting after the
        patch exits would read the real process env instead.
        """
        patcher = mock.patch.dict(os.environ, environ, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self._restore)
        importlib.reload(env_mod)

    def _restore(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            importlib.reload(env_mod)

    def test_dev_mode_selects_dev_file(self):
        with tempfile.TemporaryDirectory() as d:
            f = _write(d, ".env.dev", "DOMAIN=http://dev.local:8000\n")
            self._reload({"MODE": "development", "PIMIFY_ENV_FILE": f})
            self.assertEqual(env_mod.MODE, "development")
            self.assertEqual(env_mod.config("DOMAIN"), "http://dev.local:8000")

    def test_prod_mode_selects_prod_file(self):
        with tempfile.TemporaryDirectory() as d:
            f = _write(d, ".env.prod", "DOMAIN=https://shop.example.com\n")
            self._reload({"MODE": "production", "PIMIFY_ENV_FILE": f})
            self.assertEqual(env_mod.MODE, "production")
            self.assertEqual(env_mod.config("DOMAIN"), "https://shop.example.com")

    def test_dev_missing_file_falls_back_to_defaults(self):
        # Fresh clone, no .env.dev: must work with bare defaults, not crash.
        with tempfile.TemporaryDirectory() as d:
            missing = os.path.join(d, ".env.dev")
            self._reload({"MODE": "development", "PIMIFY_ENV_FILE": missing})
            self.assertEqual(env_mod.config("ANYTHING_UNSET", default="dflt"), "dflt")

    def test_prod_missing_file_refuses_to_boot(self):
        with tempfile.TemporaryDirectory() as d:
            missing = os.path.join(d, ".env.prod")
            with self.assertRaises(ImproperlyConfigured):
                self._reload({"MODE": "production", "PIMIFY_ENV_FILE": missing})

    def test_prod_missing_file_boots_on_environ_secret(self):
        # Container-style: --env-file provides values via the real
        # environment and no file exists. Must boot (guard still checks
        # the key); otherwise `docker run --env-file` could never work.
        # NOTE: PIMIFY_ENV_FILE deliberately UNSET here — an explicit
        # override pointing nowhere is a config error (tested above).
        # The patched environ wins over any real .env.prod on disk.
        self._reload({"MODE": "production", "SECRET_KEY": "e" * 64})
        self.assertEqual(env_mod.config("SECRET_KEY"), "e" * 64)

    def test_os_environ_wins_over_file(self):
        # docker run -e / systemd Environment= override file values.
        with tempfile.TemporaryDirectory() as d:
            f = _write(d, ".env.dev", "DOMAIN=http://file.example.com\n")
            self._reload({"MODE": "development", "PIMIFY_ENV_FILE": f,
                          "DOMAIN": "http://os.example.com"})
            self.assertEqual(env_mod.config("DOMAIN"), "http://os.example.com")

    def test_unknown_mode_refuses_to_boot(self):
        with self.assertRaises(ImproperlyConfigured):
            self._reload({"MODE": "staging"})

    def test_mode_defaults_to_development(self):
        self._reload({})
        self.assertEqual(env_mod.MODE, "development")


class ProductionSecretGuardTest(TestCase):
    def test_rejects_known_bad_and_short_keys(self):
        from core.settings.env import require_production_secret
        for bad in ["", "dummy_secret123", "change-me-to-a-strong-secret",
                    "secret_key", "x" * 31]:
            with self.assertRaises(ImproperlyConfigured, msg=f"accepted {bad!r}"):
                require_production_secret(bad)

    def test_accepts_long_random_key(self):
        from core.settings.env import require_production_secret
        key = "s" * 64
        self.assertEqual(require_production_secret(key), key)

    def test_production_settings_reject_dummy_secret(self):
        # End to end: a .env.prod carrying the public dev dummy must fail
        # a production boot. Import INSIDE assertRaises: executing
        # production.py is the thing that raises, and a stale sys.modules
        # entry would skip execution entirely.
        import sys
        with tempfile.TemporaryDirectory() as d:
            f = _write(d, ".env.prod",
                            "SECRET_KEY=dummy_secret123\n"
                            "DOMAIN=https://x.example.com\n")
            sys.modules.pop("core.settings.production", None)
            patcher = mock.patch.dict(
                os.environ, {"MODE": "production", "PIMIFY_ENV_FILE": f},
                clear=True)
            patcher.start()
            try:
                importlib.reload(env_mod)  # MODE=production, file present
                with self.assertRaises(ImproperlyConfigured):
                    import core.settings.production  # noqa: F401
            finally:
                sys.modules.pop("core.settings.production", None)
                patcher.stop()
                with mock.patch.dict(os.environ, {}, clear=True):
                    importlib.reload(env_mod)


class DockerIgnoreTest(TestCase):
    """Real per-env files must never bake into the image.

    Regression: .dockerignore listed only `.env`, which (fnmatch) matches
    just that literal file — a prod host building here would have leaked
    its live .env.prod SECRET_KEY into a layer.
    """

    def _ignored(self, filename):
        import fnmatch
        from pathlib import Path
        result = False
        for line in (Path(__file__).resolve().parent.parent.parent
                     / ".dockerignore").read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("!"):
                if fnmatch.fnmatch(filename, line[1:]):
                    result = False
            elif fnmatch.fnmatch(filename, line.rstrip("/")):
                result = True
        return result

    def test_real_env_files_excluded(self):
        self.assertTrue(self._ignored(".env"))
        self.assertTrue(self._ignored(".env.dev"))
        self.assertTrue(self._ignored(".env.prod"))

    def test_example_files_included(self):
        # The examples ship no secrets; excluding them would only confuse.
        self.assertFalse(self._ignored(".env.dev.example"))
        self.assertFalse(self._ignored(".env.prod.example"))
