import json

from django.test import Client, TestCase

from staff.models import ListModel, StaffSessionToken


class DirectStaffLoginTests(TestCase):
    def setUp(self):
        self.client = Client()
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

    def test_wrong_check_code_locks_after_three_attempts(self):
        for _ in range(2):
            response = self.post_login(check_code=999999)
            self.assertEqual(response.status_code, 401)
        response = self.post_login(check_code=999999)
        self.assertEqual(response.status_code, 423)
        self.staff.refresh_from_db()
        self.assertTrue(self.staff.is_lock)
        self.assertEqual(self.staff.error_check_code_counter, 0)

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
