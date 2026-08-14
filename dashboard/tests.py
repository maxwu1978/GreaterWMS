from types import SimpleNamespace

from django.test import TestCase
from django.utils import timezone

from asn.models import AsnDetailModel, AsnListModel
from asnserial.models import AsnSerialRecord
from receiving.models import ReceivingDetail, ReceivingRecord

from .views import OperationsBoardViewSet


class OperationsBoardTests(TestCase):
    def test_dashboard_queue_is_scoped_to_role_and_driver_identity(self):
        view = OperationsBoardViewSet()
        items = [
            {'category': 'inbound', 'assigned_role': 'QC', 'assignee_name': ''},
            {'category': 'inbound', 'assigned_role': 'DRIVER', 'assignee_name': 'Tom'},
            {'category': 'outbound', 'assigned_role': 'WAREHOUSE', 'assignee_name': ''},
            {'category': 'outbound', 'assigned_role': 'DRIVER', 'assignee_name': 'John'},
        ]

        self.assertEqual(len(view._filter_for_identity(items, 'qc', 'qc-user')), 1)
        self.assertEqual(len(view._filter_for_identity(items, 'warehouse', 'warehouse-user')), 1)
        self.assertEqual(
            [item['assignee_name'] for item in view._filter_for_identity(items, 'driver', 'Tom')],
            ['Tom'],
        )
        self.assertEqual(len(view._filter_for_identity(items, 'driver', 'Tony')), 0)
        self.assertEqual(len(view._filter_for_identity(items, 'manager', 'manager-user')), 4)

    def test_putaway_asn_with_open_qc_exception_is_blocked_for_review(self):
        openid = 'dashboard-test-tenant'
        asn_code = 'ASN-DASHBOARD-01'
        AsnListModel.objects.create(
            asn_code=asn_code,
            asn_status=4,
            actual_arrival_at=timezone.now(),
            supplier='Test Customer',
            creater='tester',
            bar_code='BAR-DASHBOARD-01',
            openid=openid,
            transportation_fee={},
        )
        AsnDetailModel.objects.create(
            asn_code=asn_code,
            asn_status=4,
            supplier='Test Customer',
            goods_code='702-S',
            goods_desc='Test SKU',
            goods_qty=1,
            goods_actual_qty=1,
            creater='tester',
            openid=openid,
        )
        AsnSerialRecord.objects.create(
            openid=openid,
            asn_code=asn_code,
            goods_code='702-S',
            scanned_goods_code='702-S',
            serial_number='SN-DASHBOARD-01',
            status=AsnSerialRecord.DAMAGED,
            is_received=True,
            damaged=True,
        )

        items = OperationsBoardViewSet()._inbound_items(openid, timezone.now())

        self.assertEqual(items[0]['operation'], 'Review QC')
        self.assertEqual(items[0]['location'], 'Stage')
        self.assertEqual(items[0]['action_route'], 'asn')
        self.assertEqual(items[0]['lane'], 'blocked')
        self.assertEqual(items[0]['assigned_role'], 'QC')

    def test_arrived_unloading_asn_is_assigned_to_named_driver(self):
        openid = 'dashboard-driver-tenant'
        asn_code = 'ASN-DASHBOARD-DRIVER-01'
        AsnListModel.objects.create(
            asn_code=asn_code,
            asn_status=1,
            actual_arrival_at=timezone.now(),
            unload_driver='Tom',
            supplier='Test Customer',
            creater='tester',
            bar_code='BAR-DASHBOARD-DRIVER-01',
            openid=openid,
            transportation_fee={},
        )
        AsnDetailModel.objects.create(
            asn_code=asn_code,
            asn_status=1,
            supplier='Test Customer',
            goods_code='702-S',
            goods_desc='Test SKU',
            goods_qty=1,
            creater='tester',
            openid=openid,
        )

        items = OperationsBoardViewSet()._inbound_items(openid, timezone.now())

        self.assertEqual(items[0]['assigned_role'], 'DRIVER')
        self.assertEqual(items[0]['assignee_name'], 'Tom')

    def test_receiving_putaway_is_visible_to_assigned_driver(self):
        openid = 'dashboard-receiving-driver-tenant'
        record = ReceivingRecord.objects.create(
            openid=openid,
            receipt_no='RC-DASHBOARD-DRIVER-01',
            customer='Test Customer',
            received_at=timezone.now(),
            status=ReceivingRecord.PUTAWAY_PENDING,
            reconciliation_status=ReceivingRecord.NO_ASN,
            putaway_driver='Tom',
        )
        ReceivingDetail.objects.create(
            receipt=record,
            openid=openid,
            goods_code='702-S',
            actual_qty=2,
            accepted_qty=2,
        )

        items = OperationsBoardViewSet()._receiving_items(openid, timezone.now())

        self.assertEqual(items[0]['assigned_role'], 'DRIVER')
        self.assertEqual(items[0]['assignee_name'], 'Tom')
        self.assertEqual(items[0]['operation'], 'Putaway')
        self.assertEqual(
            len(OperationsBoardViewSet()._filter_for_identity(items, 'driver', 'Tom')),
            1,
        )
        self.assertEqual(
            len(OperationsBoardViewSet()._filter_for_identity(items, 'driver', 'Tony')),
            0,
        )

    def test_receiving_history_keeps_final_reconciliation_status_and_role_scope(self):
        openid = 'dashboard-history-tenant'
        record = ReceivingRecord.objects.create(
            openid=openid,
            receipt_no='RC-DASHBOARD-HISTORY-01',
            customer='Test Customer',
            received_at=timezone.now(),
            status=ReceivingRecord.CLOSED,
            reconciliation_status=ReceivingRecord.MATCHED,
            qc_by='QC-1',
            putaway_driver='Tom',
            closed_by='Warehouse-1',
        )
        ReceivingDetail.objects.create(
            receipt=record,
            openid=openid,
            goods_code='702-S',
            actual_qty=2,
            accepted_qty=2,
            putaway_qty=2,
        )

        items = OperationsBoardViewSet()._receiving_items(
            openid,
            timezone.now(),
            history=True,
        )
        item = items[0]

        self.assertEqual(item['lane'], 'completed')
        self.assertEqual(item['business_status'], ReceivingRecord.MATCHED)
        self.assertIn('QC', item['history_roles'])
        self.assertIn('DRIVER', item['history_roles'])
        self.assertEqual(
            len(OperationsBoardViewSet()._filter_for_identity(items, 'qc', 'QC-1', history=True)),
            1,
        )
        self.assertEqual(
            len(OperationsBoardViewSet()._filter_for_identity(items, 'driver', 'Tom', history=True)),
            1,
        )
        self.assertEqual(
            len(OperationsBoardViewSet()._filter_for_identity(items, 'driver', 'Tony', history=True)),
            0,
        )

        request = SimpleNamespace(
            auth=SimpleNamespace(
                openid=openid,
                staff_name='Manager-1',
                staff_type='Manager',
            ),
            query_params={'view': 'history', 'limit': '10'},
        )
        response = OperationsBoardViewSet().list(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['view'], 'history')
        self.assertEqual(response.data['items'][0]['business_status'], ReceivingRecord.MATCHED)

# Create your tests here.
