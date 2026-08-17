from rest_framework.exceptions import APIException
from io import BytesIO
from zipfile import ZipFile

from django.test import TestCase

from utils.my_exceptions import custom_exception_handler


class ProductionSecurityTests(TestCase):
    def test_health_endpoint_is_public_and_checks_database(self):
        response = self.client.get('/health/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'status': 'ok'})
        self.assertEqual(response['Cache-Control'], 'no-store')

    def test_health_endpoint_rejects_non_get_requests(self):
        response = self.client.post('/health/', {})
        self.assertEqual(response.status_code, 405)

    def test_cli_install_manifest_is_public_and_machine_readable(self):
        response = self.client.get('/cli/install/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Cache-Control'], 'no-store')
        payload = response.json()
        self.assertEqual(payload['product'], 'GreaterWMS')
        self.assertEqual(payload['cli']['runtime']['node_min'], '18.0.0')
        self.assertEqual(payload['cli']['download_url'], 'https://api.maxsmartwms.online/cli/download/')
        self.assertEqual(
            payload['skills'][0]['download_url'],
            'https://api.maxsmartwms.online/skills/wms-email-intake-operator/download/',
        )
        self.assertIn('~/.codex/skills', payload['skills'][0]['install_commands'][0])
        self.assertIn('/staff/login/', [item['endpoint'] for item in payload['cli']['auth']])
        self.assertIn('GREATERWMS_CHECK_CODE', payload['cli']['auth'][1]['check_code_env'])
        serialized = response.content.decode('utf-8').lower()
        self.assertNotIn('password=', serialized)
        self.assertNotIn('token=', serialized)

    def test_cli_download_serves_only_the_cli_entrypoint(self):
        response = self.client.get('/cli/download/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Disposition'], 'attachment; filename="greaterwms.mjs"')
        self.assertEqual(response['Cache-Control'], 'no-store')
        self.assertIn(b'#!/usr/bin/env node', b''.join(response.streaming_content))

    def test_cli_download_rejects_non_get_requests(self):
        response = self.client.post('/cli/download/', {})
        self.assertEqual(response.status_code, 405)

    def test_email_intake_skill_download_contains_only_skill_bundle(self):
        response = self.client.get('/skills/wms-email-intake-operator/download/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response['Content-Disposition'],
            'attachment; filename="wms-email-intake-operator.zip"',
        )
        self.assertEqual(response['Cache-Control'], 'no-store')
        with ZipFile(BytesIO(response.content)) as bundle:
            self.assertEqual(
                sorted(bundle.namelist()),
                [
                    'wms-email-intake-operator/SKILL.md',
                    'wms-email-intake-operator/agents/openai.yaml',
                    'wms-email-intake-operator/references/document-mapping.md',
                ],
            )
            skill_text = bundle.read('wms-email-intake-operator/SKILL.md')
            self.assertIn(b'wms-email-intake-operator', skill_text)
            self.assertNotIn(b'Authorization: Bearer', skill_text)
            self.assertNotIn(b'SECRET_KEY=', skill_text)

    def test_email_intake_skill_download_rejects_non_get_requests(self):
        response = self.client.post('/skills/wms-email-intake-operator/download/', {})
        self.assertEqual(response.status_code, 405)

    def test_cli_install_manifest_rejects_non_get_requests(self):
        response = self.client.post('/cli/install/', {})
        self.assertEqual(response.status_code, 405)

    def test_login_rejects_get_without_debug_traceback(self):
        response = self.client.get('/login/')
        self.assertEqual(response.status_code, 405)
        self.assertNotIn(b'Traceback', response.content)
        self.assertNotIn(b'Django Version', response.content)

    def test_login_rejects_invalid_json(self):
        response = self.client.post(
            '/login/',
            data='{',
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)

    def test_api_requires_authentication(self):
        response = self.client.get('/staff/')
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()['status_code'], 401)

    def test_openapi_requires_authentication(self):
        response = self.client.get('/api/')
        self.assertEqual(response.status_code, 401)

    def test_api_exception_preserves_client_status(self):
        response = custom_exception_handler(
            APIException({'detail': 'Data exists'}),
            {'request': None},
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data['status_code'], 409)

    def test_security_headers_are_present(self):
        response = self.client.get('/health/')
        self.assertIn('Content-Security-Policy', response)
        self.assertIn('Permissions-Policy', response)
        self.assertEqual(response['X-Content-Type-Options'], 'nosniff')
        self.assertEqual(response['Referrer-Policy'], 'same-origin')
