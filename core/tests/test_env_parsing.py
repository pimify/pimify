"""Env parsing hardening (the .env inline-comment incident).

python-decouple does NOT strip inline comments: a line like
`MEDIA_S3_ENDPOINT_URL=  # set for MinIO` yields the literal
'# set for MinIO', which used to become a live endpoint URL (silent
corruption) or crash settings import for booleans. _env_str/_env_bool
neutralize that shape; .env.example keeps notes on their own lines.
"""
import os
from contextlib import contextmanager
from unittest import mock

from django.test import SimpleTestCase

from core.settings.base import _dbbackup_storage, _env_bool, _env_str, _media_storage


@contextmanager
def patched_env(**overrides):
    present = {k: v for k, v in overrides.items() if v is not None}
    absent = [k for k, v in overrides.items() if v is None]
    with mock.patch.dict(os.environ, present, clear=False):
        for key in absent:
            os.environ.pop(key, None)
        yield


class EnvStrTest(SimpleTestCase):
    def test_comment_value_becomes_empty(self):
        with patched_env(ZZ_X='  # set for MinIO / S3-compatible APIs'):
            self.assertEqual(_env_str('ZZ_X'), '')

    def test_plain_value_untouched(self):
        with patched_env(ZZ_X='http://minio:9000'):
            self.assertEqual(_env_str('ZZ_X'), 'http://minio:9000')

    def test_fragment_without_space_survives(self):
        with patched_env(ZZ_X='https://host/p#frag'):
            self.assertEqual(_env_str('ZZ_X'), 'https://host/p#frag')

    def test_absent_yields_default(self):
        with patched_env(ZZ_X=None):
            self.assertEqual(_env_str('ZZ_X', default='dflt'), 'dflt')


class EnvBoolTest(SimpleTestCase):
    def test_commented_false_is_false_not_crash(self):
        # This exact value used to raise ValueError and kill settings import.
        with patched_env(ZZ_B='false  # set true to add ACL public-read on upload'):
            self.assertIs(_env_bool('ZZ_B'), False)

    def test_true_variants(self):
        for raw in ('true', 'True', '1', 'yes', 'on', 'true  # note'):
            with patched_env(ZZ_B=raw):
                self.assertIs(_env_bool('ZZ_B'), True, raw)

    def test_false_variants(self):
        for raw in ('false', 'False', '0', 'no', 'off', ''):
            with patched_env(ZZ_B=raw):
                self.assertIs(_env_bool('ZZ_B'), False, repr(raw))

    def test_absent_yields_default(self):
        with patched_env(ZZ_B=None):
            self.assertIs(_env_bool('ZZ_B'), False)
            self.assertIs(_env_bool('ZZ_B', default=True), True)

    def test_junk_warns_and_falls_back(self):
        with patched_env(ZZ_B='maybe'):
            with self.assertWarns(UserWarning):
                self.assertIs(_env_bool('ZZ_B'), False)


class CommentedStorageTest(SimpleTestCase):
    def test_commented_media_endpoint_omitted(self):
        env = {'MEDIA_S3_BUCKET': 'assets',
               'MEDIA_S3_ENDPOINT_URL': '  # set for MinIO / S3-compatible APIs',
               'MEDIA_S3_PREFIX': None, 'MEDIA_S3_REGION': None,
               'MEDIA_S3_CUSTOM_DOMAIN': None, 'MEDIA_S3_PUBLIC_READ': None,
               'MEDIA_BASE_URL': None}
        with patched_env(**env):
            alias = _media_storage()
        self.assertNotIn('endpoint_url', alias['OPTIONS'])
        self.assertEqual(alias['OPTIONS']['bucket_name'], 'assets')

    def test_commented_backup_endpoint_omitted(self):
        env = {'DBBACKUP_S3_BUCKET': 'bk',
               'DBBACKUP_S3_ENDPOINT_URL': '  # set for MinIO / S3-compatible APIs',
               'DBBACKUP_S3_PREFIX': None, 'DBBACKUP_S3_REGION': None}
        with patched_env(**env):
            alias = _dbbackup_storage()
        self.assertNotIn('endpoint_url', alias['OPTIONS'])
        self.assertEqual(alias['OPTIONS']['bucket_name'], 'bk')
