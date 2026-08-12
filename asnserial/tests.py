from types import SimpleNamespace

from django.db import IntegrityError
from django.test import TestCase
from rest_framework.exceptions import APIException

from asn.models import AsnDetailModel, AsnListModel

from .models import AsnSerialRecord, PackListDocument, PackListLine
from .views import _create_pack_list, _scan, _summary


class PackListWorkflowTests(TestCase):
    def setUp(self):
        self.openid = 'test-tenant'
        self.asn_code = 'ASN-TEST-01'
        AsnListModel.objects.create(
            asn_code=self.asn_code,
            asn_status=1,
            supplier='Test Customer',
            creater='tester',
            bar_code='BAR-TEST-01',
            openid=self.openid,
            transportation_fee={},
        )
        AsnDetailModel.objects.create(
            asn_code=self.asn_code,
            asn_status=1,
            supplier='Test Customer',
            goods_code='702-S',
            goods_desc='Test SKU',
            goods_qty=2,
            creater='tester',
            openid=self.openid,
        )

    def request(self):
        return SimpleNamespace(
            auth=SimpleNamespace(openid=self.openid),
            META={},
        )

    def rows(self):
        return [{
            'goods_code': '702-S',
            'customer_goods_code': 'CUSTOMER-702',
            'customer_ssku': 'S-702',
            'package_type': 'PKG-01',
            'serial_number': '',
            'goods_qty': 2,
            'total_qty': 2,
            'goods_desc': 'Test SKU',
            'goods_weight': 10,
            'goods_volume': 1,
            'source_row': 2,
        }]

    def test_pack_list_import_is_one_current_record_and_idempotent(self):
        document, batch, created = _create_pack_list(
            self.openid,
            self.request(),
            self.asn_code,
            self.rows(),
            content_hash='a' * 64,
            package_qty=2,
        )
        self.assertTrue(created)
        self.assertIsNotNone(batch)
        same, no_batch, was_created = _create_pack_list(
            self.openid,
            self.request(),
            self.asn_code,
            self.rows(),
            content_hash='a' * 64,
            package_qty=2,
        )
        self.assertEqual(document.id, same.id)
        self.assertIsNone(no_batch)
        self.assertFalse(was_created)
        self.assertEqual(PackListDocument.objects.filter(is_current=True).count(), 1)
        self.assertEqual(PackListLine.objects.filter(pack_list=document, is_current=True).count(), 1)

        with self.assertRaises(APIException) as error:
            _create_pack_list(
                self.openid,
                self.request(),
                self.asn_code,
                self.rows(),
                content_hash='b' * 64,
                package_qty=2,
            )
        self.assertEqual(error.exception.detail['code'], 'PACK_LIST_REPLACE_REQUIRED')

    def test_summary_exposes_pending_pack_list_reconciliation(self):
        detail = AsnDetailModel.objects.get(asn_code=self.asn_code, openid=self.openid)
        detail.goods_actual_qty = 2
        detail.save(update_fields=['goods_actual_qty'])
        _create_pack_list(
            self.openid,
            self.request(),
            self.asn_code,
            self.rows(),
            content_hash='a' * 64,
            package_qty=2,
        )

        summary = _summary(self.openid, self.asn_code)
        row = summary['reconciliation_rows'][0]

        self.assertEqual(summary['reconciliation_status'], 'REVIEW')
        self.assertEqual(summary['customer_sn_status'], 'NOT_PROVIDED')
        self.assertEqual(row['goods_code'], '702-S')
        self.assertEqual(row['customer_goods_code'], 'CUSTOMER-702')
        self.assertEqual(row['pack_list_qty'], 2)
        self.assertEqual(row['received_qty'], 2)
        self.assertEqual(row['accepted_qty'], 2)
        self.assertEqual(row['variance'], 0)
        self.assertEqual(row['open_exception_count'], 0)
        self.assertEqual(row['result'], 'REVIEW')
        self.assertEqual(summary['receiving_summary']['status'], 'PASSED')

    def test_summary_marks_reconciliation_exception_for_quantity_variance(self):
        detail = AsnDetailModel.objects.get(asn_code=self.asn_code, openid=self.openid)
        detail.goods_actual_qty = 1
        detail.save(update_fields=['goods_actual_qty'])
        _create_pack_list(
            self.openid,
            self.request(),
            self.asn_code,
            self.rows(),
            content_hash='a' * 64,
            package_qty=2,
        )

        summary = _summary(self.openid, self.asn_code)

        self.assertEqual(summary['reconciliation_status'], 'EXCEPTION')
        self.assertEqual(summary['reconciliation_rows'][0]['variance'], -1)
        self.assertEqual(summary['reconciliation_rows'][0]['result'], 'EXCEPTION')

    def test_archived_pack_list_does_not_compete_with_current_record(self):
        current = PackListDocument.objects.create(
            openid=self.openid,
            asn_code=self.asn_code,
            content_hash='c' * 64,
            is_current=True,
        )
        archived = PackListDocument.objects.create(
            openid=self.openid,
            asn_code=self.asn_code,
            content_hash='d' * 64,
            is_current=False,
            status=PackListDocument.ARCHIVED,
        )
        self.assertEqual(current.asn_code, archived.asn_code)
        with self.assertRaises(IntegrityError):
            PackListDocument.objects.create(
                openid=self.openid,
                asn_code=self.asn_code,
                content_hash='e' * 64,
                is_current=True,
            )

    def test_explicit_replace_reuses_current_document_and_archives_old_lines(self):
        document, _, _ = _create_pack_list(
            self.openid,
            self.request(),
            self.asn_code,
            self.rows(),
            content_hash='a' * 64,
            package_qty=2,
        )
        replacement_rows = self.rows()
        replacement_rows[0]['customer_goods_code'] = 'CUSTOMER-702-REV2'
        replaced, batch, created = _create_pack_list(
            self.openid,
            self.request(),
            self.asn_code,
            replacement_rows,
            content_hash='b' * 64,
            package_qty=2,
            replace=True,
        )
        self.assertFalse(created)
        self.assertIsNotNone(batch)
        self.assertEqual(document.id, replaced.id)
        self.assertEqual(replaced.version, 2)
        self.assertEqual(PackListDocument.objects.filter(is_current=True).count(), 1)
        self.assertEqual(PackListLine.objects.filter(pack_list=document, is_current=True).count(), 1)
        self.assertEqual(PackListLine.objects.filter(pack_list=document, is_current=False).count(), 1)

    def test_pack_list_cannot_be_replaced_after_physical_receiving_started(self):
        rows = self.rows()
        rows[0]['serial_number'] = 'SN-702-001'
        _create_pack_list(
            self.openid,
            self.request(),
            self.asn_code,
            rows,
            content_hash='a' * 64,
            package_qty=2,
        )
        _scan(self.openid, self.request(), self.asn_code, '702-S', 'SN-702-001')
        self.assertTrue(AsnSerialRecord.objects.get(serial_number='SN-702-001').is_received)
        with self.assertRaises(APIException) as error:
            _create_pack_list(
                self.openid,
                self.request(),
                self.asn_code,
                self.rows(),
                content_hash='b' * 64,
                package_qty=2,
                replace=True,
            )
        self.assertIn('cannot be replaced', str(error.exception.detail['detail']))

    def test_damaged_receiving_scan_is_open_exception_until_resolved(self):
        rows = self.rows()
        rows[0]['serial_number'] = 'SN-702-002'
        _create_pack_list(
            self.openid,
            self.request(),
            self.asn_code,
            rows,
            content_hash='a' * 64,
            package_qty=2,
        )
        record, _ = _scan(
            self.openid,
            self.request(),
            self.asn_code,
            '702-S',
            'SN-702-002',
            damaged=True,
            row={'note': 'Packaging damaged during receiving'},
        )
        self.assertEqual(record.status, AsnSerialRecord.DAMAGED)
        self.assertEqual(record.note, 'Packaging damaged during receiving')
        self.assertFalse(_summary(self.openid, self.asn_code)['ready_for_putaway'])

    def test_open_quantity_exception_is_not_ready_for_putaway(self):
        detail = AsnDetailModel.objects.get(asn_code=self.asn_code, openid=self.openid)
        detail.goods_actual_qty = 1
        detail.goods_shortage_qty = 1
        detail.save(update_fields=['goods_actual_qty', 'goods_shortage_qty'])
        summary = _summary(self.openid, self.asn_code)
        self.assertEqual(summary['total_quantity_exceptions'], 1)
        self.assertFalse(summary['ready_for_putaway'])

    def test_resolved_quantity_exception_can_be_ready_for_putaway(self):
        detail = AsnDetailModel.objects.get(asn_code=self.asn_code, openid=self.openid)
        detail.goods_actual_qty = 1
        detail.goods_shortage_qty = 1
        detail.exception_resolved = True
        detail.save(update_fields=['goods_actual_qty', 'goods_shortage_qty', 'exception_resolved'])
        summary = _summary(self.openid, self.asn_code)
        self.assertEqual(summary['total_quantity_exceptions'], 0)
        self.assertTrue(summary['ready_for_putaway'])
