from types import SimpleNamespace

from django.test import TestCase
from rest_framework.exceptions import APIException

from asnserial.models import SourceEvidence

from .models import ListModel
from .serializers import GoodsSourceImportSerializer
from .units import unit_volume_cubic_meters, weight_to_kg
from .views import SourceImportView


class GoodsSourceImportTests(TestCase):
    def setUp(self):
        self.openid = 'goods-source-test'
        self.evidence = SourceEvidence.objects.create(
            openid=self.openid,
            source_type=SourceEvidence.EMAIL,
            operation='master_data.configure',
            message_id='message-1',
            content_hash='hash-1',
        )

    def request(self, data, openid=None):
        return SimpleNamespace(
            auth=SimpleNamespace(
                openid=openid or self.openid,
                staff_name='test-admin',
            ),
            user=SimpleNamespace(is_authenticated=True),
            META={},
            data=data,
        )

    def test_us_volume_and_weight_are_converted_for_transaction_totals(self):
        self.assertAlmostEqual(
            unit_volume_cubic_meters(44, 44, 71, 'in/lb'),
            2.2525,
            places=4,
        )
        goods = SimpleNamespace(goods_weight=100, measurement_unit='in/lb')
        self.assertAlmostEqual(weight_to_kg(goods), 45.3592, places=4)

    def test_source_serializer_allows_missing_optional_master_data(self):
        serializer = GoodsSourceImportSerializer(data={
            'goods_code': 'SKU-EMPTY-01',
            'source_evidence_id': self.evidence.id,
        })
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_source_import_creates_and_reuses_same_source_record(self):
        payload = {
            'items': [{
                'goods_code': 'SKU-US-01',
                'goods_supplier': 'Delta',
                'goods_weight': 100,
                'goods_w': 44,
                'goods_d': 44,
                'goods_h': 71,
                'goods_unit': '',
                'measurement_unit': 'in/lb',
                'source_evidence_id': self.evidence.id,
                'source_note': 'Source: 100 lb; normalized write: 100 lb',
            }],
        }
        response = SourceImportView().create(self.request(payload))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['created_count'], 1)
        item = ListModel.objects.get(goods_code='SKU-US-01', openid=self.openid)
        self.assertEqual(item.goods_supplier, 'Delta')
        self.assertEqual(item.measurement_unit, 'in/lb')
        self.assertEqual(item.source_evidence_id, self.evidence.id)
        self.assertEqual(item.goods_class, '')
        self.assertEqual(self.evidence.__class__.objects.get(id=self.evidence.id).status, SourceEvidence.USED)

        response = SourceImportView().create(self.request(payload))
        self.assertEqual(response.data['created_count'], 0)
        self.assertEqual(response.data['reused_count'], 1)
        self.assertEqual(ListModel.objects.filter(openid=self.openid).count(), 1)

    def test_source_import_rejects_evidence_from_another_tenant(self):
        payload = {
            'goods_code': 'SKU-FOREIGN-01',
            'source_evidence_id': self.evidence.id,
        }
        with self.assertRaises(APIException):
            SourceImportView().create(self.request(payload, openid='other-tenant'))
