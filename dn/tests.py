from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from rest_framework.exceptions import APIException

from driver.models import DispatchListModel, ListModel as Driver
from staff.models import ListModel as Staff
from stock.models import StockBinModel, StockListModel
from staging.models import StagingAssignment

from .models import DnDetailModel, DnListModel, PickingListModel
from .views import DnDispatchViewSet


class DnDispatchSafetyTests(TestCase):
    def setUp(self):
        self.openid = 'dn-dispatch-test'
        self.dn = DnListModel.objects.create(
            dn_code='DN-TEST-01',
            dn_status=4,
            customer='Customer A',
            creater='tester',
            bar_code='DN-BAR-01',
            openid=self.openid,
        )
        DnDetailModel.objects.create(
            dn_code=self.dn.dn_code,
            dn_status=4,
            customer=self.dn.customer,
            goods_code='SKU-01',
            goods_desc='Test SKU',
            goods_qty=2,
            picked_qty=2,
            creater='tester',
            openid=self.openid,
        )
        StockListModel.objects.create(
            goods_code='SKU-01',
            goods_desc='Test SKU',
            goods_qty=3,
            picked_stock=2,
            openid=self.openid,
        )
        PickingListModel.objects.create(
            dn_code=self.dn.dn_code,
            bin_name='A1-01',
            goods_code='SKU-01',
            picked_qty=2,
            creater='tester',
            t_code='TX-01',
            openid=self.openid,
        )
        StockBinModel.objects.create(
            bin_name='A1-01',
            goods_code='SKU-01',
            goods_desc='Test SKU',
            goods_qty=2,
            picked_qty=2,
            bin_size='STD',
            bin_property='Normal',
            t_code='TX-01',
            openid=self.openid,
            create_time=timezone.now(),
        )
        Driver.objects.create(
            driver_name='Tom',
            license_plate='TEST-01',
            contact='N/A',
            creater='tester',
            openid=self.openid,
        )
        self.operator = Staff.objects.create(
            staff_name='Dispatch Operator',
            staff_type='Inbound',
            openid=self.openid,
        )

    def request(self, data=None, operator_id=None):
        return SimpleNamespace(
            auth=SimpleNamespace(openid=self.openid),
            user=SimpleNamespace(is_authenticated=True),
            META={'HTTP_OPERATOR': str(operator_id or self.operator.id)},
            data=data or {},
        )

    def dispatch(self, data=None, operator_id=None):
        request = self.request(data, operator_id=operator_id)
        view = DnDispatchViewSet()
        view.request = request
        view.action = 'create'
        view.get_object = lambda: DnListModel.objects.get(id=self.dn.id)
        return view.create(request, self.dn.id)

    def test_missing_dn_code_and_free_form_contact_dispatch_once(self):
        response = self.dispatch({'driver': 'Tom', 'staging_bin': 'STAGE-LEFT-01'})

        self.assertEqual(response.status_code, 200)
        self.dn.refresh_from_db()
        self.assertEqual(self.dn.dn_status, 5)
        self.assertEqual(DispatchListModel.objects.filter(openid=self.openid, dn_code=self.dn.dn_code).count(), 1)
        self.assertEqual(
            DispatchListModel.objects.get(openid=self.openid, dn_code=self.dn.dn_code).contact,
            'N/A',
        )
        stock = StockListModel.objects.get(openid=self.openid, goods_code='SKU-01')
        self.assertEqual(stock.goods_qty, 1)
        self.assertEqual(stock.picked_stock, 0)

        with self.assertRaises(APIException):
            self.dispatch({'driver': 'Tom', 'staging_bin': 'STAGE-LEFT-01'})
        stock.refresh_from_db()
        self.assertEqual(stock.goods_qty, 1)
        self.assertEqual(DispatchListModel.objects.filter(openid=self.openid, dn_code=self.dn.dn_code).count(), 1)

    def test_dispatch_failure_rolls_back_inventory_and_staging(self):
        with patch('dn.views.driverdispatch.objects.create', side_effect=RuntimeError('dispatch write failed')):
            with self.assertRaises(RuntimeError):
                self.dispatch({'driver': 'Tom', 'staging_bin': 'STAGE-RIGHT-01'})

        self.dn.refresh_from_db()
        stock = StockListModel.objects.get(openid=self.openid, goods_code='SKU-01')
        detail = DnDetailModel.objects.get(openid=self.openid, dn_code=self.dn.dn_code)
        self.assertEqual(self.dn.dn_status, 4)
        self.assertEqual(stock.goods_qty, 3)
        self.assertEqual(stock.picked_stock, 2)
        self.assertEqual(detail.dn_status, 4)
        self.assertEqual(detail.intransit_qty, 0)
        self.assertFalse(StagingAssignment.objects.filter(
            openid=self.openid,
            reference_code=self.dn.dn_code,
            status__in=(StagingAssignment.RESERVED, StagingAssignment.ACTIVE),
        ).exists())
        self.assertFalse(DispatchListModel.objects.filter(openid=self.openid, dn_code=self.dn.dn_code).exists())

    def test_missing_operator_is_rejected_before_inventory_change(self):
        with self.assertRaises(APIException) as raised:
            self.dispatch(
                {'driver': 'Tom', 'staging_bin': 'STAGE-LEFT-01'},
                operator_id=999999,
            )
        self.assertEqual(raised.exception.detail['detail'], 'Operator does not exist')
