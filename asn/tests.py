from types import SimpleNamespace

from django.test import TestCase
from rest_framework.exceptions import APIException, ValidationError

from supplier.models import ListModel as Supplier
from goods.models import ListModel as Goods
from staff.models import ListModel as Staff
from utils.my_exceptions import custom_exception_handler

from .models import AsnDetailModel, AsnListModel
from .services import asn_detail_reference_errors
from .views import AsnDetailViewSet, MoveToBinViewSet, _validate_asn_detail_payload


class AsnInputSafetyTests(TestCase):
    def setUp(self):
        self.openid = 'asn-input-test'
        self.asn = AsnListModel.objects.create(
            asn_code='ASN-TEST-01',
            asn_status=4,
            supplier='Customer A',
            creater='tester',
            bar_code='ASN-BAR-01',
            openid=self.openid,
        )
        self.detail = AsnDetailModel.objects.create(
            asn_code=self.asn.asn_code,
            asn_status=4,
            supplier=self.asn.supplier,
            goods_code='SKU-01',
            goods_desc='Test SKU',
            goods_qty=1,
            creater='tester',
            openid=self.openid,
        )
        Supplier.objects.create(
            supplier_name='Customer A',
            supplier_city='Dallas',
            supplier_address='Test address',
            supplier_contact='test',
            supplier_manager='test',
            creater='tester',
            openid=self.openid,
        )
        Goods.objects.create(
            goods_code='SKU-01',
            goods_desc='Test SKU',
            goods_supplier='Customer A',
            goods_weight=1,
            goods_w=1,
            goods_d=1,
            goods_h=1,
            unit_volume=1,
            goods_unit='EA',
            goods_class='TEST',
            goods_brand='TEST',
            goods_color='NA',
            goods_shape='BOX',
            goods_specs='TEST',
            goods_origin='US',
            goods_cost=1,
            goods_price=1,
            creater='tester',
            bar_code='SKU-01-BAR',
            openid=self.openid,
        )
        self.operator = Staff.objects.create(
            staff_name='inbound-operator',
            staff_type='Inbound',
            check_code=1234,
            openid=self.openid,
        )

    def request(self, data, operator='999999'):
        return SimpleNamespace(
            auth=SimpleNamespace(openid=self.openid),
            user=SimpleNamespace(is_authenticated=True),
            META={'HTTP_OPERATOR': str(operator)},
            data=data,
        )

    def test_asn_detail_create_rejects_missing_operator_without_traceback(self):
        request = self.request({
            'asn_code': self.asn.asn_code,
            'supplier': self.asn.supplier,
            'goods_code': ['SKU-01'],
            'goods_qty': [1],
        })
        view = AsnDetailViewSet()
        view.request = request
        view.action = 'create'

        with self.assertRaises(APIException) as raised:
            view.create(request)
        response = custom_exception_handler(raised.exception, {'request': request})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['detail'], 'Operator does not exist')

    def test_movetobin_rejects_asn_code_mismatch_as_client_error(self):
        request = self.request({
            'asn_code': 'ASN-WRONG',
            'goods_code': 'SKU-01',
            'qty': 1,
            'bin_name': 'A1-01',
            'driver': 'Tom',
        }, operator='1')
        view = MoveToBinViewSet()
        view.request = request
        view.action = 'create'
        view.get_object = lambda: AsnDetailModel.objects.get(id=self.detail.id)

        with self.assertRaises(APIException) as raised:
            view.create(request, self.detail.id)
        response = custom_exception_handler(raised.exception, {'request': request})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['detail'], 'Putaway ASN code does not match the selected ASN detail')

    def test_asn_detail_rejects_scalar_parallel_fields(self):
        with self.assertRaises(ValidationError) as raised:
            _validate_asn_detail_payload({
                'asn_code': 'ASN-TEST-01',
                'supplier': 'Customer A',
                'goods_code': 'SKU-01',
                'goods_qty': 1,
            })

        self.assertEqual(raised.exception.detail['goods_code'][0], 'Expected a non-empty list.')
        self.assertEqual(raised.exception.detail['goods_qty'][0], 'Expected a non-empty list.')

    def test_asn_detail_rejects_mismatched_parallel_fields(self):
        with self.assertRaises(ValidationError) as raised:
            _validate_asn_detail_payload({
                'asn_code': 'ASN-TEST-01',
                'supplier': 'Customer A',
                'goods_code': ['SKU-01', 'SKU-02'],
                'goods_qty': [1],
            })

        self.assertEqual(
            raised.exception.detail['goods_qty'][0],
            'Must contain the same number of entries as goods_code.',
        )

    def test_asn_detail_reference_errors_report_missing_sku_as_client_error(self):
        errors = asn_detail_reference_errors(
            self.openid,
            self.asn.asn_code,
            self.asn.supplier,
            ['SKU-MISSING'],
        )

        self.assertEqual(errors['goods_code'], ['SKU does not exist: SKU-MISSING.'])

    def test_asn_detail_create_rejects_missing_sku_before_inventory_write(self):
        request = self.request({
            'asn_code': self.asn.asn_code,
            'supplier': self.asn.supplier,
            'goods_code': ['SKU-MISSING'],
            'goods_qty': [1],
        }, operator=self.operator.id)
        view = AsnDetailViewSet()
        view.request = request
        view.action = 'create'

        with self.assertRaises(ValidationError) as raised:
            view.create(request)

        self.assertEqual(raised.exception.detail['goods_code'][0], 'SKU does not exist: SKU-MISSING.')
        self.assertFalse(AsnDetailModel.objects.filter(
            openid=self.openid,
            asn_code=self.asn.asn_code,
            goods_code='SKU-MISSING',
        ).exists())
