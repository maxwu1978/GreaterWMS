from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

from staff.auth import issue_session_token
from staff.models import ListModel as Staff
from userprofile.models import Users


class RoleAuthorizationTests(TestCase):
    def setUp(self):
        self.tenant_openid = 'tenant-role-test'
        self.admin_user = User.objects.create_user(
            username='role-admin',
            password='test-password-123',
        )
        Users.objects.create(
            user_id=self.admin_user.id,
            name='role-admin',
            openid=self.tenant_openid,
            appid='role-app',
            t_code='role-code',
            ip='127.0.0.1',
        )
        self.admin = Staff.objects.create(
            staff_name='role-admin',
            staff_type='Admin',
            check_code=1111,
            openid=self.tenant_openid,
        )
        self.worker = Staff.objects.create(
            staff_name='worker-1',
            staff_type='StockControl',
            check_code=2222,
            openid=self.tenant_openid,
        )
        self.admin_token = issue_session_token(self.admin, token_kind='admin')
        self.worker_token = issue_session_token(self.worker, token_kind='staff')

    def request(self, token, operator=None):
        client = APIClient()
        headers = {'HTTP_TOKEN': token}
        if operator is not None:
            headers['HTTP_OPERATOR'] = str(operator)
        client.credentials(**headers)
        return client

    def test_legacy_tenant_openid_is_not_an_api_credential(self):
        response = self.request(self.tenant_openid).get('/company/')
        self.assertEqual(response.status_code, 401)

    def test_admin_login_returns_opaque_session_token(self):
        response = self.client.post(
            '/login/',
            {'name': 'role-admin', 'password': 'test-password-123'},
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()['data']
        self.assertTrue(data['token'].startswith('gwms_'))
        self.assertEqual(data['openid'], data['token'])
        self.assertEqual(data['tenant_openid'], self.tenant_openid)
        self.assertEqual(self.request(data['token']).get('/company/').status_code, 200)

    def test_worker_cannot_manage_staff_or_master_data(self):
        worker = self.request(self.worker_token, operator=self.worker.id)
        self.assertEqual(worker.get('/staff/').status_code, 403)
        self.assertEqual(
            worker.post('/staff/', {
                'staff_name': 'forged-manager',
                'staff_type': 'Manager',
                'check_code': 3333,
            }).status_code,
            403,
        )
        self.assertEqual(
            worker.post('/company/', {
                'company_name': 'forged-company',
                'company_city': 'Dallas',
                'company_address': '1 Test Way',
                'company_contact': '555-0100',
                'company_manager': 'worker-1',
                'creater': 'worker-1',
            }).status_code,
            403,
        )

    def test_worker_can_read_own_staff_profile_only(self):
        worker = self.request(self.worker_token, operator=self.worker.id)
        response = worker.get('/staff/?staff_name=worker-1')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['count'], 1)
        self.assertEqual(response.json()['results'][0]['staff_name'], 'worker-1')

    def test_worker_cannot_spoof_operator_identity(self):
        worker = self.request(self.worker_token, operator=self.admin.id)
        response = worker.post('/staging/assignments/', {})
        self.assertEqual(response.status_code, 403)

    def test_admin_can_issue_a_staff_session_token(self):
        admin = self.request(self.admin_token)
        response = admin.get('/staff/?staff_name=worker-1&check_code=2222')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['token_type'], 'staff')
        issued_token = response.json()['auth_token']
        self.assertTrue(issued_token.startswith('gwms_'))
        self.assertEqual(self.request(issued_token).get('/company/').status_code, 200)

    def test_tenant_keeps_one_active_administrator(self):
        admin = self.request(self.admin_token)
        duplicate = admin.post('/staff/', {
            'staff_name': 'second-admin',
            'staff_type': 'Admin',
            'check_code': 4444,
        })
        self.assertEqual(duplicate.status_code, 409)
        self.assertEqual(admin.delete('/staff/{}/'.format(self.admin.id)).status_code, 400)
