from types import SimpleNamespace

from django.test import TestCase
from django.utils import timezone
from rest_framework.exceptions import APIException, ValidationError

from asn.models import AsnDetailModel, AsnListModel
from asn.views import AsnDetailViewSet
from binset.models import ListModel as BinModel
from driver.models import ListModel as DriverModel
from dn.models import DnDetailModel, DnListModel, DnSerialAllocation
from goods.models import ListModel as GoodsModel
from staff.models import ListModel as StaffModel
from stock.models import StockListModel
from supplier.models import ListModel as SupplierModel
from userprofile.models import Users
from warehouse.models import ListModel as WarehouseModel

from .models import ReceivingDetail, ReceivingRecord, ReceivingSerial
from .views import (
    ReceivingExceptionResolveView,
    ReceivingPutawayAssignView,
    ReceivingPutawayView,
    ReceivingQcCompleteView,
    ReceivingRecordListView,
    ReceivingReconcileView,
)
from .services import assert_legacy_asn_putaway_allowed


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

        assigned = self.call(ReceivingPutawayAssignView, {
            'receipt_no': 'RC-001',
            'driver_name': 'Tom',
        })
        self.assertEqual(assigned.data['putaway_driver'], 'Tom')

        putaway = self.call(ReceivingPutawayView, {
            'receipt_no': 'RC-001',
            'goods_code': self.goods_code,
            'quantity': 2,
            'bin_name': 'A1-01',
            'driver_name': 'Tom',
            'idempotency_key': 'RC-001-A1-01',
        })
        self.assertEqual(putaway.data['status'], ReceivingRecord.PUTAWAY_COMPLETE)
        self.assertEqual(putaway.data['putaway_driver'], 'Tom')
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

    def test_linked_asn_receiving_does_not_double_total_or_asn_stock(self):
        supplier = SupplierModel.objects.create(
            supplier_name='Customer A',
            supplier_city='Dallas',
            supplier_address='Test address',
            supplier_contact='test',
            supplier_manager='test',
            creater='tester',
            openid=self.openid,
        )
        WarehouseModel.objects.create(
            warehouse_name='Test Warehouse',
            warehouse_city='Dallas',
            warehouse_address='Test address',
            warehouse_contact='test',
            warehouse_manager='test',
            creater='tester',
            openid=self.openid,
        )
        operator = StaffModel.objects.create(
            staff_name='ASN Operator',
            staff_type='Manager',
            openid=self.openid,
        )
        Users.objects.create(
            user_id=operator.id,
            name=operator.staff_name,
            openid=self.openid,
            appid='receiving-test-app',
            t_code='receiving-test-code',
            ip='127.0.0.1',
        )
        AsnListModel.objects.create(
            asn_code='ASN-INVENTORY-001',
            asn_status=1,
            supplier='Customer A',
            creater='tester',
            bar_code='ASN-INVENTORY-BAR',
            openid=self.openid,
            transportation_fee={},
        )
        asn_request = SimpleNamespace(
            auth=SimpleNamespace(openid=self.openid),
            user=SimpleNamespace(is_authenticated=True),
            META={'HTTP_OPERATOR': str(operator.id)},
            data={
                'asn_code': 'ASN-INVENTORY-001',
                'supplier': supplier.supplier_name,
                'goods_code': [self.goods_code],
                'goods_qty': [2],
            },
        )
        asn_view = AsnDetailViewSet()
        asn_view.request = asn_request
        asn_view.action = 'create'
        asn_view.format_kwarg = None
        asn_response = asn_view.create(asn_request)
        self.assertEqual(asn_response.status_code, 200)
        stock = StockListModel.objects.get(openid=self.openid, goods_code=self.goods_code)
        self.assertEqual(stock.goods_qty, 2)
        self.assertEqual(stock.asn_stock, 2)
        created = self.call(ReceivingRecordListView, {
            'receipt_no': 'RC-INVENTORY-001',
            'customer': 'Customer A',
            'linked_asn_code': 'ASN-INVENTORY-001',
            'details': [{'goods_code': self.goods_code, 'actual_qty': 2}],
        })
        self.assertEqual(created.status_code, 201)
        self.call(ReceivingQcCompleteView, {
            'receipt_no': 'RC-INVENTORY-001',
            'details': [{'goods_code': self.goods_code, 'actual_qty': 2}],
        })
        stock = StockListModel.objects.get(openid=self.openid, goods_code=self.goods_code)
        self.assertEqual(stock.goods_qty, 2)
        self.assertEqual(stock.asn_stock, 0)

        putaway = self.call(ReceivingPutawayView, {
            'receipt_no': 'RC-INVENTORY-001',
            'goods_code': self.goods_code,
            'quantity': 2,
            'bin_name': 'A1-01',
            'driver_name': 'Tom',
        })
        self.assertEqual(putaway.data['status'], ReceivingRecord.PUTAWAY_COMPLETE)
        stock.refresh_from_db()
        self.assertEqual(stock.goods_qty, 2)
        self.assertEqual(stock.onhand_stock, 2)
        self.assertEqual(stock.can_order_stock, 2)

    def test_reconcile_after_unlinked_receiving_removes_late_asn_reservation(self):
        self.call(ReceivingRecordListView, {
            'receipt_no': 'RC-LATE-ASN-001',
            'customer': 'Customer A',
            'details': [{'goods_code': self.goods_code, 'actual_qty': 2}],
        })
        self.call(ReceivingQcCompleteView, {
            'receipt_no': 'RC-LATE-ASN-001',
            'details': [{'goods_code': self.goods_code, 'actual_qty': 2}],
        })
        self.call(ReceivingPutawayView, {
            'receipt_no': 'RC-LATE-ASN-001',
            'goods_code': self.goods_code,
            'quantity': 2,
            'bin_name': 'A1-01',
            'driver_name': 'Tom',
        })
        stock = StockListModel.objects.get(openid=self.openid, goods_code=self.goods_code)
        self.assertEqual(stock.goods_qty, 2)

        AsnListModel.objects.create(
            asn_code='ASN-LATE-001',
            asn_status=1,
            supplier='Customer A',
            creater='tester',
            bar_code='ASN-LATE-BAR',
            openid=self.openid,
            transportation_fee={},
        )
        AsnDetailModel.objects.create(
            asn_code='ASN-LATE-001',
            asn_status=1,
            supplier='Customer A',
            goods_code=self.goods_code,
            goods_desc='Receiving test SKU',
            goods_qty=2,
            creater='tester',
            openid=self.openid,
        )
        stock.goods_qty += 2
        stock.asn_stock = 2
        stock.save()
        reconciled = self.call(ReceivingReconcileView, {
            'receipt_no': 'RC-LATE-ASN-001',
            'asn_code': 'ASN-LATE-001',
        })
        self.assertEqual(reconciled.data['variance'], {})
        stock.refresh_from_db()
        self.assertEqual(stock.goods_qty, 2)
        self.assertEqual(stock.asn_stock, 0)

    def test_receiving_claims_an_asn_once_and_blocks_started_legacy_asn(self):
        AsnListModel.objects.create(
            asn_code='ASN-CLAIM-001',
            asn_status=1,
            supplier='Customer A',
            creater='tester',
            bar_code='ASN-CLAIM-BAR',
            openid=self.openid,
            transportation_fee={},
        )
        AsnDetailModel.objects.create(
            asn_code='ASN-CLAIM-001',
            asn_status=1,
            supplier='Customer A',
            goods_code=self.goods_code,
            goods_desc='Receiving test SKU',
            goods_qty=2,
            creater='tester',
            openid=self.openid,
        )
        created = self.call(ReceivingRecordListView, {
            'receipt_no': 'RC-CLAIM-001',
            'customer': 'Customer A',
            'linked_asn_code': 'ASN-CLAIM-001',
            'details': [{'goods_code': self.goods_code, 'actual_qty': 2}],
        })
        self.assertEqual(created.status_code, 201)
        with self.assertRaises(APIException):
            self.call(ReceivingRecordListView, {
                'receipt_no': 'RC-CLAIM-002',
                'customer': 'Customer A',
                'linked_asn_code': 'ASN-CLAIM-001',
                'details': [{'goods_code': self.goods_code, 'actual_qty': 2}],
            })

        legacy_asn = AsnListModel.objects.create(
            asn_code='ASN-LEGACY-001',
            asn_status=4,
            supplier='Customer A',
            creater='tester',
            bar_code='ASN-LEGACY-BAR',
            openid=self.openid,
            transportation_fee={},
        )
        AsnDetailModel.objects.create(
            asn_code=legacy_asn.asn_code,
            asn_status=4,
            supplier='Customer A',
            goods_code=self.goods_code,
            goods_desc='Receiving test SKU',
            goods_qty=2,
            creater='tester',
            openid=self.openid,
        )
        ReceivingRecord.objects.create(
            receipt_no='RC-CANONICAL-001',
            customer='Customer A',
            openid=self.openid,
            received_at=timezone.now(),
            status=ReceivingRecord.PUTAWAY_COMPLETE,
        )
        canonical = ReceivingRecord.objects.get(receipt_no='RC-CANONICAL-001')
        ReceivingDetail.objects.create(
            receipt=canonical,
            openid=self.openid,
            goods_code=self.goods_code,
            actual_qty=2,
            accepted_qty=2,
            putaway_qty=2,
        )
        with self.assertRaises(APIException):
            assert_legacy_asn_putaway_allowed(self.openid, legacy_asn.asn_code, self.goods_code)

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

    def test_canceled_outbound_return_reenters_inventory_through_receiving(self):
        DnListModel.objects.create(
            dn_code='DN-RETURN-001',
            dn_status=7,
            customer='Customer A',
            creater='tester',
            bar_code='DN-RETURN-BAR',
            openid=self.openid,
            transportation_fee={},
        )
        DnDetailModel.objects.create(
            dn_code='DN-RETURN-001',
            dn_status=7,
            customer='Customer A',
            goods_code=self.goods_code,
            goods_desc='Receiving test SKU',
            goods_qty=2,
            cancelled_qty=2,
            creater='tester',
            openid=self.openid,
        )
        created = self.call(ReceivingRecordListView, {
            'receipt_no': 'RC-RETURN-001',
            'customer': 'Customer A',
            'source_type': 'OUTBOUND_RETURN',
            'source_reference': 'DN-RETURN-001',
            'details': [{'goods_code': self.goods_code, 'actual_qty': 2}],
        })
        self.assertEqual(created.status_code, 201)
        self.call(ReceivingQcCompleteView, {
            'receipt_no': 'RC-RETURN-001',
            'details': [{'goods_code': self.goods_code, 'actual_qty': 2}],
        })
        putaway = self.call(ReceivingPutawayView, {
            'receipt_no': 'RC-RETURN-001',
            'goods_code': self.goods_code,
            'quantity': 2,
            'bin_name': 'A1-01',
            'driver_name': 'Tom',
        })
        self.assertEqual(putaway.data['status'], ReceivingRecord.PUTAWAY_COMPLETE)
        self.assertEqual(
            StockListModel.objects.get(openid=self.openid, goods_code=self.goods_code).onhand_stock,
            2,
        )
        detail = DnDetailModel.objects.get(dn_code='DN-RETURN-001', goods_code=self.goods_code)
        self.assertEqual(detail.returned_qty, 2)
        with self.assertRaises(ValidationError):
            self.call(ReceivingRecordListView, {
                'receipt_no': 'RC-RETURN-002',
                'customer': 'Customer A',
                'source_type': 'OUTBOUND_RETURN',
                'source_reference': 'DN-RETURN-001',
                'details': [{'goods_code': self.goods_code, 'actual_qty': 1}],
            })

    def test_outbound_return_allows_released_serial_to_be_received_again(self):
        self.call(ReceivingRecordListView, {
            'receipt_no': 'RC-SN-HISTORY-001',
            'customer': 'Customer A',
            'details': [{'goods_code': self.goods_code, 'actual_qty': 1}],
        })
        self.call(ReceivingQcCompleteView, {
            'receipt_no': 'RC-SN-HISTORY-001',
            'details': [{
                'goods_code': self.goods_code,
                'actual_qty': 1,
                'serials': ['SN-RETURN-001'],
            }],
        })
        self.assertTrue(ReceivingSerial.objects.filter(
            serial_number='SN-RETURN-001',
            status=ReceivingSerial.ACCEPTED,
        ).exists())

        DnListModel.objects.create(
            dn_code='DN-RETURN-SN-001',
            dn_status=7,
            customer='Customer A',
            creater='tester',
            bar_code='DN-RETURN-SN-BAR',
            openid=self.openid,
            transportation_fee={},
        )
        DnDetailModel.objects.create(
            dn_code='DN-RETURN-SN-001',
            dn_status=7,
            customer='Customer A',
            goods_code=self.goods_code,
            goods_desc='Receiving test SKU',
            goods_qty=1,
            cancelled_qty=1,
            creater='tester',
            openid=self.openid,
        )
        DnSerialAllocation.objects.create(
            openid=self.openid,
            dn_code='DN-RETURN-SN-001',
            goods_code=self.goods_code,
            serial_number='SN-RETURN-001',
            status=DnSerialAllocation.RELEASED,
            created_by='tester',
        )
        created = self.call(ReceivingRecordListView, {
            'receipt_no': 'RC-RETURN-SN-001',
            'customer': 'Customer A',
            'source_type': 'OUTBOUND_RETURN',
            'source_reference': 'DN-RETURN-SN-001',
            'details': [{'goods_code': self.goods_code, 'actual_qty': 1}],
        })
        self.assertEqual(created.status_code, 201)
        qc = self.call(ReceivingQcCompleteView, {
            'receipt_no': 'RC-RETURN-SN-001',
            'details': [{
                'goods_code': self.goods_code,
                'actual_qty': 1,
                'serials': ['SN-RETURN-001'],
            }],
        })
        self.assertEqual(qc.data['status'], ReceivingRecord.PUTAWAY_PENDING)
        self.assertTrue(ReceivingSerial.objects.filter(
            detail__receipt__receipt_no='RC-RETURN-SN-001',
            serial_number='SN-RETURN-001',
            status=ReceivingSerial.ACCEPTED,
        ).exists())
        self.assertEqual(
            DnSerialAllocation.objects.get(
                dn_code='DN-RETURN-SN-001',
                serial_number='SN-RETURN-001',
            ).status,
            DnSerialAllocation.RETURNED,
        )
        with self.assertRaises(ValidationError):
            self.call(ReceivingRecordListView, {
                'receipt_no': 'RC-RETURN-SN-002',
                'customer': 'Customer A',
                'source_type': 'OUTBOUND_RETURN',
                'source_reference': 'DN-RETURN-SN-001',
                'details': [{'goods_code': self.goods_code, 'actual_qty': 1}],
            })

    def test_duplicate_serial_is_not_counted_without_expected_serials(self):
        self.call(ReceivingRecordListView, {
            'receipt_no': 'RC-SN-DUP-001',
            'customer': 'Customer A',
            'details': [{'goods_code': self.goods_code, 'actual_qty': 1}],
        })
        first = self.call(ReceivingQcCompleteView, {
            'receipt_no': 'RC-SN-DUP-001',
            'details': [{
                'goods_code': self.goods_code,
                'actual_qty': 1,
                'serials': ['SN-DUP-001'],
            }],
        })
        self.assertEqual(first.data['status'], ReceivingRecord.PUTAWAY_PENDING)

        self.call(ReceivingRecordListView, {
            'receipt_no': 'RC-SN-DUP-002',
            'customer': 'Customer A',
            'details': [{'goods_code': self.goods_code, 'actual_qty': 1}],
        })
        second = self.call(ReceivingQcCompleteView, {
            'receipt_no': 'RC-SN-DUP-002',
            'details': [{
                'goods_code': self.goods_code,
                'actual_qty': 1,
                'serials': ['SN-DUP-001'],
            }],
        })
        self.assertEqual(second.data['status'], ReceivingRecord.QC_EXCEPTION)
        detail = ReceivingRecord.objects.get(receipt_no='RC-SN-DUP-002').details.get(goods_code=self.goods_code)
        self.assertEqual(detail.accepted_qty, 0)
        self.assertEqual(detail.hold_qty, 1)
