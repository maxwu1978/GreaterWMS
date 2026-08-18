import json

from django.core.cache import cache
from django.test import Client, TestCase
from django.test.utils import override_settings

from staff.models import ListModel, StaffSessionToken
from staff.serializers import (
    FileRenderSerializer,
    StaffGetSerializer,
    StaffPartialUpdateSerializer,
    StaffPostSerializer,
    StaffUpdateSerializer,
)


@override_settings(
    STAFF_LOGIN_RATE_LIMIT_WINDOW_SECONDS=60,
    STAFF_LOGIN_ACCOUNT_RATE_LIMIT=3,
    STAFF_LOGIN_IP_RATE_LIMIT=10,
)
class DirectStaffLoginTests(TestCase):
    def setUp(self):
        self.client = Client()
        cache.clear()
        self.staff = ListModel.objects.create(
            staff_name='op10@peaksmartlogistics.com',
            staff_type='Warehouse',
            check_code=123456,
            openid='tenant-direct-login',
        )

    def post_login(self, staff_name=None, check_code=None):
        payload = {
            'staff_name': staff_name or self.staff.staff_name,
            'check_code': self.staff.check_code if check_code is None else check_code,
        }
        return self.client.post(
            '/staff/login/',
            data=json.dumps(payload),
            content_type='application/json',
        )

    def test_staff_can_login_without_an_admin_session(self):
        response = self.post_login()
        self.assertEqual(response.status_code, 200)
        data = response.json()['data']
        self.assertEqual(data['user_id'], self.staff.id)
        self.assertEqual(data['staff_type'], 'Warehouse')
        self.assertTrue(data['token'].startswith('gwms_'))
        self.assertEqual(
            StaffSessionToken.objects.filter(
                staff_id=self.staff.id,
                token_kind='staff',
            ).count(),
            1,
        )

    def test_wrong_check_code_does_not_lock_shared_account(self):
        for _ in range(2):
            response = self.post_login(check_code=999999)
            self.assertEqual(response.status_code, 401)
        response = self.post_login(check_code=999999)
        self.assertEqual(response.status_code, 401)
        self.staff.refresh_from_db()
        self.assertFalse(self.staff.is_lock)
        self.assertEqual(self.staff.error_check_code_counter, 0)

    def test_repeated_wrong_codes_are_rate_limited_without_locking_account(self):
        for _ in range(3):
            response = self.post_login(check_code=999999)
            self.assertEqual(response.status_code, 401)
        response = self.post_login(check_code=999999)
        self.assertEqual(response.status_code, 429)
        self.staff.refresh_from_db()
        self.assertFalse(self.staff.is_lock)

    def test_locked_staff_cannot_login(self):
        self.staff.is_lock = True
        self.staff.save(update_fields=['is_lock'])
        response = self.post_login()
        self.assertEqual(response.status_code, 423)
        self.assertEqual(StaffSessionToken.objects.filter(staff_id=self.staff.id).count(), 0)

    def test_duplicate_staff_name_is_rejected(self):
        ListModel.objects.create(
            staff_name=self.staff.staff_name.upper(),
            staff_type='Driver',
            check_code=123456,
            openid='tenant-other-login',
        )
        response = self.post_login()
        self.assertEqual(response.status_code, 409)
        self.assertIn('ambiguous', response.json()['detail'].lower())

    def test_invalid_method_is_rejected(self):
        response = self.client.get('/staff/login/')
        self.assertEqual(response.status_code, 405)

    def test_staff_serializers_never_return_check_code(self):
        self.assertNotIn('check_code', StaffGetSerializer(self.staff).data)
        self.assertNotIn('check_code', FileRenderSerializer(self.staff).data)
        self.assertNotIn('check_code', StaffPostSerializer(self.staff).data)
        self.assertNotIn('check_code', StaffUpdateSerializer(self.staff).data)
        self.assertNotIn('check_code', StaffPartialUpdateSerializer(self.staff).data)
