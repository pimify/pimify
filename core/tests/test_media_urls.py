"""Media storage selection tests (settings-level, no network).

Phase 4 media hosting: local dir by default; S3/MinIO when MEDIA_S3_BUCKET
is set; MEDIA_BASE_URL prefixes self-served files with your own origin.
decouple reads the environment at call time, so tests patch os.environ
around _media_storage() directly — no settings reload, no boto traffic.
"""
import os
from contextlib import contextmanager
from unittest import mock

from django.core.files.storage import FileSystemStorage
from django.test import SimpleTestCase

from catalog.platforms.base import is_absolute_url
from core.settings.base import _media_storage

_MEDIA_KEYS = (
    'MEDIA_S3_BUCKET', 'MEDIA_S3_PREFIX', 'MEDIA_S3_REGION',
    'MEDIA_S3_ENDPOINT_URL', 'MEDIA_S3_CUSTOM_DOMAIN',
    'MEDIA_S3_PUBLIC_READ', 'MEDIA_BASE_URL',
)


@contextmanager
def media_env(**overrides):
    """Clean slate for MEDIA_* env vars, then apply the case's values."""
    scrubbed = {key: None for key in _MEDIA_KEYS}
    scrubbed.update(overrides)
    present = {k: v for k, v in scrubbed.items() if v is not None}
    with mock.patch.dict(os.environ, present, clear=False):
        for key in _MEDIA_KEYS:
            if key not in present:
                os.environ.pop(key, None)
        yield


class MediaStorageTest(SimpleTestCase):
    def test_default_is_local_filesystem(self):
        with media_env():
            alias = _media_storage()
        self.assertEqual(
            alias['BACKEND'], 'django.core.files.storage.FileSystemStorage')
        storage = FileSystemStorage(**alias['OPTIONS'])
        self.assertEqual(
            storage.url('product_images/x.jpg'), '/media/product_images/x.jpg')

    def test_base_url_makes_absolute(self):
        with media_env(MEDIA_BASE_URL='https://pimify.example.com'):
            alias = _media_storage()
        storage = FileSystemStorage(**alias['OPTIONS'])
        url = storage.url('product_images/x.jpg')
        self.assertEqual(
            url, 'https://pimify.example.com/media/product_images/x.jpg')
        self.assertTrue(is_absolute_url(url))  # clears media_not_absolute

    def test_relative_url_is_not_absolute(self):
        with media_env():
            alias = _media_storage()
        url = FileSystemStorage(**alias['OPTIONS']).url('product_images/x.jpg')
        self.assertFalse(is_absolute_url(url))  # why the warning exists

    def test_s3_branch_unsigned_with_prefix(self):
        with media_env(MEDIA_S3_BUCKET='assets'):
            alias = _media_storage()
        self.assertEqual(alias['BACKEND'], 'storages.backends.s3.S3Storage')
        self.assertEqual(
            (alias['OPTIONS']['bucket_name'],
             alias['OPTIONS']['location'],
             alias['OPTIONS']['querystring_auth']),
            ('assets', 'media/', False))

    def test_s3_options_accepted_without_network(self):
        # Instantiation proves django-storages accepts every OPTION key we
        # emit (unknown kwargs raise); no request leaves the machine.
        from storages.backends.s3 import S3Storage
        with media_env(MEDIA_S3_BUCKET='assets',
                       MEDIA_S3_ENDPOINT_URL='http://minio:9000',
                       MEDIA_S3_REGION='us-east-1',
                       MEDIA_S3_CUSTOM_DOMAIN='cdn.example.com',
                       MEDIA_S3_PUBLIC_READ='true'):
            alias = _media_storage()
        storage = S3Storage(**alias['OPTIONS'])
        self.assertEqual(
            (storage.bucket_name, storage.endpoint_url,
             storage.custom_domain, storage.querystring_auth,
             storage.object_parameters),
            ('assets', 'http://minio:9000', 'cdn.example.com', False,
             {'ACL': 'public-read'}))

    def test_public_read_defaults_off(self):
        with media_env(MEDIA_S3_BUCKET='assets'):
            alias = _media_storage()
        self.assertNotIn('object_parameters', alias['OPTIONS'])
