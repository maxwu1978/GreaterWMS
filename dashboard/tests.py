from types import SimpleNamespace
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from asn.models import AsnDetailModel, AsnListModel
from asnserial.models import AsnSerialRecord
from dn.models import DnDetailModel
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
        self.assertEqual(items[0]['task_qty'], 1)
        self.assertEqual(items[0]['task_total_qty'], 1)
        self.assertEqual(items[0]['quantity_label'], '1 / 1')
        self.assertEqual(items[0]['location_summary'], 'Dock -> Stage')

        request = SimpleNamespace(
            auth=SimpleNamespace(
                openid=openid,
                staff_name='Tom',
                staff_type='Driver',
            ),
            query_params={'view': 'active', 'limit': '10', 'offset': '0'},
        )
        response = OperationsBoardViewSet().list(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['total'], 1)
        self.assertEqual(response.data['offset'], 0)
        self.assertFalse(response.data['has_more'])
        self.assertEqual(response.data['items'][0]['action_code'], 'unload')
        self.assertEqual(response.data['items'][0]['available_actions'], ['unload'])
        self.assertTrue(response.data['items'][0]['can_act'])

    def test_dashboard_action_metadata_is_scoped_to_role(self):
        view = OperationsBoardViewSet()
        driver_task = {
            'category': 'inbound',
            'assigned_role': 'DRIVER',
            'assignee_name': 'Tom',
            'operation': 'Unload',
        }

        view._decorate_action(driver_task, 'driver')
        self.assertEqual(driver_task['action_code'], 'unload')
        self.assertEqual(driver_task['available_actions'], ['unload'])
        self.assertTrue(driver_task['can_act'])

        view._decorate_action(driver_task, 'qc')
        self.assertEqual(driver_task['action_code'], 'unload')
        self.assertEqual(driver_task['available_actions'], [])
        self.assertFalse(driver_task['can_act'])

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

    def test_history_excludes_in_progress_inbound_and_outbound(self):
        openid = 'dashboard-history-terminal-tenant'
        AsnDetailModel.objects.create(
            asn_code='ASN-DASHBOARD-IN-PROGRESS',
            asn_status=2,
            supplier='Test Customer',
            goods_code='702-S',
            goods_desc='Test SKU',
            goods_qty=1,
            creater='tester',
            openid=openid,
        )
        DnDetailModel.objects.create(
            dn_code='DN-DASHBOARD-IN-PROGRESS',
            dn_status=3,
            customer='Test Customer',
            goods_code='702-S',
            goods_desc='Test SKU',
            goods_qty=1,
            creater='tester',
            openid=openid,
        )
        AsnDetailModel.objects.create(
            asn_code='ASN-DASHBOARD-COMPLETED',
            asn_status=5,
            supplier='Test Customer',
            goods_code='702-S',
            goods_desc='Test SKU',
            goods_qty=1,
            creater='tester',
            openid=openid,
        )
        for dn_code, dn_status in (
            ('DN-DASHBOARD-COMPLETED', 6),
            ('DN-DASHBOARD-CANCELLED', 7),
        ):
            DnDetailModel.objects.create(
                dn_code=dn_code,
                dn_status=dn_status,
                customer='Test Customer',
                goods_code='702-S',
                goods_desc='Test SKU',
                goods_qty=1,
                creater='tester',
                openid=openid,
            )

        view = OperationsBoardViewSet()
        active_references = {
            item['reference']
            for item in view._inbound_items(openid, timezone.now())
            + view._outbound_items(openid, timezone.now())
        }
        history_references = {
            item['reference']
            for item in view._inbound_items(openid, timezone.now(), history=True)
            + view._outbound_items(openid, timezone.now(), history=True)
        }

        self.assertIn('ASN-DASHBOARD-IN-PROGRESS', active_references)
        self.assertIn('DN-DASHBOARD-IN-PROGRESS', active_references)
        self.assertNotIn('ASN-DASHBOARD-IN-PROGRESS', history_references)
        self.assertNotIn('DN-DASHBOARD-IN-PROGRESS', history_references)
        self.assertIn('ASN-DASHBOARD-COMPLETED', history_references)
        self.assertIn('DN-DASHBOARD-COMPLETED', history_references)
        self.assertIn('DN-DASHBOARD-CANCELLED', history_references)

    def test_format_item_accepts_naive_eta(self):
        now = timezone.now()
        item = OperationsBoardViewSet()._format_item({
            'category': 'inbound',
            'reference': 'ASN-DASHBOARD-ETA-01',
            'operation': 'Await Arrival',
            'location': 'Stage',
            'action_route': 'asn',
            'status': 1,
            'business_status': 'PRE_ARRIVAL',
            'quantity': 1,
            'progress_quantity': 0,
            'blocked': False,
            'planned': True,
            'timestamp': now,
            'eta': now.replace(tzinfo=None),
            'history': False,
        }, now)

        self.assertEqual(item['eta'], now.strftime('%m-%d %H:%M'))

    def test_format_item_exposes_eta_urgency_and_countdown(self):
        now = timezone.now()
        view = OperationsBoardViewSet()

        def format_eta(eta=None, actual_arrival_at=None):
            return view._format_item({
                'category': 'inbound',
                'reference': 'ASN-DASHBOARD-ETA-STATE',
                'operation': 'Await Arrival',
                'location': 'Stage',
                'action_route': 'asn',
                'status': 1,
                'business_status': 'PRE_ARRIVAL',
                'quantity': 1,
                'progress_quantity': 0,
                'blocked': False,
                'planned': True,
                'timestamp': now,
                'eta': eta,
                'actual_arrival_at': actual_arrival_at,
                'history': False,
            }, now)

        self.assertEqual(format_eta()['eta_status'], 'NOT_PROVIDED')
        self.assertEqual(format_eta(now + timedelta(minutes=90))['eta_status'], 'DUE_SOON')
        self.assertEqual(format_eta(now + timedelta(minutes=90))['minutes_to_eta'], 90)
        self.assertEqual(format_eta(now + timedelta(minutes=180))['eta_status'], 'ON_TIME')
        self.assertEqual(format_eta(now - timedelta(minutes=15))['eta_status'], 'OVERDUE')
        self.assertEqual(format_eta(now - timedelta(minutes=15))['minutes_to_eta'], -15)
        self.assertEqual(format_eta(now - timedelta(minutes=15), actual_arrival_at=now)['eta_status'], 'ARRIVED')

# Create your tests here.
