"""Custom admin template class coverage.

Incident: templates/admin/index.html used Tailwind `gray-*` utilities
(bg-gray-50, text-gray-900, dark:bg-gray-800 …) that Unfold's Tailwind v4
build does not ship — they only worked because a stale Tailwind v3
stylesheet was loaded via UNFOLD["STYLES"]. Removing that v3 build (it
conflicted with Unfold's v4 output) silently unstyled the dashboard.

Unfold ships ~400 `dark:` utilities, but all keyed to its own semantic
tokens (base-*/font-*/primary-*), never the Tailwind gray ramp. So this
test asserts every class literal in our templates actually exists in
Unfold's compiled CSS.
"""
import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

import unfold

# Django admin classes that live in django's own admin.css (Unfold ships its
# own stylesheet and does not style these) — exempt from the check.
DJANGO_ADMIN_CLASSES = {
    'addlink', 'changelink', 'deletelink', 'actionlist', 'module',
    'changeform', 'object-tools', 'submit-row',
}

_TEMPLATE_DIR = Path(settings.BASE_DIR).parent / 'templates'


def _unfold_css() -> str:
    path = Path(unfold.__file__).parent / 'static' / 'unfold' / 'css' / 'styles.css'
    return path.read_text(encoding='utf-8')


def _selector_for(cls: str) -> str:
    return '.' + ''.join('\\' + ch if ch in ':/.[]()%#,!' else ch for ch in cls)


def _classes_in_template(text: str):
    """Utility classes from class="..." literals, skipping template logic."""
    found = set()
    for chunk in re.findall(r'class="([^"]+)"', text):
        # Resolve conditional/loop fragments first: a class attribute may read
        # `{% if x %}addlink{% endif %} border ...`, and the tag bodies are
        # template logic, not class names.
        chunk = re.sub(r'{%.*?%}', ' ', chunk)
        chunk = re.sub(r'{{.*?}}', ' ', chunk)
        for token in chunk.split():
            if not token or token in DJANGO_ADMIN_CLASSES:
                continue
            found.add(token)
    return found


class AdminTemplateClassCoverageTest(SimpleTestCase):
    def test_custom_templates_only_use_classes_unfold_ships(self):
        css = _unfold_css()
        templates = sorted(_TEMPLATE_DIR.rglob('*.html'))
        self.assertTrue(templates, 'expected custom admin templates')
        missing = {}
        for path in templates:
            absent = sorted(
                cls for cls in _classes_in_template(path.read_text(encoding='utf-8'))
                if not re.search(re.escape(_selector_for(cls)) + r'(?![A-Za-z0-9_-])', css)
            )
            if absent:
                missing[str(path.relative_to(_TEMPLATE_DIR.parent))] = absent
        self.assertEqual(
            missing, {},
            'These classes are not in Unfold\'s Tailwind v4 build, so they will '
            'not be styled. Map them to Unfold tokens (base-*/font-*/primary-*) '
            f'or drop them: {missing}')

    def test_no_tailwind_v3_gray_ramp_in_custom_templates(self):
        # Unfold has no gray-* utilities; reintroducing them silently loses
        # styling (the reason the dashboard broke when the v3 CSS was removed).
        offenders = {}
        for path in sorted(_TEMPLATE_DIR.rglob('*.html')):
            hits = sorted(set(re.findall(r'(?:dark:)?(?:bg|text|border)-gray-\d+(?:/\d+)?',
                                         path.read_text(encoding='utf-8'))))
            if hits:
                offenders[str(path.relative_to(_TEMPLATE_DIR.parent))] = hits
        self.assertEqual(offenders, {}, f'Use Unfold base-*/font-* tokens: {offenders}')

    def test_tailwind_v4_artifact_is_not_loaded(self):
        self.assertNotIn(
            'STYLES', settings.UNFOLD,
            'Do not add a second Tailwind build alongside Unfold\'s v4 output.')
