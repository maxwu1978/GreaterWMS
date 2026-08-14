from types import SimpleNamespace

from django.test import TestCase
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from asn.models import AsnDetailModel, AsnListModel
from binset.models import ListModel as BinModel
from driver.models import ListModel as DriverModel
from goods.models import ListModel as GoodsModel
from stock.models import StockListModel

from .models import ReceivingRecord
from .views import (
    ReceivingExceptionResolveView,
    ReceivingPutawayView,
    ReceivingQcCompleteView,
    ReceivingRecordListView,
    ReceivingReconcileView,
)


class ReceivingFlowTests(TestCase):
    def setUp(self):
        self.openid = 'receiving-flow-test'
        self.goods_code = 'SKU-RECEIVE-01'
        GoodsModel.objects.create(
            goods_code=self.goods_code,
            goods_desc='Receiving test SKU',
            goods_supplier='Customer A',
            goods_unit='EA',
            goods_class='Test',
            goods_brand='Test',
            goods_color='Test',
            goods_shape='Test',
            goods_specs='Test',
            goods_origin='US',
            creater='tester',
            bar_code='BAR-RECEIVE-01',
            openid=self.openid,
        )
        DriverModel.objects.create(
            driver_name='Tom',
            license_plate='TEST-TRUCK',
            contact='N/A',
            creater='tester',
            openid=self.openid,
        )
        BinModel.objects.create(
            bin_name='A1-01',
            bin_size='STD',
            bin_property='Normal',
            creater='tester',
            bar_code='BIN-RECEIVE-01',
            openid=self.openid,
        )

    def request(self, data):
        return SimpleNamespace(
            auth=SimpleNamespace(
                openid=self.openid,
                is_admin=True,
                staff_name='Admin',
                staff_type='Manager',
            ),
            user=SimpleNamespace(is_authenticated=True),
            META={'HTTP_OPERATOR': '1'},
            data=data,
            GET={},
        )

    def call(self, view_class, data):
        request = self.request(data)
        view = view_class()
        view.request = request
        return view.post(request)

    def test_goods_can_be_received_before_asn_then_reconciled_after_putaway(self):
        created = self.call(ReceivingRecordListView, {
            'receipt_no': 'RC-001',
            'customer': 'Customer A',
            'details': [{'goods_code': self.goods_code, 'actual_qty': 2}],
        })
        self.assertEqual(created.status_code, 201)

        qc = self.call(ReceivingQcCompleteView, {
            'receipt_no': 'RC-001',
            'details': [{'goods_code': self.goods_code, 'actual_qty': 2}],
        })
        self.assertEqual(qc.data['status'], ReceivingRecord.PUTAWAY_PENDING)

        putaway = self.call(ReceivingPutawayView, {
            'receipt_no': 'RC-001',
            'goods_code': self.goods_code,
            'quantity': 2,
            'bin_name': 'A1-01',
            'driver_name': 'Tom',
            'idempotency_key': 'RC-001-A1-01',
        })
        self.assertEqual(putaway.data['status'], ReceivingRecord.PUTAWAY_COMPLETE)
        self.assertEqual(StockListModel.objects.get(openid=self.openid, goods_code=self.goods_code).onhand_stock, 2)
        self.assertEqual(putaway.data['reconciliation_status'], ReceivingRecord.NO_ASN)

        AsnListModel.objects.create(
            asn_code='ASN-AFTER-001',
            asn_status=1,
            supplier='Customer A',
            creater='tester',
            bar_code='ASN-AFTER-BAR',
            openid=self.openid,
            transportation_fee={},
        )
        AsnDetailModel.objects.create(
            asn_code='ASN-AFTER-001',
            asn_status=1,
            supplier='Customer A',
            goods_code=self.goods_code,
            goods_desc='Receiving test SKU',
            goods_qty=2,
            creater='tester',
            openid=self.openid,
        )
        reconciled = self.call(ReceivingReconcileView, {
            'receipt_no': 'RC-001',
            'asn_code': 'ASN-AFTER-001',
        })
        self.assertEqual(reconciled.data['variance'], {})
        self.assertEqual(reconciled.data['record']['status'], ReceivingRecord.CLOSED)
        self.assertEqual(reconciled.data['record']['reconciliation_status'], ReceivingRecord.MATCHED)

    def test_qc_exception_requires_resolution_before_putaway(self):
        self.call(ReceivingRecordListView, {
            'receipt_no': 'RC-002',
            'customer': 'Customer A',
            'details': [{'goods_code': self.goods_code, 'expected_qty': 2, 'actual_qty': 2}],
        })
        qc = self.call(ReceivingQcCompleteView, {
            'receipt_no': 'RC-002',
            'details': [{
                'goods_code': self.goods_code,
                'actual_qty': 2,
                'expected_serials': ['SN-1', 'SN-2'],
                'serials': ['SN-1', 'SN-WRONG'],
            }],
        })
        self.assertEqual(qc.data['status'], ReceivingRecord.QC_EXCEPTION)
        with self.assertRaises(ValidationError):
            self.call(ReceivingPutawayView, {
                'receipt_no': 'RC-002',
                'goods_code': self.goods_code,
                'quantity': 1,
                'bin_name': 'A1-01',
                'driver_name': 'Tom',
            })

        resolved = self.call(ReceivingExceptionResolveView, {
            'receipt_no': 'RC-002',
            'action': 'ACCEPT_FOR_PUTAWAY',
            'note': 'Customer approved one valid serial for storage',
        })
        self.assertEqual(resolved.data['status'], ReceivingRecord.PUTAWAY_PENDING)
        putaway = self.call(ReceivingPutawayView, {
            'receipt_no': 'RC-002',
            'goods_code': self.goods_code,
            'quantity': 1,
            'bin_name': 'A1-01',
            'driver_name': 'Tom',
        })
        self.assertEqual(putaway.data['status'], ReceivingRecord.PUTAWAY_COMPLETE)

    def test_reconciliation_cannot_bypass_qc_and_putaway(self):
        self.call(ReceivingRecordListView, {
            'receipt_no': 'RC-003',
            'customer': 'Customer A',
            'details': [{'goods_code': self.goods_code, 'actual_qty': 1}],
        })
        AsnListModel.objects.create(
            asn_code='ASN-BEFORE-001',
            asn_status=1,
            supplier='Customer A',
            creater='tester',
            bar_code='ASN-BEFORE-BAR',
            openid=self.openid,
            transportation_fee={},
        )
        AsnDetailModel.objects.create(
            asn_code='ASN-BEFORE-001',
            asn_status=1,
            supplier='Customer A',
            goods_code=self.goods_code,
            goods_desc='Receiving test SKU',
            goods_qty=1,
            creater='tester',
            openid=self.openid,
        )
        with self.assertRaises(ValidationError):
            self.call(ReceivingReconcileView, {
                'receipt_no': 'RC-003',
                'asn_code': 'ASN-BEFORE-001',
            })
