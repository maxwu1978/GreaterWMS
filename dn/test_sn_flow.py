from types import SimpleNamespace

from django.test import TestCase
from django.utils import timezone
from rest_framework.exceptions import APIException

from asnserial.models import AsnSerialRecord
from driver.models import DispatchListModel, ListModel as DriverModel
from staff.models import ListModel as StaffModel
from stock.models import StockBinModel, StockListModel
from staging.models import StagingAssignment
from transport.models import TransportOrder

from .models import DnDetailModel, DnListModel, DnSerialAllocation, PickingListModel
from .views import (
    DnDispatchViewSet,
    DnPODViewSet,
    _mark_picked_serials,
    _validate_pick_serials,
)


class SerialOutboundFlowTests(TestCase):
    def setUp(self):
        self.openid = 'dn-sn-flow-test'
        self.dn = DnListModel.objects.create(
            dn_code='DN-SN-001',
            dn_status=4,
            picking_mode=DnListModel.SN,
            customer='Customer A',
            creater='tester',
            bar_code='DN-SN-BAR',
            openid=self.openid,
        )
        self.detail = DnDetailModel.objects.create(
            dn_code=self.dn.dn_code,
            dn_status=4,
            customer=self.dn.customer,
            goods_code='SKU-SN-01',
            goods_desc='Serial SKU',
            goods_qty=1,
            picked_qty=1,
            creater='tester',
            openid=self.openid,
            requested_serials=['SN-001'],
        )
        DnSerialAllocation.objects.create(
            openid=self.openid,
            dn_code=self.dn.dn_code,
            goods_code=self.detail.goods_code,
            serial_number='SN-001',
            created_by='tester',
        )
        AsnSerialRecord.objects.create(
            openid=self.openid,
            asn_code='ASN-SN-001',
            goods_code=self.detail.goods_code,
            scanned_goods_code=self.detail.goods_code,
            serial_number='SN-001',
            status=AsnSerialRecord.ACCEPTED,
            is_received=True,
        )
        StockListModel.objects.create(
            goods_code=self.detail.goods_code,
            goods_desc='Serial SKU',
            goods_qty=1,
            picked_stock=1,
            openid=self.openid,
        )
        PickingListModel.objects.create(
            dn_code=self.dn.dn_code,
            bin_name='A1-01',
            goods_code=self.detail.goods_code,
            picked_qty=1,
            creater='tester',
            t_code='TX-SN-01',
            openid=self.openid,
        )
        StockBinModel.objects.create(
            bin_name='A1-01',
            goods_code=self.detail.goods_code,
            goods_desc='Serial SKU',
            goods_qty=1,
            picked_qty=1,
            bin_size='STD',
            bin_property='Normal',
            t_code='TX-SN-01',
            openid=self.openid,
            create_time=timezone.now(),
        )
        DriverModel.objects.create(
            driver_name='Tom',
            license_plate='SN-TRUCK',
            contact='N/A',
            creater='tester',
            openid=self.openid,
        )
        self.operator = StaffModel.objects.create(
            staff_name='Warehouse Operator',
            staff_type='Warehouse',
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
            META={'HTTP_OPERATOR': str(self.operator.id)},
            data=data,
        )

    def test_sn_must_be_scanned_before_dispatch_and_is_shipped_at_pod(self):
        request = self.request({'goodsData': [{'goods_code': self.detail.goods_code, 'serial_numbers': ['SN-001']}]})
        serials = _validate_pick_serials(self.openid, self.dn, request.data['goodsData'])
        _mark_picked_serials(self.openid, self.dn, serials)

        dispatch_request = self.request({'driver': 'Tom', 'staging_bin': 'STAGE-LEFT-01'})
        dispatch_view = DnDispatchViewSet()
        dispatch_view.request = dispatch_request
        dispatch_view.action = 'create'
        dispatch_view.get_object = lambda: DnListModel.objects.select_for_update().get(id=self.dn.id)
        response = dispatch_view.create(dispatch_request, self.dn.id)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            DnSerialAllocation.objects.get(serial_number='SN-001').status,
            DnSerialAllocation.IN_TRANSIT,
        )

        pod_request = self.request({
            'dn_code': self.dn.dn_code,
            'goodsData': [{
                'goods_code': self.detail.goods_code,
                'intransit_qty': 1,
            }],
        })
        pod_view = DnPODViewSet()
        pod_view.request = pod_request
        pod_view.action = 'create'
        pod_view.get_object = lambda: DnListModel.objects.select_for_update().get(id=self.dn.id)
        pod_response = pod_view.create(pod_request, self.dn.id)
        self.assertEqual(pod_response.status_code, 200)
        self.assertEqual(
            DnSerialAllocation.objects.get(serial_number='SN-001').status,
            DnSerialAllocation.SHIPPED,
        )
        self.assertEqual(
            DnDetailModel.objects.get(id=self.detail.id).shipped_serials,
            ['SN-001'],
        )

    def test_dispatch_rejects_a_ticket_sn_that_was_not_picked(self):
        dispatch_request = self.request({'driver': 'Tom', 'staging_bin': 'STAGE-LEFT-01'})
        dispatch_view = DnDispatchViewSet()
        dispatch_view.request = dispatch_request
        dispatch_view.action = 'create'
        dispatch_view.get_object = lambda: DnListModel.objects.select_for_update().get(id=self.dn.id)
        with self.assertRaises(APIException):
            dispatch_view.create(dispatch_request, self.dn.id)
        self.assertFalse(StagingAssignment.objects.filter(reference_code=self.dn.dn_code).exists())
        self.assertFalse(DispatchListModel.objects.filter(dn_code=self.dn.dn_code).exists())

    def test_transport_is_completed_with_outbound_pod(self):
        self.dn.transport_required = True
        self.dn.ship_to = 'Customer dock'
        self.dn.save(update_fields=['transport_required', 'ship_to', 'update_time'])
        serials = _validate_pick_serials(
            self.openid,
            self.dn,
            [{'goods_code': self.detail.goods_code, 'serial_numbers': ['SN-001']}],
        )
        _mark_picked_serials(self.openid, self.dn, serials)

        dispatch_request = self.request({'driver': 'Tom', 'staging_bin': 'STAGE-LEFT-01'})
        dispatch_view = DnDispatchViewSet()
        dispatch_view.request = dispatch_request
        dispatch_view.action = 'create'
        dispatch_view.get_object = lambda: DnListModel.objects.select_for_update().get(id=self.dn.id)
        dispatch_view.create(dispatch_request, self.dn.id)

        transport = TransportOrder.objects.get(openid=self.openid, reference_no=self.dn.dn_code)
        self.assertEqual(transport.driver_name, 'Tom')
        self.assertEqual(transport.status, TransportOrder.IN_TRANSIT)

        pod_request = self.request({
            'dn_code': self.dn.dn_code,
            'goodsData': [{
                'goods_code': self.detail.goods_code,
                'intransit_qty': 1,
            }],
        })
        pod_view = DnPODViewSet()
        pod_view.request = pod_request
        pod_view.action = 'create'
        pod_view.get_object = lambda: DnListModel.objects.select_for_update().get(id=self.dn.id)
        pod_view.create(pod_request, self.dn.id)
        transport.refresh_from_db()
        self.assertEqual(transport.status, TransportOrder.COMPLETED)
        self.assertEqual(transport.pod_reference, self.dn.dn_code)
