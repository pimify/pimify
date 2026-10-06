"""UNFOLD settings regression tests.

Incident: UNFOLD["COLORS"] used Tailwind v3 triplet syntax ("75 85 99").
Unfold emits each value verbatim as `--color-<group>-<key>: <value>` and its
Tailwind v4 build consumes it directly as a color (no rgb() wrapper), so every
triplet shipped as an invalid color and all themed utilities silently fell
back to inherited color — an admin that renders, but looks wrong.
"""
import re

from django.conf import settings
from django.test import SimpleTestCase

# A complete CSS color: hex, functional notation, or another custom property.
_VALID_COLOR = re.compile(
    r'^(#\w{3,8}'
    r'|rgba?\([^)]*\)'
    r'|hsla?\([^)]*\)'
    r'|oklch\([^)]*\)'
    r'|oklab\([^)]*\)'
    r'|color\([^)]*\)'
    r'|lab\([^)]*\)'
    r'|lch\([^)]*\)'
    r'|var\(--[\w-]+\))$'
)
# Tailwind v3 triplet syntax that broke under v4.
_V3_TRIPLET = re.compile(r'^\d{1,3} \d{1,3} \d{1,3}$')


def _leaves(mapping, path='UNFOLD["COLORS"]'):
    for key, value in mapping.items():
        if isinstance(value, dict):
            yield from _leaves(value, f'{path}["{key}"]')
        else:
            yield f'{path}["{key}"]', value


class UnfoldColorsTest(SimpleTestCase):
    def test_no_v3_triplet_values(self):
        offenders = [where for where, v in _leaves(settings.UNFOLD['COLORS'])
                     if isinstance(v, str) and _V3_TRIPLET.match(v.strip())]
        self.assertEqual(
            offenders, [],
            'Tailwind v3 triplets are invalid under Unfold/Tailwind v4 — wrap '
            f'them in rgb(): {offenders}')

    def test_all_values_are_complete_colors(self):
        offenders = [f'{where}={v!r}' for where, v in _leaves(settings.UNFOLD['COLORS'])
                     if not (isinstance(v, str) and _VALID_COLOR.match(v.strip()))]
        self.assertEqual(
            offenders, [],
            'Unfold emits COLORS values verbatim into --color-* variables, so '
            f'each must be a complete CSS color: {offenders}')

    def test_font_and_primary_groups_present(self):
        colors = settings.UNFOLD['COLORS']
        self.assertIn('font', colors)
        self.assertIn('primary', colors)
        for key in ('subtle-light', 'default-light', 'important-light'):
            self.assertIn(key, colors['font'])

    def test_primary_500_is_valid(self):
        # Guards the one value used for buttons/links/active sidebar item.
        self.assertEqual(settings.UNFOLD['COLORS']['primary']['500'], 'rgb(245 121 0)')


class UnfoldStaticFilesTest(SimpleTestCase):
    def test_no_custom_stylesheet_registered(self):
        # A second Tailwind build (v3) previously fought Unfold's v4 output.
        self.assertNotIn('STYLES', settings.UNFOLD)

    def test_unfold_before_django_admin(self):
        apps = list(settings.INSTALLED_APPS)
        self.assertLess(apps.index('unfold'), apps.index('django.contrib.admin'))
