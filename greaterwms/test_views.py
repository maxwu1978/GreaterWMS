from django.test import SimpleTestCase


class FrontendCacheHeaderTests(SimpleTestCase):
    def test_index_requires_revalidation(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Cache-Control'], 'no-cache, no-store, must-revalidate')

    def test_javascript_requires_revalidation(self):
        response = self.client.get('/js/app.d7882ceb.js')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Cache-Control'], 'no-cache, no-store, must-revalidate')
