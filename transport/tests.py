from types import SimpleNamespace

from django.test import TestCase
from rest_framework.exceptions import ValidationError

from driver.models import ListModel as DriverModel

from .models import TransportOrder
from .views import (
    TransportAssignView,
    TransportOrderListView,
    TransportTransitionView,
)


class TransportFlowTests(TestCase):
    def setUp(self):
        self.openid = 'transport-flow-test'
        DriverModel.objects.create(
            driver_name='Tom',
            license_plate='TRUCK-01',
            contact='N/A',
            creater='tester',
            openid=self.openid,
        )

    def request(self, data):
        return SimpleNamespace(
            auth=SimpleNamespace(
                openid=self.openid,
                is_admin=True,
                staff_name='Logistics',
                staff_type='Logistics',
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

    def test_transport_requires_assignment_and_pod_for_completion(self):
        created = self.call(TransportOrderListView, {
            'direction': TransportOrder.OUTBOUND,
            'reference_type': 'DN',
            'reference_no': 'DN-001',
            'customer': 'Customer A',
            'delivery_location': 'Customer dock',
        })
        transport_no = created.data['transport_no']
        self.call(TransportAssignView, {'transport_no': transport_no, 'driver_name': 'Tom'})
        self.call(TransportTransitionView, {'transport_no': transport_no, 'status': TransportOrder.IN_TRANSIT})
        self.call(TransportTransitionView, {'transport_no': transport_no, 'status': TransportOrder.ARRIVED})
        with self.assertRaises(ValidationError):
            self.call(TransportTransitionView, {'transport_no': transport_no, 'status': TransportOrder.COMPLETED})
        completed = self.call(TransportTransitionView, {
            'transport_no': transport_no,
            'status': TransportOrder.COMPLETED,
            'pod_reference': 'POD-001',
        })
        self.assertEqual(completed.data['status'], TransportOrder.COMPLETED)

    def test_transport_cancellation_requires_a_reason(self):
        created = self.call(TransportOrderListView, {'direction': TransportOrder.INBOUND})
        transport_no = created.data['transport_no']
        with self.assertRaises(ValidationError):
            self.call(TransportTransitionView, {
                'transport_no': transport_no,
                'status': TransportOrder.CANCELLED,
            })
        canceled = self.call(TransportTransitionView, {
            'transport_no': transport_no,
            'status': TransportOrder.CANCELLED,
            'note': 'Customer canceled the pickup',
        })
        self.assertEqual(canceled.data['status'], TransportOrder.CANCELLED)
