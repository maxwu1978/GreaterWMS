from io import BytesIO
from types import SimpleNamespace

from django.db import IntegrityError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone
from openpyxl import Workbook
from rest_framework.exceptions import APIException

from asn.models import AsnDetailModel, AsnListModel
from asn.serializers import ASNListGetSerializer
from binset.models import ListModel as Bin
from driver.models import ListModel as Driver
from stock.models import StockBinModel, StockListModel
from staff.models import ListModel as Staff

from .models import (
    ACCEPT_FOR_PUTAWAY,
    HOLD_QUARANTINE,
    REPAIR_REWORK,
    REJECT_RETURN,
    AsnSerialRecord,
    PackListDocument,
    PackListImportBatch,
    PackListLine,
)
from .views import (
    SerialExceptionResolveView,
    SerialExceptionMoveView,
    AgentCommandPreviewView,
    PackListPreviewView,
    SerialImportPreviewView,
    _create_pack_list,
    _receiving_started,
    _scan,
    _serial_rows_from_workbook,
    _summary,
)
from .agent import complete_preview, consume_preview, create_preview, request_payload


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

    def agent_request(self, data=None, operator_id=None):
        if operator_id is None:
            operator_id = Staff.objects.create(
                openid=self.openid,
                staff_name='Inbound Operator',
                staff_type='Inbound',
            ).id
        return SimpleNamespace(
            auth=SimpleNamespace(openid=self.openid),
            META={
                'HTTP_X_AGENT_CLIENT': 'greaterwms-cli',
                'HTTP_OPERATOR': str(operator_id),
            },
            data=data or {},
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

    def workbook_upload(self, headers, rows):
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(headers)
        for row in rows:
            sheet.append(row)
        payload = BytesIO()
        workbook.save(payload)
        return SimpleUploadedFile(
            'inbound-smoke.xlsx',
            payload.getvalue(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )

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

    def test_receiving_status_blocks_pack_list_replacement_before_quantity_is_entered(self):
        asn = AsnListModel.objects.get(asn_code=self.asn_code, openid=self.openid)
        asn.asn_status = 3
        asn.save(update_fields=['asn_status'])

        self.assertTrue(_receiving_started(self.openid, self.asn_code))

    def test_missing_expected_serial_cannot_be_accepted_for_putaway(self):
        record = AsnSerialRecord.objects.create(
            openid=self.openid,
            asn_code=self.asn_code,
            goods_code='702-S',
            serial_number='SN-MISSING',
            is_expected=True,
            is_received=False,
            status=AsnSerialRecord.EXPECTED,
        )
        request = self.request()
        request.data = {
            'id': record.id,
            'action': ACCEPT_FOR_PUTAWAY,
            'note': 'Incorrectly attempted to bypass missing SN',
        }

        with self.assertRaises(APIException) as error:
            SerialExceptionResolveView().post(request)

        self.assertEqual(error.exception.detail['code'], 'MISSING_SN_NOT_PUTAWAY_ELIGIBLE')

    def test_resolved_received_serial_exception_moves_stock_and_releases_staging(self):
        asn = AsnListModel.objects.get(asn_code=self.asn_code, openid=self.openid)
        asn.asn_status = 4
        asn.save(update_fields=['asn_status'])
        detail = AsnDetailModel.objects.get(asn_code=self.asn_code, openid=self.openid)
        detail.asn_status = 4
        detail.goods_actual_qty = 1
        detail.sorted_qty = 0
        detail.save(update_fields=['asn_status', 'goods_actual_qty', 'sorted_qty'])
        StockListModel.objects.create(
            openid=self.openid,
            goods_code='702-S',
            goods_desc='Test SKU',
            goods_qty=1,
            sorted_stock=1,
        )
        Bin.objects.create(
            openid=self.openid,
            bin_name='QC-HOLD-01',
            bin_size='STD',
            bin_property='Holding',
            location_role='STORAGE',
            staging_flow='NONE',
            creater='tester',
            bar_code='QC-HOLD-01',
        )
        record = AsnSerialRecord.objects.create(
            openid=self.openid,
            asn_code=self.asn_code,
            goods_code='702-S',
            serial_number='SN-HOLD-001',
            is_expected=True,
            is_received=True,
            status=AsnSerialRecord.DAMAGED,
            exception_resolved=True,
            exception_resolution_action=HOLD_QUARANTINE,
            exception_resolution_location='QC-HOLD-01',
        )
        request = self.request()
        request.data = {'id': record.id, 'bin_name': 'QC-HOLD-01'}

        response = SerialExceptionMoveView().post(request)

        self.assertEqual(response.data['destination_bin'], 'QC-HOLD-01')
        record.refresh_from_db()
        detail.refresh_from_db()
        asn.refresh_from_db()
        stock = StockListModel.objects.get(openid=self.openid, goods_code='702-S')
        self.assertTrue(record.exception_moved)
        self.assertEqual(detail.sorted_qty, 1)
        self.assertEqual(detail.asn_status, 5)
        self.assertEqual(asn.asn_status, 5)
        self.assertEqual(stock.sorted_stock, 0)
        self.assertEqual(stock.onhand_stock, 1)
        self.assertEqual(StockBinModel.objects.get(goods_code='702-S').goods_qty, 1)

    def test_pack_list_defaults_to_ai_agent_source_and_audits_batch_source(self):
        document, batch, created = _create_pack_list(
            self.openid,
            self.request(),
            self.asn_code,
            self.rows(),
            content_hash='f' * 64,
        )

        self.assertTrue(created)
        self.assertEqual(document.source_type, 'AI_AGENT')
        self.assertEqual(batch.source_type, 'AI_AGENT')

    def test_agent_preview_token_is_payload_bound_and_idempotent(self):
        request = self.agent_request()
        preview = create_preview(
            request,
            'packlist.confirm',
            {'id': 123},
            resource_id='123',
        )
        execute_request = self.agent_request({
            'id': 123,
            'confirmation_token': preview['confirmation_token'],
            'idempotency_key': 'packlist-confirm-123-1',
        }, operator_id=request.META['HTTP_OPERATOR'])
        command, replay = consume_preview(
            execute_request,
            'packlist.confirm',
            request_payload(execute_request),
            resource_id='123',
        )
        self.assertIsNone(replay)
        complete_preview(command, {'detail': 'success'})

        replay_command, replay = consume_preview(
            execute_request,
            'packlist.confirm',
            request_payload(execute_request),
            resource_id='123',
        )
        self.assertEqual(replay, {'detail': 'success'})
        self.assertEqual(replay_command.id, command.id)

    def test_outbound_role_can_confirm_outbound_preview(self):
        operator = Staff.objects.create(
            openid=self.openid,
            staff_name='Outbound Operator',
            staff_type='Outbound',
        )
        payload = {
            'customer': 'Test Customer',
            'creater': 'Outbound Operator',
        }
        preview_request = self.agent_request(operator_id=operator.id)
        preview = create_preview(preview_request, 'outbound.create', payload)
        execute_request = self.agent_request({
            **payload,
            'confirmation_token': preview['confirmation_token'],
            'idempotency_key': 'outbound-create-test-1',
        }, operator_id=operator.id)

        command, replay = consume_preview(
            execute_request,
            'outbound.create',
            request_payload(execute_request),
        )
        self.assertIsNone(replay)
        complete_preview(command, {'detail': 'success'})

    def test_invalid_agent_token_is_a_client_error(self):
        request = self.agent_request({
            'id': 123,
            'confirmation_token': 'invalid-token',
            'idempotency_key': 'packlist-confirm-invalid-1',
        })

        with self.assertRaises(Exception) as raised:
            consume_preview(
                request,
                'packlist.confirm',
                request_payload(request),
                resource_id='123',
            )

        self.assertEqual(raised.exception.status_code, 400)

    def test_putaway_preview_reuses_final_putaway_gates(self):
        asn = AsnListModel.objects.get(asn_code=self.asn_code, openid=self.openid)
        asn.asn_status = 4
        asn.save(update_fields=['asn_status'])
        detail = AsnDetailModel.objects.get(asn_code=self.asn_code, openid=self.openid)
        detail.asn_status = 4
        detail.goods_actual_qty = 2
        detail.sorted_qty = 2
        detail.save(update_fields=['asn_status', 'goods_actual_qty', 'sorted_qty'])
        Driver.objects.create(
            openid=self.openid,
            driver_name='Tom',
            license_plate='TEST-001',
            contact='555-0001',
            creater='tester',
        )
        Bin.objects.create(
            openid=self.openid,
            bin_name='A1-01',
            bin_size='STD',
            bin_property='Normal',
            location_role='STORAGE',
            staging_flow='NONE',
            creater='tester',
            bar_code='A1-01',
        )
        StockListModel.objects.create(
            openid=self.openid,
            goods_code='702-S',
            goods_desc='Test SKU',
            goods_qty=2,
            sorted_stock=0,
        )
        request = self.agent_request({
            'operation': 'asn.putaway',
            'resource_id': str(detail.id),
            'asn_code': self.asn_code,
            'payload': {
                'asn_code': self.asn_code,
                'goods_code': '702-S',
                'qty': 1,
                'bin_name': 'A1-01',
                'putaway_driver': 'Tom',
            },
        })

        with self.assertRaises(Exception) as raised:
            AgentCommandPreviewView().post(request)

        self.assertEqual(raised.exception.status_code, 400)
        self.assertIn('remaining received quantity', str(raised.exception.detail))

    def test_pack_list_preview_returns_client_error_for_unknown_sku(self):
        request = self.request()
        request.data = {'asn_code': self.asn_code}
        request.FILES = {
            'file': self.workbook_upload(['SKU', 'Item Qty'], [['UNKNOWN-SKU', 1]]),
        }

        with self.assertRaises(Exception) as raised:
            PackListPreviewView().post(request)

        self.assertEqual(raised.exception.status_code, 400)
        self.assertIn('Goods Code is not part of this ASN', str(raised.exception.detail))

    def test_inspection_preview_returns_client_error_for_unscoped_scan_sheet(self):
        request = self.request()
        request.data = {'asn_code': self.asn_code}
        request.FILES = {
            'file': self.workbook_upload(['SKU#', 'SN#'], [['702-S', 'SN-001']]),
        }

        with self.assertRaises(Exception) as raised:
            SerialImportPreviewView().post(request, inspection=True)

        self.assertEqual(raised.exception.status_code, 400)
        self.assertIn('inbound_po or shipout_ref', str(raised.exception.detail))

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

    def test_acceptance_workbook_reads_matching_rows_across_sheets_and_sections(self):
        workbook = Workbook()
        first = workbook.active
        first.title = 'Scan'
        first.append(['Inbound PO#', 'SKU#', 'SN#'])
        first.append(['PO-001', '702-S', 'SN-001'])
        first.append(['PO-002', '702-S', 'SN-002'])
        first.append(['SKU#', 'SN#', 'Result'])
        first.append(['702-S', 'SN-003', 'PASS'])
        second = workbook.create_sheet('Verification')
        second.append(['SKU', 'Serial Number', 'Status'])
        second.append(['702-S', 'SN-004', 'PASS'])
        payload = BytesIO()
        workbook.save(payload)

        rows = _serial_rows_from_workbook(payload.getvalue(), inbound_po='PO-001')

        self.assertEqual([(row['sheet'], row['row_number']) for row in rows], [('Scan', 2)])

    def test_acceptance_workbook_returns_no_rows_for_nonmatching_filter(self):
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(['Inbound PO#', 'SKU#', 'SN#'])
        sheet.append(['PO-001', '702-S', 'SN-001'])
        payload = BytesIO()
        workbook.save(payload)

        rows = _serial_rows_from_workbook(payload.getvalue(), inbound_po='PO-MISSING')

        self.assertEqual(rows, [])

    def test_imported_qc_batch_cannot_report_passed_or_ready(self):
        detail = AsnDetailModel.objects.get(asn_code=self.asn_code, openid=self.openid)
        detail.goods_actual_qty = 2
        detail.save(update_fields=['goods_actual_qty'])
        PackListImportBatch.objects.create(
            openid=self.openid,
            asn_code=self.asn_code,
            import_type=PackListImportBatch.RECEIVING_ACCEPTANCE,
            status=PackListImportBatch.IMPORTED,
            row_count=2,
            matched_count=2,
        )

        summary = _summary(self.openid, self.asn_code)

        self.assertEqual(summary['qc_status'], 'PARTIAL')
        self.assertEqual(summary['receiving_summary']['status'], 'REVIEW')
        self.assertTrue(summary['qc_import_incomplete'])
        self.assertFalse(summary['qc_complete'])
        self.assertFalse(summary['ready_for_putaway'])

    def test_asn_serializer_handles_missing_pack_list(self):
        asn = AsnListModel.objects.get(asn_code=self.asn_code, openid=self.openid)

        data = ASNListGetSerializer(asn, context={}).data

        self.assertEqual(data['pack_list_status'], 'NOT_RECEIVED')
        self.assertEqual(data['serial_acceptance']['status'], 'NOT_IMPORTED')

    def test_quantity_only_receipt_without_pack_list_is_ready_for_putaway(self):
        asn = AsnListModel.objects.get(asn_code=self.asn_code, openid=self.openid)
        asn.actual_arrival_at = timezone.now()
        asn.asn_status = 3
        asn.save(update_fields=['actual_arrival_at', 'asn_status'])
        detail = AsnDetailModel.objects.get(asn_code=self.asn_code, openid=self.openid)
        detail.goods_actual_qty = 2
        detail.save(update_fields=['goods_actual_qty'])

        receiving_review = ASNListGetSerializer(asn, context={}).data
        self.assertEqual(receiving_review['operational_status'], 'RECEIVING_REVIEW')
        self.assertEqual(receiving_review['next_action_code'], 'REVIEW_RECEIVING')

        asn.asn_status = 4
        asn.save(update_fields=['asn_status'])

        data = ASNListGetSerializer(asn, context={}).data
        summary = _summary(self.openid, self.asn_code)

        self.assertEqual(data['serial_acceptance']['status'], 'NOT_IMPORTED')
        self.assertTrue(data['serial_acceptance']['qc_complete'])
        self.assertEqual(data['operational_status'], 'READY_FOR_PUTAWAY')
        self.assertEqual(data['next_action_code'], 'ASSIGN_DRIVER_PUTAWAY')
        self.assertTrue(summary['qc_complete'])
        self.assertTrue(summary['ready_for_putaway'])

    def test_asn_serializer_exposes_operational_status_for_work_queue(self):
        asn = AsnListModel.objects.get(asn_code=self.asn_code, openid=self.openid)

        data = ASNListGetSerializer(asn, context={}).data
        self.assertEqual(data['operational_status'], 'PENDING_ARRIVAL')
        self.assertEqual(data['next_action_code'], 'SET_ETA')

        asn.actual_arrival_at = timezone.now()
        asn.asn_status = 4
        asn.save(update_fields=['actual_arrival_at', 'asn_status'])
        detail = AsnDetailModel.objects.get(asn_code=self.asn_code, openid=self.openid)
        detail.goods_actual_qty = 2
        detail.save(update_fields=['goods_actual_qty'])
        for serial_number in ('SN-STATUS-001', 'SN-STATUS-002'):
            AsnSerialRecord.objects.create(
                openid=self.openid,
                asn_code=self.asn_code,
                goods_code='702-S',
                serial_number=serial_number,
                status=AsnSerialRecord.ACCEPTED,
                is_expected=True,
                is_received=True,
            )
        _create_pack_list(
            self.openid,
            self.request(),
            self.asn_code,
            self.rows(),
            content_hash='status-pending',
            package_qty=2,
        )

        data = ASNListGetSerializer(asn, context={}).data
        self.assertEqual(data['operational_status'], 'PACK_LIST_REVIEW')
        self.assertEqual(data['next_action_code'], 'REVIEW_PACK_LIST')
        self.assertEqual(data['putaway_qty'], 0)

        damaged = AsnSerialRecord.objects.get(serial_number='SN-STATUS-002')
        damaged.status = AsnSerialRecord.DAMAGED
        damaged.damaged = True
        damaged.note = 'Outer packaging damage'
        damaged.save(update_fields=['status', 'damaged', 'note'])
        data = ASNListGetSerializer(asn, context={}).data
        self.assertEqual(data['operational_status'], 'QC_REVIEW_REQUIRED')
        self.assertEqual(data['next_action_code'], 'REVIEW_QC')

    def test_extra_scan_record_does_not_increase_received_or_putaway_qty(self):
        detail = AsnDetailModel.objects.get(asn_code=self.asn_code, openid=self.openid)
        detail.goods_actual_qty = 2
        detail.save(update_fields=['goods_actual_qty'])
        for serial_number in ('SN-702-001', 'SN-702-002'):
            AsnSerialRecord.objects.create(
                openid=self.openid,
                asn_code=self.asn_code,
                goods_code='702-S',
                serial_number=serial_number,
                status=AsnSerialRecord.ACCEPTED,
                is_expected=True,
                is_received=True,
            )
        AsnSerialRecord.objects.create(
            openid=self.openid,
            asn_code=self.asn_code,
            goods_code='702-S',
            serial_number='SN-702-EXTRA',
            status=AsnSerialRecord.UNEXPECTED,
            is_expected=False,
            is_received=True,
            exception_resolved=True,
        )

        asn = AsnListModel.objects.get(asn_code=self.asn_code, openid=self.openid)
        acceptance = ASNListGetSerializer(asn, context={}).data['serial_acceptance']
        summary = _summary(self.openid, self.asn_code)

        self.assertEqual(acceptance['actual_received_qty'], 2)
        self.assertEqual(acceptance['scan_record_count'], 3)
        self.assertEqual(acceptance['extra_scan_count'], 1)
        self.assertEqual(acceptance['accepted_for_putaway'], 2)
        self.assertEqual(acceptance['putaway_qty'], 2)
        self.assertEqual(summary['receiving_summary']['received_qty'], 2)
        self.assertEqual(summary['receiving_summary']['scan_record_count'], 3)
        self.assertEqual(summary['receiving_summary']['extra_scan_records'], 1)
        self.assertEqual(summary['receiving_summary']['putaway_qty'], 0)
        self.assertEqual(summary['total_accepted_for_putaway'], 2)
        self.assertEqual(summary['total_putaway_qty'], 0)
        self.assertEqual(summary['reconciliation_rows'][0]['received_qty'], 2)

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

    def test_late_pack_list_is_a_new_reference_revision_after_receiving_started(self):
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
        self.assertEqual(error.exception.detail['code'], 'PACK_LIST_LATE_REFERENCE_REQUIRED')
        late, _, created = _create_pack_list(
            self.openid,
            self.request(),
            self.asn_code,
            self.rows(),
            content_hash='b' * 64,
            package_qty=2,
            replace=True,
            late_reference=True,
        )
        self.assertTrue(created)
        self.assertTrue(late.late_reference)
        self.assertTrue(late.is_current)
        self.assertEqual(PackListDocument.objects.filter(is_current=True).count(), 1)
        self.assertEqual(PackListDocument.objects.filter(status=PackListDocument.ARCHIVED).count(), 1)

    def test_qc_recheck_does_not_create_duplicate_scan(self):
        rows = self.rows()
        rows[0]['serial_number'] = 'SN-702-003'
        document, _, _ = _create_pack_list(
            self.openid,
            self.request(),
            self.asn_code,
            rows,
            content_hash='a' * 64,
            package_qty=2,
        )
        detail = AsnDetailModel.objects.get(asn_code=self.asn_code, openid=self.openid)
        detail.goods_actual_qty = 2
        detail.save(update_fields=['goods_actual_qty'])
        first_batch = PackListImportBatch.objects.create(
            openid=self.openid,
            asn_code=self.asn_code,
            import_type=PackListImportBatch.RECEIVING_ACCEPTANCE,
            status=PackListImportBatch.PASSED,
            source_type='UPLOAD',
        )
        record, _ = _scan(
            self.openid,
            self.request(),
            self.asn_code,
            '702-S',
            'SN-702-003',
            damaged=True,
            source='inspection',
            import_batch=first_batch,
        )
        self.assertEqual(record.status, AsnSerialRecord.DAMAGED)
        second_batch = PackListImportBatch.objects.create(
            openid=self.openid,
            asn_code=self.asn_code,
            import_type=PackListImportBatch.RECEIVING_ACCEPTANCE,
            status=PackListImportBatch.PASSED,
            source_type='UPLOAD',
        )
        record, _ = _scan(
            self.openid,
            self.request(),
            self.asn_code,
            '702-S',
            'SN-702-003',
            damaged=False,
            source='inspection',
            import_batch=second_batch,
        )
        self.assertEqual(record.status, AsnSerialRecord.ACCEPTED)
        self.assertEqual(record.scan_count, 0)
        self.assertEqual(_summary(self.openid, self.asn_code)['qc_status'], 'PASSED')

    def test_late_pack_list_sn_mismatch_is_an_open_reconciliation_exception(self):
        original_rows = self.rows()
        original_rows[0]['serial_number'] = 'SN-702-ORIGINAL'
        _create_pack_list(
            self.openid,
            self.request(),
            self.asn_code,
            original_rows,
            content_hash='a' * 64,
            package_qty=2,
        )
        _scan(self.openid, self.request(), self.asn_code, '702-S', 'SN-702-ORIGINAL', source='inspection')
        late_rows = self.rows()
        late_rows[0]['serial_number'] = 'SN-702-LATE'
        _create_pack_list(
            self.openid,
            self.request(),
            self.asn_code,
            late_rows,
            content_hash='b' * 64,
            package_qty=2,
            replace=True,
            late_reference=True,
        )
        summary = _summary(self.openid, self.asn_code)
        self.assertEqual(summary['pack_list_serial_mismatch_count'], 2)
        self.assertEqual(summary['reconciliation_status'], 'EXCEPTION')
        self.assertFalse(summary['ready_for_putaway'])

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

    def test_qc_evidence_url_preserves_case(self):
        record, _ = _scan(
            self.openid,
            self.request(),
            self.asn_code,
            '702-S',
            'SN-EVIDENCE-001',
            row={'evidence_url': 'https://drive.google.com/drive/u/0/folders/AbC123'},
        )

        self.assertEqual(record.evidence_url, 'https://drive.google.com/drive/u/0/folders/AbC123')

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

    def test_held_serial_is_not_putaway_eligible_but_qc_can_complete(self):
        detail = AsnDetailModel.objects.get(asn_code=self.asn_code, openid=self.openid)
        detail.goods_actual_qty = 2
        detail.save(update_fields=['goods_actual_qty'])
        AsnSerialRecord.objects.create(
            openid=self.openid,
            asn_code=self.asn_code,
            goods_code='702-S',
            serial_number='SN-OK-001',
            status=AsnSerialRecord.ACCEPTED,
            is_expected=True,
            is_received=True,
        )
        AsnSerialRecord.objects.create(
            openid=self.openid,
            asn_code=self.asn_code,
            goods_code='702-S',
            serial_number='SN-HOLD-001',
            status=AsnSerialRecord.DAMAGED,
            is_expected=True,
            is_received=True,
            damaged=True,
            exception_resolved=True,
            exception_resolution_action=HOLD_QUARANTINE,
            exception_resolution_note='Move damaged unit to quarantine.',
            exception_resolution_location='QC-HOLD-01',
        )

        summary = _summary(self.openid, self.asn_code)
        line = summary['lines'][0]

        self.assertTrue(summary['qc_complete'])
        self.assertEqual(summary['total_eligible_for_putaway'], 1)
        self.assertEqual(summary['total_held_serials'], 1)
        self.assertEqual(line['eligible_for_putaway'], 1)
        self.assertTrue(summary['ready_for_putaway'])

    def test_rejected_serials_are_not_putaway_eligible(self):
        detail = AsnDetailModel.objects.get(asn_code=self.asn_code, openid=self.openid)
        detail.goods_actual_qty = 1
        detail.save(update_fields=['goods_actual_qty'])
        AsnSerialRecord.objects.create(
            openid=self.openid,
            asn_code=self.asn_code,
            goods_code='702-S',
            serial_number='SN-REJECT-001',
            status=AsnSerialRecord.REJECTED,
            is_expected=True,
            is_received=True,
            exception_resolved=True,
            exception_resolution_action=REJECT_RETURN,
            exception_resolution_note='Return damaged unit.',
            exception_resolution_location='RETURN-01',
        )

        summary = _summary(self.openid, self.asn_code)

        self.assertTrue(summary['qc_complete'])
        self.assertEqual(summary['total_rejected_serials'], 1)
        self.assertEqual(summary['total_eligible_for_putaway'], 0)
        self.assertFalse(summary['ready_for_putaway'])

    def test_repair_serial_keeps_partial_putaway_available(self):
        detail = AsnDetailModel.objects.get(asn_code=self.asn_code, openid=self.openid)
        detail.goods_actual_qty = 2
        detail.save(update_fields=['goods_actual_qty'])
        asn = AsnListModel.objects.get(asn_code=self.asn_code, openid=self.openid)
        asn.actual_arrival_at = timezone.now()
        asn.asn_status = 4
        asn.save(update_fields=['actual_arrival_at', 'asn_status'])
        AsnSerialRecord.objects.create(
            openid=self.openid,
            asn_code=self.asn_code,
            goods_code='702-S',
            serial_number='SN-OK-REPAIR-001',
            status=AsnSerialRecord.ACCEPTED,
            is_expected=True,
            is_received=True,
        )
        AsnSerialRecord.objects.create(
            openid=self.openid,
            asn_code=self.asn_code,
            goods_code='702-S',
            serial_number='SN-REPAIR-001',
            status=AsnSerialRecord.DAMAGED,
            is_expected=True,
            is_received=True,
            damaged=True,
            exception_resolved=True,
            exception_resolution_action=REPAIR_REWORK,
            exception_resolution_note='Needs repair and reinspection.',
            exception_resolution_location='REPAIR-01',
        )

        summary = _summary(self.openid, self.asn_code)
        self.assertTrue(summary['qc_complete'])
        self.assertEqual(summary['total_eligible_for_putaway'], 1)
        self.assertEqual(summary['total_repair_serials'], 1)
        self.assertTrue(summary['ready_for_putaway'])

        data = ASNListGetSerializer(asn, context={}).data
        self.assertEqual(data['serial_acceptance']['repair'], 1)
        self.assertEqual(data['operational_status'], 'READY_FOR_PUTAWAY_PARTIAL')
        self.assertEqual(data['next_action_code'], 'ASSIGN_DRIVER_PUTAWAY')
