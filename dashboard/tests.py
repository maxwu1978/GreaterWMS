from django.test import TestCase
from django.utils import timezone

from asn.models import AsnDetailModel, AsnListModel
from asnserial.models import AsnSerialRecord

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

# Create your tests here.
