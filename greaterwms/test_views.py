import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase


def current_app_js_path():
    index_path = Path(settings.BASE_DIR) / 'templates' / 'dist' / 'spa' / 'index.html'
    match = re.search(r'src=js/(app\.[^"]+\.js)', index_path.read_text())
    if not match:
        raise AssertionError('Could not find the current app bundle in index.html')
    return '/js/' + match.group(1)


class FrontendCacheHeaderTests(SimpleTestCase):
    def test_index_requires_revalidation(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Cache-Control'], 'no-cache, no-store, must-revalidate')

    def test_javascript_requires_revalidation(self):
        response = self.client.get(current_app_js_path())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Cache-Control'], 'no-cache, no-store, must-revalidate')
