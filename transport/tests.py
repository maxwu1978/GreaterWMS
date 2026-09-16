from types import SimpleNamespace

from django.test import TestCase
from rest_framework.exceptions import NotFound, ValidationError

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

    def list_orders(self, **params):
        request = self.request({})
        request.GET = params
        request.query_params = params
        request.build_absolute_uri = lambda: 'http://testserver/transport/orders/'
        view = TransportOrderListView()
        view.request = request
        return view.get(request)

    def call(self, view_class, data):
        request = self.request(data)
        view = view_class()
        view.request = request
        return view.post(request)

    def test_transport_list_paginates_filtered_tenant_orders(self):
        for number in range(201):
            TransportOrder.objects.create(
                transport_no='TR-PAGE-%03d' % number,
                direction=TransportOrder.INBOUND,
                openid=self.openid,
            )
        TransportOrder.objects.create(
            transport_no='TR-OTHER-TENANT',
            direction=TransportOrder.INBOUND,
            openid='other-tenant',
        )

        first_page = self.list_orders(page='1', max_page='200')
        second_page = self.list_orders(page='2', max_page='200')
        capped_page = self.list_orders(page='1', max_page='999')
        returned = [
            row['transport_no']
            for row in first_page.data['results'] + second_page.data['results']
        ]

        self.assertEqual(first_page.data['count'], 201)
        self.assertEqual(len(first_page.data['results']), 200)
        self.assertEqual(len(capped_page.data['results']), 200)
        self.assertIsNotNone(first_page.data['next'])
        self.assertIsNone(first_page.data['previous'])
        self.assertEqual(len(second_page.data['results']), 1)
        self.assertIsNone(second_page.data['next'])
        self.assertIsNotNone(second_page.data['previous'])
        self.assertEqual(len(returned), 201)
        self.assertEqual(len(set(returned)), 201)
        self.assertNotIn('TR-OTHER-TENANT', returned)
        with self.assertRaises(NotFound):
            self.list_orders(page='invalid', max_page='200')

    def test_transport_list_returns_short_result_sets_and_transport_filter(self):
        for number in range(8):
            TransportOrder.objects.create(
                transport_no='TR-SHORT-%03d' % number,
                direction=TransportOrder.OUTBOUND,
                openid=self.openid,
            )
        TransportOrder.objects.create(
            transport_no='TR-SHORT-OTHER',
            direction=TransportOrder.OUTBOUND,
            openid='other-tenant',
        )

        response = self.list_orders()
        filtered = self.list_orders(transport_no='TR-SHORT-003', page='1', max_page='30')

        self.assertEqual(response.data['count'], 8)
        self.assertEqual(len(response.data['results']), 8)
        self.assertEqual(filtered.data['count'], 1)
        self.assertEqual(
            [row['transport_no'] for row in filtered.data['results']],
            ['TR-SHORT-003'],
        )

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
