from types import SimpleNamespace
from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIRequestFactory
from rest_framework.exceptions import PermissionDenied

from asnserial.models import AgentCommandPreview
from company.models import ListModel as Company
from staff.auth import hash_session_token
from staff.models import ListModel as Staff
from staff.models import StaffSessionToken, TypeListModel
from userprofile.models import Users

from .service import CLEANUP_PAYLOAD, build_cleanup_plan, execute_cleanup
from .views import TenantCleanupPreviewView


@override_settings(
    TENANT_CLEANUP_ENABLED=True,
    TENANT_CLEANUP_ALLOWED_OPENIDS={'tenant-cleanup-test'},
)
class TenantCleanupServiceTests(TestCase):
    def setUp(self):
        self.tenant = 'tenant-cleanup-test'
        self.raw_token = 'gwms_test_admin_token'
        self.admin = Staff.objects.create(
            staff_name='admin@example.test',
            staff_type='Admin',
            check_code=1234,
            openid=self.tenant,
        )
        self.other_staff = Staff.objects.create(
            staff_name='warehouse@example.test',
            staff_type='Warehouse',
            check_code=5678,
            openid=self.tenant,
        )
        self.admin_profile = Users.objects.create(
            user_id=1,
            name=self.admin.staff_name,
            openid=self.tenant,
            appid='test-app',
            t_code='test-code',
            ip='127.0.0.1',
        )
        self.other_profile = Users.objects.create(
            user_id=2,
            name=self.other_staff.staff_name,
            openid=self.tenant,
            appid='test-app-2',
            t_code='test-code-2',
            ip='127.0.0.1',
        )
        self.session = StaffSessionToken.objects.create(
            staff_id=self.admin.id,
            openid=self.tenant,
            token_hash=hash_session_token(self.raw_token),
            token_kind='admin',
        )
        self.other_session = StaffSessionToken.objects.create(
            staff_id=self.other_staff.id,
            openid=self.tenant,
            token_hash=hash_session_token('other-token'),
            token_kind='staff',
        )
        Company.objects.create(
            openid=self.tenant,
            company_name='Test Company',
            company_city='Test City',
            company_address='Test Address',
            company_contact='000',
            company_manager='Test Manager',
            creater='Test',
        )
        TypeListModel.objects.create(
            openid='init_data',
            staff_type='Admin',
            creater='seed',
        )
        self.request = SimpleNamespace(
            auth=SimpleNamespace(
                is_admin=True,
                openid=self.tenant,
                staff_id=self.admin.id,
            ),
            META={
                'HTTP_TOKEN': self.raw_token,
                'HTTP_OPERATOR': str(self.admin.id),
            },
        )

    def test_plan_excludes_admin_context(self):
        plan = build_cleanup_plan(self.request)

        self.assertEqual(plan['deletions']['staff.ListModel'], 1)
        self.assertEqual(plan['deletions']['userprofile.Users'], 1)
        self.assertEqual(plan['deletions']['staff.StaffSessionToken'], 1)
        self.assertEqual(plan['deletions']['company.ListModel'], 1)
        self.assertEqual(plan['protected']['admin_staff_id'], self.admin.id)
        self.assertEqual(plan['protected']['session_id'], self.session.id)

    @override_settings(TENANT_CLEANUP_ALLOWED_OPENIDS=set())
    def test_cleanup_requires_an_explicitly_allowlisted_tenant(self):
        with self.assertRaises(PermissionDenied):
            build_cleanup_plan(self.request)

    def test_execute_deletes_tenant_data_but_preserves_admin_context_and_seed(self):
        command = AgentCommandPreview.objects.create(
            openid=self.tenant,
            operation='tenant.cleanup',
            payload_hash='payload-hash',
            confirmation_token_hash='token-hash',
            preview_payload=CLEANUP_PAYLOAD,
            expires_at=timezone.now() + timedelta(days=1),
        )

        result = execute_cleanup(self.request, command)

        self.assertGreaterEqual(result['delete_total'], 4)
        self.assertTrue(Staff.objects.filter(id=self.admin.id, is_delete=False).exists())
        self.assertTrue(Users.objects.filter(id=self.admin_profile.id, is_delete=False).exists())
        self.assertTrue(StaffSessionToken.objects.filter(id=self.session.id, is_revoked=False).exists())
        self.assertFalse(Staff.objects.filter(id=self.other_staff.id).exists())
        self.assertFalse(Users.objects.filter(id=self.other_profile.id).exists())
        self.assertFalse(StaffSessionToken.objects.filter(id=self.other_session.id).exists())
        self.assertTrue(TypeListModel.objects.filter(openid='init_data').exists())
        self.assertEqual(
            AgentCommandPreview.objects.get(id=command.id).status,
            AgentCommandPreview.EXECUTED,
        )

    def test_preview_view_requires_agent_client_header(self):
        request = APIRequestFactory().post('/tenant/cleanup/preview/', {}, format='json')
        request.auth = self.request.auth
        request.user = self.request.auth
        request.META['HTTP_OPERATOR'] = str(self.admin.id)
        response = TenantCleanupPreviewView.as_view()(request)

        self.assertEqual(response.status_code, 401)

    def test_preview_view_returns_plan_for_authenticated_admin_agent(self):
        request = APIRequestFactory().post('/tenant/cleanup/preview/', {}, format='json')
        request.auth = self.request.auth
        request.user = SimpleNamespace(is_authenticated=True)
        request.META.update({
            'HTTP_OPERATOR': str(self.admin.id),
            'HTTP_TOKEN': self.raw_token,
            'HTTP_X_AGENT_CLIENT': 'greaterwms-cli',
        })
        response = TenantCleanupPreviewView.as_view()(request)

        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(response.data['delete_total'], 4)
        self.assertEqual(response.data['protected']['admin_staff_id'], self.admin.id)
