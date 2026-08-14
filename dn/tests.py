from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from rest_framework.exceptions import APIException, PermissionDenied, ValidationError

from driver.models import DispatchListModel, ListModel as Driver
from staff.models import ListModel as Staff
from stock.models import StockBinModel, StockListModel
from staging.models import StagingAssignment
from asnserial.models import AsnSerialRecord

from .models import DnDetailModel, DnListModel, DnSerialAllocation, PickingListModel
from .serializers import DNListGetSerializer
from .views import (
    DnCancelInTransitViewSet,
    DnDispatchViewSet,
    DnPODViewSet,
    _validate_outbound_detail_payload,
    _validate_outbound_serial_request,
)


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

    def request(self, data=None, operator_id=None, is_admin=False):
        return SimpleNamespace(
            auth=SimpleNamespace(
                openid=self.openid,
                is_admin=is_admin,
                staff_name='Admin Operator' if is_admin else 'Dispatch Operator',
            ),
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

    def pod(self, data=None):
        request = self.request(data)
        view = DnPODViewSet()
        view.request = request
        view.action = 'create'
        view.get_object = lambda: DnListModel.objects.get(id=self.dn.id)
        return view.create(request, self.dn.id)

    def cancel_intransit(self, data=None, is_admin=False):
        request = self.request(data, is_admin=is_admin)
        view = DnCancelInTransitViewSet()
        view.request = request
        view.action = 'create'
        view.get_object = lambda: DnListModel.objects.select_for_update().get(id=self.dn.id)
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
        dispatch = DispatchListModel.objects.get(openid=self.openid, dn_code=self.dn.dn_code)
        self.assertEqual(dispatch.staging_bin, 'STAGE-LEFT-01')
        self.assertEqual(
            StagingAssignment.objects.get(openid=self.openid, reference_code=self.dn.dn_code).status,
            StagingAssignment.ACTIVE,
        )
        summary = DNListGetSerializer(self.dn).data
        self.assertEqual(summary['dispatch_driver'], 'Tom')
        self.assertEqual(summary['staging_bin'], 'STAGE-LEFT-01')
        self.assertEqual(summary['staging_status'], 'Occupied')
        self.assertEqual(summary['sku_summary'], 'SKU-01 x 2')
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

    def test_pod_records_exception_and_releases_staging(self):
        self.dispatch({'driver': 'Tom', 'staging_bin': 'STAGE-RIGHT-01'})

        response = self.pod({
            'dn_code': self.dn.dn_code,
            'goodsData': [{
                'goods_code': 'SKU-01',
                'intransit_qty': 1,
                'delivery_damage_qty': 1,
                'delivery_note': 'One unit damaged on delivery',
            }],
        })

        self.assertEqual(response.status_code, 200)
        self.dn.refresh_from_db()
        detail = DnDetailModel.objects.get(openid=self.openid, dn_code=self.dn.dn_code)
        self.assertEqual(self.dn.dn_status, 6)
        self.assertEqual(detail.delivery_actual_qty, 1)
        self.assertEqual(detail.delivery_shortage_qty, 1)
        self.assertEqual(detail.delivery_damage_qty, 1)
        self.assertEqual(detail.delivery_note, 'One unit damaged on delivery')
        self.assertFalse(StagingAssignment.objects.filter(
            openid=self.openid,
            reference_code=self.dn.dn_code,
            status__in=(StagingAssignment.RESERVED, StagingAssignment.ACTIVE),
        ).exists())

    def test_pod_rejects_damage_above_actual_quantity(self):
        self.dispatch({'driver': 'Tom', 'staging_bin': 'STAGE-RIGHT-01'})

        with self.assertRaises(APIException) as raised:
            self.pod({
                'dn_code': self.dn.dn_code,
                'goodsData': [{
                    'goods_code': 'SKU-01',
                    'intransit_qty': 1,
                    'delivery_damage_qty': 2,
                    'delivery_note': 'Invalid damage quantity',
                }],
            })
        self.assertIn('between 0 and actual quantity', raised.exception.detail['detail'])
        self.dn.refresh_from_db()
        self.assertEqual(self.dn.dn_status, 5)

    def test_admin_can_cancel_intransit_and_release_staging(self):
        self.dispatch({'driver': 'Tom', 'staging_bin': 'STAGE-RIGHT-01'})

        response = self.cancel_intransit(
            {'cancellation_note': 'Carrier returned before delivery'},
            is_admin=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['released'], 1)
        self.assertEqual(response.data['cancelled_qty'], {'SKU-01': 2})
        self.dn.refresh_from_db()
        self.assertEqual(self.dn.dn_status, 7)
        self.assertEqual(self.dn.cancellation_note, 'Carrier returned before delivery')
        self.assertEqual(self.dn.canceled_by, 'Admin Operator')
        self.assertIsNotNone(self.dn.canceled_at)
        self.assertEqual(
            DnDetailModel.objects.get(openid=self.openid, dn_code=self.dn.dn_code).dn_status,
            7,
        )
        detail = DnDetailModel.objects.get(openid=self.openid, dn_code=self.dn.dn_code)
        self.assertEqual(detail.cancelled_qty, 2)
        self.assertEqual(detail.intransit_qty, 0)
        # Cancellation does not invent stock. A physical return must re-enter
        # through Receiving and Putaway before inventory is increased.
        self.assertEqual(
            StockListModel.objects.get(openid=self.openid, goods_code='SKU-01').goods_qty,
            1,
        )
        assignment = StagingAssignment.objects.get(openid=self.openid, reference_code=self.dn.dn_code)
        self.assertEqual(assignment.status, StagingAssignment.RELEASED)
        self.assertEqual(DNListGetSerializer(self.dn).data['delivery_exception'], 'Cancelled (2)')

        with self.assertRaises(APIException):
            self.cancel_intransit({'cancellation_note': 'Duplicate close'}, is_admin=True)

    def test_non_admin_cannot_cancel_intransit(self):
        self.dispatch({'driver': 'Tom', 'staging_bin': 'STAGE-LEFT-01'})

        with self.assertRaises(PermissionDenied):
            self.cancel_intransit({'cancellation_note': 'Not authorized'}, is_admin=False)

        self.dn.refresh_from_db()
        self.assertEqual(self.dn.dn_status, 5)
        self.assertTrue(StagingAssignment.objects.filter(
            openid=self.openid,
            reference_code=self.dn.dn_code,
            status=StagingAssignment.ACTIVE,
        ).exists())

    def test_cancel_intransit_requires_reason(self):
        self.dispatch({'driver': 'Tom', 'staging_bin': 'STAGE-LEFT-01'})

        with self.assertRaises(APIException) as raised:
            self.cancel_intransit({'cancellation_note': '  '}, is_admin=True)
        self.assertEqual(raised.exception.detail['detail'], 'A cancellation reason is required')
        self.dn.refresh_from_db()
        self.assertEqual(self.dn.dn_status, 5)

    def test_missing_operator_is_rejected_before_inventory_change(self):
        with self.assertRaises(APIException) as raised:
            self.dispatch(
                {'driver': 'Tom', 'staging_bin': 'STAGE-LEFT-01'},
                operator_id=999999,
            )
        self.assertEqual(raised.exception.detail['detail'], 'Operator does not exist')


class SerialAllocationSafetyTests(TestCase):
    def test_shipped_serial_cannot_be_allocated_to_another_delivery(self):
        openid = 'dn-serial-allocation-test'
        first = DnListModel.objects.create(
            dn_code='DN-FIRST-001',
            dn_status=6,
            picking_mode=DnListModel.SN,
            customer='Customer A',
            creater='tester',
            bar_code='DN-FIRST-BAR',
            openid=openid,
        )
        DnSerialAllocation.objects.create(
            openid=openid,
            dn_code=first.dn_code,
            goods_code='SKU-SN-01',
            serial_number='SN-SHIPPED-001',
            status=DnSerialAllocation.SHIPPED,
            created_by='tester',
        )
        second = DnListModel.objects.create(
            dn_code='DN-SECOND-001',
            dn_status=4,
            picking_mode=DnListModel.SN,
            customer='Customer A',
            creater='tester',
            bar_code='DN-SECOND-BAR',
            openid=openid,
        )
        DnDetailModel.objects.create(
            dn_code=second.dn_code,
            dn_status=4,
            customer='Customer A',
            goods_code='SKU-SN-01',
            goods_desc='Serial SKU',
            goods_qty=1,
            requested_serials=['SN-SHIPPED-001'],
            creater='tester',
            openid=openid,
        )
        AsnSerialRecord.objects.create(
            openid=openid,
            asn_code='ASN-SN-001',
            goods_code='SKU-SN-01',
            scanned_goods_code='SKU-SN-01',
            serial_number='SN-SHIPPED-001',
            status=AsnSerialRecord.ACCEPTED,
            is_received=True,
        )
        with self.assertRaises(APIException) as raised:
            _validate_outbound_serial_request(
                openid,
                second,
                ['SKU-SN-01'],
                [1],
                [['SN-SHIPPED-001']],
            )
        self.assertIn('already allocated', raised.exception.detail['detail'])


class OutboundPayloadValidationTests(TestCase):
    def test_scalar_parallel_fields_are_rejected_before_legacy_indexing(self):
        with self.assertRaises(ValidationError) as raised:
            _validate_outbound_detail_payload({
                'dn_code': 'DN-TEST-01',
                'customer': 'Customer A',
                'goods_code': 'SKU-01',
                'goods_qty': 1,
            })

        self.assertEqual(raised.exception.detail['goods_code'][0], 'Expected a non-empty list.')
        self.assertEqual(raised.exception.detail['goods_qty'][0], 'Expected a non-empty list.')

    def test_parallel_fields_must_have_matching_lengths(self):
        with self.assertRaises(ValidationError) as raised:
            _validate_outbound_detail_payload({
                'dn_code': 'DN-TEST-01',
                'customer': 'Customer A',
                'goods_code': ['SKU-01', 'SKU-02'],
                'goods_qty': [1],
            })

        self.assertEqual(
            raised.exception.detail['goods_qty'][0],
            'Must contain the same number of entries as goods_code.',
        )

    def test_parallel_fields_reject_non_integer_quantity(self):
        with self.assertRaises(ValidationError) as raised:
            _validate_outbound_detail_payload({
                'dn_code': 'DN-TEST-01',
                'customer': 'Customer A',
                'goods_code': ['SKU-01'],
                'goods_qty': ['two'],
            })

        self.assertEqual(raised.exception.detail['goods_qty'][0], 'Entry 0 must be an integer.')
