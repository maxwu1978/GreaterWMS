from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from io import BytesIO

from django.db import IntegrityError, transaction
from django.utils import timezone
from openpyxl import load_workbook
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.exceptions import APIException

from asn.models import AsnDetailModel, AsnListModel
from staff.models import ListModel as Staff
from supplier.shortname import generated_supplier_short_name

from .models import (
    ACCEPT_FOR_PUTAWAY,
    HOLD_QUARANTINE,
    LEGACY_ACCEPT_EXCEPTION,
    NON_PUTAWAY_RESOLUTIONS,
    REJECT_RETURN,
    AsnSerialRecord,
    PackListDocument,
    PackListImportBatch,
    PackListLine,
    PUTAWAY_APPROVED_RESOLUTIONS,
    resolution_allows_putaway,
)


EXCEPTION_STATUSES = {
    AsnSerialRecord.UNEXPECTED,
    AsnSerialRecord.DUPLICATE,
    AsnSerialRecord.WRONG_SKU,
    AsnSerialRecord.DAMAGED,
    AsnSerialRecord.REJECTED,
}

SERIAL_EXCEPTION_ACTIONS = {
    ACCEPT_FOR_PUTAWAY,
    LEGACY_ACCEPT_EXCEPTION,
    HOLD_QUARANTINE,
    REJECT_RETURN,
    'WAIVE_MISSING',
    'REOPEN',
}


def _resolved_putaway_count(records):
    return records.filter(
        exception_resolved=True,
        exception_resolution_action__in=PUTAWAY_APPROVED_RESOLUTIONS,
    ).count()


def _resolved_hold_count(records):
    return records.filter(
        exception_resolved=True,
        exception_resolution_action=HOLD_QUARANTINE,
    ).count()


def _resolved_reject_count(records):
    return records.filter(
        exception_resolved=True,
        exception_resolution_action=REJECT_RETURN,
    ).count()


def _openid(request):
    auth = getattr(request, 'auth', None)
    value = getattr(auth, 'openid', None)
    if not value:
        raise APIException({'detail': 'Authentication is required'})
    return str(value)


def _operator_name(request, openid):
    operator_id = request.META.get('HTTP_OPERATOR')
    staff = None
    if operator_id:
        staff = Staff.objects.filter(openid=openid, id=operator_id, is_delete=False).first()
    return staff.staff_name if staff else str(operator_id or '')


def _clean(value):
    if value is None:
        return ''
    return str(value).strip().upper()


def _text(value):
    """Preserve free text such as evidence URLs without SKU normalization."""
    return str(value or '').strip()


def _is_damage_flag(value):
    normalized = str(value or '').strip().lower()
    return normalized in {'1', 'true', 'yes', 'y', 'ng', 'nok'} or normalized.startswith((
        'damage', 'defect', 'fail', 'reject',
    ))


def _asn_detail(openid, asn_code, goods_code):
    asn = AsnListModel.objects.filter(openid=openid, asn_code=asn_code, is_delete=False).first()
    if not asn:
        raise APIException({'detail': 'ASN Code does not exists'})
    detail = AsnDetailModel.objects.filter(
        openid=openid,
        asn_code=asn_code,
        goods_code=goods_code,
        is_delete=False,
    ).first()
    if not detail:
        raise APIException({'detail': 'Goods Code is not part of this ASN'})
    return asn, detail


def _date_value(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    for fmt in ('%Y-%m-%d', '%m/%d/%Y', '%Y/%m/%d'):
        try:
            return datetime.strptime(str(value).strip(), fmt).date()
        except ValueError:
            continue
    return None


def _number(value, default=Decimal('0')):
    try:
        return Decimal(str(value or default).replace(',', '').strip())
    except (InvalidOperation, AttributeError):
        return default


def _current_pack_list(openid, asn_code):
    return PackListDocument.objects.filter(
        openid=openid,
        asn_code=asn_code,
        is_current=True,
        status=PackListDocument.CONFIRMED,
    ).first()


def _pack_list_json(document):
    serials = document.serial_records.all()
    lines = document.lines.filter(is_current=True) if document.is_current else document.lines.all()
    return {
        'id': document.id,
        'asn_code': document.asn_code,
        'version': document.version,
        'source_type': document.source_type,
        'status': document.status,
        'is_current': document.is_current,
        'late_reference': document.late_reference,
        'has_serials': document.has_serials,
        'package_qty': document.package_qty,
        'note': document.note,
        'created_by': document.created_by,
        'confirmed_by': document.confirmed_by,
        'confirmed_at': document.confirmed_at.isoformat() if document.confirmed_at else None,
        'create_time': document.create_time.isoformat() if document.create_time else None,
        'line_count': lines.count(),
        'total_qty': sum(line.goods_qty for line in lines),
        'lines': [
            {
                'goods_code': line.goods_code,
                'customer_goods_code': line.customer_goods_code,
                'customer_ssku': line.customer_ssku,
                'goods_qty': line.goods_qty,
                'total_qty': line.total_qty,
                'package_type': line.package_type,
                'goods_desc': line.goods_desc,
                'source_row': line.source_row,
            }
            for line in lines
        ],
        'expected_serial_count': serials.filter(is_expected=True).count(),
        'received_serial_count': serials.filter(is_received=True).count(),
    }


def _inspection_batch_json(batch):
    return {
        'id': batch.id,
        'asn_code': batch.asn_code,
        'import_type': batch.import_type,
        'status': batch.status,
        'source_type': batch.source_type,
        'row_count': batch.row_count,
        'matched_count': batch.matched_count,
        'accepted_count': batch.accepted_count,
        'exception_count': batch.exception_count,
        'note': batch.note,
        'evidence_url': batch.evidence_url,
        'imported_by': batch.imported_by,
        'created_at': batch.created_at.isoformat() if batch.created_at else None,
    }


def _receiving_started(openid, asn_code):
    if AsnSerialRecord.objects.filter(openid=openid, asn_code=asn_code, is_received=True).exists():
        return True
    return AsnDetailModel.objects.filter(
        openid=openid,
        asn_code=asn_code,
        is_delete=False,
        goods_actual_qty__gt=0,
    ).exists()


def _pack_list_serial_mismatch(document, records):
    if not document or not document.has_serials:
        return {'total': 0, 'missing': [], 'unexpected': [], 'wrong_sku': [], 'by_goods': {}}
    expected = {
        record.serial_number: record.goods_code
        for record in document.serial_records.filter(is_expected=True)
    }
    received = {
        record.serial_number: record.goods_code
        for record in records
        if record.is_received
    }
    missing = sorted(set(expected) - set(received))
    unexpected = sorted(set(received) - set(expected))
    wrong_sku = sorted(
        serial_number for serial_number in set(expected).intersection(received)
        if _clean(expected[serial_number]) != _clean(received[serial_number])
    )
    by_goods = {}
    for serial_number in missing:
        goods_code = expected[serial_number]
        by_goods[goods_code] = by_goods.get(goods_code, 0) + 1
    for serial_number in unexpected:
        goods_code = received[serial_number]
        by_goods[goods_code] = by_goods.get(goods_code, 0) + 1
    for serial_number in wrong_sku:
        goods_code = expected[serial_number]
        by_goods[goods_code] = by_goods.get(goods_code, 0) + 1
    return {
        'total': len(missing) + len(unexpected) + len(wrong_sku),
        'missing': missing,
        'unexpected': unexpected,
        'wrong_sku': wrong_sku,
        'by_goods': by_goods,
    }


def _record_json(record):
    return {
        'id': record.id,
        'asn_code': record.asn_code,
        'goods_code': record.goods_code,
        'expected_goods_code': record.expected_goods_code,
        'scanned_goods_code': record.scanned_goods_code,
        'serial_number': record.serial_number,
        'double_scan_sn': record.double_scan_sn,
        'inbound_po': record.inbound_po,
        'inbound_date': record.inbound_date.isoformat() if record.inbound_date else None,
        'source_location': record.source_location,
        'shipout_ref': record.shipout_ref,
        'source_row': record.source_row,
        'status': record.status,
        'is_expected': record.is_expected,
        'is_received': record.is_received,
        'scan_count': record.scan_count,
        'damaged': record.damaged,
        'note': record.note,
        'evidence_url': record.evidence_url,
        'exception_resolved': record.exception_resolved,
        'exception_resolution_action': record.exception_resolution_action,
        'exception_resolution_note': record.exception_resolution_note,
        'resolution_location': record.exception_resolution_location,
        'exception_resolved_by': record.exception_resolved_by,
        'exception_resolved_at': record.exception_resolved_at.isoformat() if record.exception_resolved_at else None,
        'expected_by': record.expected_by,
        'received_by': record.received_by,
        'expected_at': record.expected_at.isoformat() if record.expected_at else None,
        'received_at': record.received_at.isoformat() if record.received_at else None,
        'pack_list_id': record.pack_list_id,
    }


def _reconciliation_rows(document, details, records, strict_serial_check, exception_statuses, serial_mismatch=None):
    """Join the customer Pack List, ASN receipt quantities, and QC scan results by SKU."""
    pack_lines = {}
    if document:
        for line in document.lines.filter(is_current=True):
            key = _clean(line.goods_code)
            item = pack_lines.setdefault(key, {
                'customer_goods_codes': set(),
                'customer_sskus': set(),
                'pack_list_qty': 0,
            })
            if line.customer_goods_code:
                item['customer_goods_codes'].add(line.customer_goods_code)
            if line.customer_ssku:
                item['customer_sskus'].add(line.customer_ssku)
            item['pack_list_qty'] += int(line.goods_qty or 0)

    detail_list = list(details)
    detail_map = {_clean(detail.goods_code): detail for detail in detail_list}
    record_groups = {}
    for record in records:
        record_groups.setdefault(_clean(record.goods_code), []).append(record)

    rows = []
    keys = list(detail_map.keys())
    keys.extend(key for key in pack_lines if key not in detail_map)
    for key in keys:
        detail = detail_map.get(key)
        line = pack_lines.get(key, {})
        line_records = record_groups.get(key, [])
        expected_count = sum(1 for record in line_records if record.is_expected)
        accepted_count = sum(1 for record in line_records if record.status == AsnSerialRecord.ACCEPTED)
        resolved_count = sum(1 for record in line_records if record.exception_resolved)
        putaway_eligible_count = sum(
            1 for record in line_records
            if record.status == AsnSerialRecord.ACCEPTED or (
                record.exception_resolved and resolution_allows_putaway(record.exception_resolution_action)
            )
        )
        exception_count = sum(
            1 for record in line_records
            if record.status in exception_statuses and not record.exception_resolved
        )
        serial_mismatch_count = int((serial_mismatch or {}).get('by_goods', {}).get(key, 0))
        received_qty = int(detail.goods_actual_qty or 0) if detail else 0
        planned_qty = int(detail.goods_qty or 0) if detail else 0
        pack_list_qty = int(line.get('pack_list_qty') or 0)
        baseline_qty = pack_list_qty if document else planned_qty
        quantity_exception_qty = 0
        quantity_exception_resolved = False
        if detail:
            quantity_exception_qty = 0 if detail.exception_resolved else (
                int(detail.goods_shortage_qty or 0)
                + int(detail.goods_more_qty or 0)
                + int(detail.goods_damage_qty or 0)
            )
            quantity_exception_resolved = bool(detail.exception_resolved)

        open_exception_count = exception_count + serial_mismatch_count + int(quantity_exception_qty > 0)
        resolved_exception_total = resolved_count + int(quantity_exception_resolved)
        variance = received_qty - baseline_qty
        accepted_qty = putaway_eligible_count if (strict_serial_check or (document and document.has_serials)) else received_qty
        if open_exception_count or variance:
            result = 'EXCEPTION'
        elif not document or document.status == PackListDocument.PENDING:
            result = 'REVIEW'
        elif resolved_exception_total:
            result = 'RESOLVED'
        else:
            result = 'PASSED'

        rows.append({
            'goods_code': detail.goods_code if detail else key,
            'customer_goods_code': ', '.join(sorted(line.get('customer_goods_codes', set()))),
            'customer_ssku': ', '.join(sorted(line.get('customer_sskus', set()))),
            'pack_list_qty': pack_list_qty,
            'asn_qty': planned_qty,
            'received_qty': received_qty,
            'accepted_qty': accepted_qty,
            'putaway_eligible_qty': putaway_eligible_count,
            'variance': variance,
            'baseline': 'PACK_LIST' if document else 'ASN',
            'expected_serial_count': expected_count,
            'customer_sn_status': 'PROVIDED' if document and document.has_serials else 'NOT_PROVIDED',
            'open_exception_count': open_exception_count,
            'resolved_exception_count': resolved_exception_total,
            'quantity_exception_qty': quantity_exception_qty,
            'goods_shortage_qty': int(detail.goods_shortage_qty or 0),
            'goods_more_qty': int(detail.goods_more_qty or 0),
            'goods_damage_qty': int(detail.goods_damage_qty or 0),
            'serial_mismatch_count': serial_mismatch_count,
            'result': result,
        })
    return rows


def _summary(openid, asn_code):
    details = AsnDetailModel.objects.filter(openid=openid, asn_code=asn_code, is_delete=False)
    records = AsnSerialRecord.objects.filter(openid=openid, asn_code=asn_code)
    pack_lists = PackListDocument.objects.filter(openid=openid, asn_code=asn_code, is_current=True)
    current_pack_list = _current_pack_list(openid, asn_code)
    pending_pack_list = pack_lists.filter(status=PackListDocument.PENDING).first()
    active_pack_list = pack_lists.order_by('-version', '-id').first()
    asn = AsnListModel.objects.filter(openid=openid, asn_code=asn_code, is_delete=False).first()
    has_expected_serials = records.filter(is_expected=True).exists()
    if current_pack_list and current_pack_list.has_serials:
        verification_mode = 'PACK_LIST'
    elif pending_pack_list:
        verification_mode = 'PACK_LIST_PENDING' if pending_pack_list.has_serials else 'PACK_LIST_QTY'
    elif has_expected_serials:
        verification_mode = 'MANUAL_SN'
    elif current_pack_list:
        verification_mode = 'PACK_LIST_QTY'
    else:
        verification_mode = 'ASN_ONLY'
    strict_serial_check = has_expected_serials
    exception_statuses = EXCEPTION_STATUSES if strict_serial_check else EXCEPTION_STATUSES - {AsnSerialRecord.UNEXPECTED}
    lines = []
    for detail in details:
        line_records = records.filter(goods_code=detail.goods_code)
        expected_count = line_records.filter(is_expected=True).count()
        received_count = line_records.filter(is_received=True).count()
        accepted_count = line_records.filter(status=AsnSerialRecord.ACCEPTED).count()
        resolved_count = line_records.filter(exception_resolved=True).count()
        resolved_putaway_count = _resolved_putaway_count(line_records)
        exception_count = line_records.filter(status__in=exception_statuses, exception_resolved=False).count()
        missing_count = line_records.filter(is_expected=True, is_received=False, exception_resolved=False).count()
        actual_received_qty = int(detail.goods_actual_qty or 0)
        quantity_only_resolved = (
            actual_received_qty > 0
            and not line_records.exists()
            and not strict_serial_check
            and bool(detail.exception_resolved)
        )
        accepted_for_putaway = actual_received_qty if quantity_only_resolved else min(
            accepted_count + resolved_putaway_count,
            actual_received_qty,
        )
        quantity_exception_qty = 0 if detail.exception_resolved else (
            int(detail.goods_shortage_qty or 0)
            + int(detail.goods_more_qty or 0)
            + int(detail.goods_damage_qty or 0)
        )
        lines.append({
            'goods_code': detail.goods_code,
            'planned_qty': detail.goods_qty,
            'received_qty': actual_received_qty,
            'expected_serial_count': expected_count,
            'received_serial_count': received_count,
            'extra_scan_count': max(received_count - actual_received_qty, 0),
            'accepted_serial_count': accepted_count,
            'accepted_for_putaway': accepted_for_putaway,
            'eligible_for_putaway': accepted_for_putaway,
            'resolved_exception_count': resolved_count,
            'held_count': _resolved_hold_count(line_records),
            'rejected_count': _resolved_reject_count(line_records),
            'missing_serial_count': missing_count,
            'exception_count': exception_count,
            'quantity_exception_qty': quantity_exception_qty,
            'quantity_exception_resolved': bool(detail.exception_resolved),
            'exception_resolved': bool(detail.exception_resolved),
            'exception_resolution_action': detail.exception_resolution_action,
            'exception_resolution_note': detail.exception_resolution_note,
            'resolution_location': detail.exception_resolution_location,
            'ready_for_putaway': (
                quantity_exception_qty == 0 and (
                    not line_records.exists()
                    or (not strict_serial_check and exception_count == 0)
                    or (strict_serial_check and missing_count == 0 and exception_count == 0 and accepted_for_putaway >= detail.goods_actual_qty)
                )
            ),
        })
    exception_total = records.filter(status__in=exception_statuses, exception_resolved=False).count()
    missing_total = records.filter(is_expected=True, is_received=False, exception_resolved=False).count()
    resolved_total = records.filter(exception_resolved=True).count()
    accepted_total = records.filter(status=AsnSerialRecord.ACCEPTED).count()
    actual_received_qty = sum(int(detail.goods_actual_qty or 0) for detail in details)
    physical_putaway_qty = sum(int(detail.sorted_qty or 0) for detail in details)
    scanned_record_count = records.filter(is_received=True).count()
    resolved_putaway_total = _resolved_putaway_count(records)
    quantity_only_resolved = (
        actual_received_qty > 0
        and not records.exists()
        and not has_expected_serials
        and not details.filter(exception_resolved=False).exists()
    )
    accepted_for_putaway_total = actual_received_qty if quantity_only_resolved else min(
        accepted_total + resolved_putaway_total,
        actual_received_qty,
    )
    extra_scan_record_count = max(scanned_record_count - actual_received_qty, 0)
    quantity_exception_total = sum(
        0 if detail.exception_resolved else (
            int(detail.goods_shortage_qty or 0)
            + int(detail.goods_more_qty or 0)
            + int(detail.goods_damage_qty or 0)
        )
        for detail in details
    )
    reconciliation_rows = _reconciliation_rows(
        active_pack_list,
        details,
        records,
        strict_serial_check,
        exception_statuses,
        serial_mismatch=_pack_list_serial_mismatch(active_pack_list, records),
    )
    open_reconciliation_exceptions = sum(row['open_exception_count'] for row in reconciliation_rows)
    resolved_reconciliation_exceptions = sum(row['resolved_exception_count'] for row in reconciliation_rows)
    pack_list_variance = sum(
        abs(int(row['variance'] or 0))
        for row in reconciliation_rows
    ) if active_pack_list else 0
    pack_list_serial_mismatch = _pack_list_serial_mismatch(active_pack_list, records)
    # Quantity-only receiving has no SN rows by design. It is complete here
    # only after all quantity exceptions have been explicitly resolved.
    has_receiving_result = records.exists() or actual_received_qty == 0 or quantity_only_resolved
    qc_complete = bool(
        has_receiving_result
        and not open_reconciliation_exceptions
        and not pack_list_variance
        and missing_total == 0
        and quantity_exception_total == 0
    )
    if open_reconciliation_exceptions or pack_list_variance:
        reconciliation_status = 'EXCEPTION'
    elif not active_pack_list or active_pack_list.status == PackListDocument.PENDING:
        reconciliation_status = 'REVIEW'
    elif resolved_reconciliation_exceptions:
        reconciliation_status = 'RESOLVED'
    else:
        reconciliation_status = 'PASSED'
    receiving_status = 'EXCEPTION' if (open_reconciliation_exceptions or pack_list_variance) else (
        'RESOLVED' if resolved_reconciliation_exceptions else 'PASSED'
    )
    inspection_batches = list(PackListImportBatch.objects.filter(
        openid=openid,
        asn_code=asn_code,
        import_type=PackListImportBatch.RECEIVING_ACCEPTANCE,
    )[:10])
    latest_inspection = inspection_batches[0] if inspection_batches else None
    if open_reconciliation_exceptions or pack_list_variance or (inspection_batches and missing_total):
        qc_status = 'EXCEPTION'
        reconciliation_status = 'EXCEPTION'
        receiving_status = 'EXCEPTION'
    elif not inspection_batches:
        qc_status = 'NOT_STARTED'
    elif latest_inspection.status == PackListImportBatch.PARTIAL:
        qc_status = 'PARTIAL'
    else:
        qc_status = 'PASSED'
    all_pack_lists = PackListDocument.objects.filter(
        openid=openid,
        asn_code=asn_code,
    ).order_by('-version', '-id')
    pack_list_status = (
        PackListDocument.CONFIRMED if current_pack_list else
        PackListDocument.PENDING if pending_pack_list else
        'NOT_RECEIVED'
    )
    if active_pack_list and active_pack_list.late_reference:
        pack_list_status = 'LATE' if active_pack_list.status == PackListDocument.CONFIRMED else 'LATE_PENDING'
    return {
        'asn_code': asn_code,
        'customer': asn.supplier if asn else '',
        'customer_short_name': generated_supplier_short_name(asn.supplier if asn else ''),
        'expected_arrival_at': asn.expected_arrival_at.isoformat() if asn and asn.expected_arrival_at else None,
        'actual_arrival_at': asn.actual_arrival_at.isoformat() if asn and asn.actual_arrival_at else None,
        'pack_list_present': pack_lists.exists(),
        'pack_list_status': pack_list_status,
        'pack_list_timing': 'LATE_REFERENCE' if active_pack_list and active_pack_list.late_reference else (
            'BEFORE_RECEIPT' if active_pack_list else 'NOT_RECEIVED'
        ),
        'pack_list_confirmed': bool(current_pack_list),
        'pack_list_has_serials': bool(current_pack_list and current_pack_list.has_serials),
        'active_pack_list': _pack_list_json(active_pack_list) if active_pack_list else None,
        'customer_sn_status': 'PROVIDED' if active_pack_list and active_pack_list.has_serials else 'NOT_PROVIDED',
        'current_pack_list': _pack_list_json(current_pack_list) if current_pack_list else None,
        'pack_list_history': [_pack_list_json(document) for document in all_pack_lists],
        'inspection_batches': [_inspection_batch_json(batch) for batch in inspection_batches],
        'latest_inspection_batch': _inspection_batch_json(latest_inspection) if latest_inspection else None,
        'qc_status': qc_status,
        'qc_complete': qc_complete,
        'verification_mode': verification_mode,
        'verification_note': (
            'Receiving scans are not checked against a Pack List yet.'
            if verification_mode == 'ASN_ONLY' else
            'Pack List has quantities only; physical scans are recorded without SN validation.'
            if verification_mode == 'PACK_LIST_QTY' else
            'Pack List with expected SN is pending confirmation.'
            if verification_mode == 'PACK_LIST_PENDING' else
            'Expected SN comes from a Pack List.'
            if verification_mode == 'PACK_LIST' else
            'Expected SN was entered manually.'
        ),
        'lines': lines,
        'reconciliation_status': reconciliation_status,
        'reconciliation_rows': reconciliation_rows,
        'receiving_summary': {
            'expected': records.filter(is_expected=True).count(),
            'received_qty': actual_received_qty,
            'scanned': scanned_record_count,
            'scan_record_count': scanned_record_count,
            'accepted': accepted_total,
            'accepted_for_putaway': accepted_for_putaway_total,
            'eligible_for_putaway': accepted_for_putaway_total,
            'putaway_qty': physical_putaway_qty,
            'held_qty': _resolved_hold_count(records),
            'rejected_qty': _resolved_reject_count(records),
            'extra_scan_records': extra_scan_record_count,
            'open_exceptions': open_reconciliation_exceptions,
            'resolved_exceptions': resolved_reconciliation_exceptions,
            'status': receiving_status,
            'qc_status': qc_status,
            'latest_batch_id': latest_inspection.id if latest_inspection else None,
            'pack_list_variance': pack_list_variance,
        },
        'total_expected_serials': records.filter(is_expected=True).count(),
        'total_received_qty': actual_received_qty,
        'total_received_serials': scanned_record_count,
        'total_scan_records': scanned_record_count,
        'total_accepted_serials': accepted_total,
        'total_resolved_exceptions': resolved_total,
        'total_accepted_for_putaway': accepted_for_putaway_total,
        'total_eligible_for_putaway': accepted_for_putaway_total,
        'total_held_serials': _resolved_hold_count(records),
        'total_rejected_serials': _resolved_reject_count(records),
        'total_putaway_qty': physical_putaway_qty,
        'total_extra_scan_records': extra_scan_record_count,
        'total_exception_serials': exception_total,
        'total_missing_serials': missing_total,
        'total_quantity_exceptions': quantity_exception_total,
        'pack_list_variance': pack_list_variance,
        'pack_list_serial_mismatch': pack_list_serial_mismatch,
        'pack_list_serial_mismatch_count': pack_list_serial_mismatch['total'],
        'ready_for_putaway': bool(qc_complete and accepted_for_putaway_total > physical_putaway_qty),
    }


def _save_expected(openid, request, asn_code, goods_code, serial_number, row=None, source='manual', pack_list=None, import_batch=None):
    serial_number = _clean(serial_number)
    if not serial_number:
        raise APIException({'detail': 'Serial Number is required'})
    _, detail = _asn_detail(openid, asn_code, goods_code)
    record = AsnSerialRecord.objects.filter(
        openid=openid,
        asn_code=asn_code,
        serial_number=serial_number,
    ).first()
    now = timezone.now()
    metadata = row or {}
    if record:
        if record.goods_code != goods_code:
            raise APIException({'detail': 'Serial Number already belongs to another SKU in this ASN'})
        record.is_expected = True
        record.expected_goods_code = goods_code
        record.double_scan_sn = _clean(metadata.get('double_scan_sn')) or record.double_scan_sn
        record.inbound_po = _clean(metadata.get('inbound_po')) or record.inbound_po
        record.inbound_date = _date_value(metadata.get('inbound_date')) or record.inbound_date
        record.source_location = _clean(metadata.get('source_location')) or record.source_location
        record.shipout_ref = _clean(metadata.get('shipout_ref')) or record.shipout_ref
        record.source_row = int(metadata.get('source_row') or record.source_row or 0)
        record.note = str(metadata.get('note') or record.note or '').strip()
        record.evidence_url = _text(metadata.get('evidence_url')) or record.evidence_url
        record.pack_list = pack_list or record.pack_list
        record.import_batch = import_batch or record.import_batch
        record.expected_by = _operator_name(request, openid)
        record.expected_at = record.expected_at or now
        if record.is_received and record.scanned_goods_code == goods_code and record.status not in EXCEPTION_STATUSES:
            record.status = AsnSerialRecord.ACCEPTED
            record.exception_resolved = False
            record.exception_resolution_action = ''
            record.exception_resolution_note = ''
            record.exception_resolution_location = ''
            record.exception_resolved_by = ''
            record.exception_resolved_at = None
        record.save()
        return record, False
    expected_count = AsnSerialRecord.objects.filter(
        openid=openid,
        asn_code=asn_code,
        goods_code=goods_code,
        is_expected=True,
    ).count()
    if expected_count >= int(detail.goods_qty):
        raise APIException({'detail': 'Expected SN quantity cannot exceed ASN quantity'})
    record = AsnSerialRecord.objects.create(
        openid=openid,
        asn_code=asn_code,
        goods_code=goods_code,
        expected_goods_code=goods_code,
        serial_number=serial_number,
        double_scan_sn=_clean(metadata.get('double_scan_sn')),
        inbound_po=_clean(metadata.get('inbound_po')),
        inbound_date=_date_value(metadata.get('inbound_date')),
        source_location=_clean(metadata.get('source_location')),
        shipout_ref=_clean(metadata.get('shipout_ref')),
        source_row=int(metadata.get('source_row') or 0),
        note=str(metadata.get('note') or '').strip(),
        evidence_url=_text(metadata.get('evidence_url')),
        import_batch=import_batch,
        status=AsnSerialRecord.EXPECTED,
        is_expected=True,
        expected_by=_operator_name(request, openid),
        expected_at=now,
        pack_list=pack_list,
    )
    return record, True


def _scan_status_without_pack_list(openid, asn_code):
    pack_list = _current_pack_list(openid, asn_code)
    return AsnSerialRecord.UNEXPECTED if pack_list and pack_list.has_serials else AsnSerialRecord.UNVERIFIED


def _scan(openid, request, asn_code, goods_code, serial_number, damaged=False, row=None, source='manual', import_batch=None):
    serial_number = _clean(serial_number)
    goods_code = _clean(goods_code)
    if not serial_number or not goods_code:
        raise APIException({'detail': 'Goods Code and Serial Number are required'})
    _asn_detail(openid, asn_code, goods_code)
    record = AsnSerialRecord.objects.filter(
        openid=openid,
        asn_code=asn_code,
        serial_number=serial_number,
    ).first()
    now = timezone.now()
    metadata = row or {}
    inspection = source in ('inspection', 'qc')
    if record:
        # An inspection workbook is a result snapshot, not another physical scan.
        # Re-importing a later QC round must not turn a valid SN into a duplicate.
        if not inspection:
            record.scan_count += 1
        record.is_received = True
        record.received_at = now
        record.received_by = _operator_name(request, openid)
        record.scanned_goods_code = goods_code
        record.double_scan_sn = _clean(metadata.get('double_scan_sn')) or record.double_scan_sn
        record.inbound_po = _clean(metadata.get('inbound_po')) or record.inbound_po
        record.inbound_date = _date_value(metadata.get('inbound_date')) or record.inbound_date
        record.source_location = _clean(metadata.get('source_location')) or record.source_location
        record.shipout_ref = _clean(metadata.get('shipout_ref')) or record.shipout_ref
        record.source_row = int(metadata.get('source_row') or record.source_row or 0)
        record.import_batch = import_batch or record.import_batch
        record.note = str(metadata.get('note') or record.note or '').strip()
        record.evidence_url = _text(metadata.get('evidence_url')) or record.evidence_url
        record.damaged = bool(damaged) if inspection else record.damaged or bool(damaged)
        if not inspection and record.scan_count > 1:
            record.status = AsnSerialRecord.DUPLICATE
        elif record.goods_code != goods_code:
            record.status = AsnSerialRecord.WRONG_SKU
        elif record.damaged:
            record.status = AsnSerialRecord.DAMAGED
        elif record.is_expected:
            record.status = AsnSerialRecord.ACCEPTED
        else:
            record.status = _scan_status_without_pack_list(openid, asn_code)
        if record.status in EXCEPTION_STATUSES:
            record.exception_resolved = False
            record.exception_resolution_action = ''
            record.exception_resolution_note = ''
            record.exception_resolution_location = ''
            record.exception_resolved_by = ''
            record.exception_resolved_at = None
        elif inspection:
            record.exception_resolved = False
            record.exception_resolution_action = ''
            record.exception_resolution_note = ''
            record.exception_resolution_location = ''
            record.exception_resolved_by = ''
            record.exception_resolved_at = None
        record.save()
        return record, False
    record = AsnSerialRecord.objects.create(
        openid=openid,
        asn_code=asn_code,
        goods_code=goods_code,
        scanned_goods_code=goods_code,
        serial_number=serial_number,
        double_scan_sn=_clean(metadata.get('double_scan_sn')),
        inbound_po=_clean(metadata.get('inbound_po')),
        inbound_date=_date_value(metadata.get('inbound_date')),
        source_location=_clean(metadata.get('source_location')),
        shipout_ref=_clean(metadata.get('shipout_ref')),
        source_row=int(metadata.get('source_row') or 0),
        note=str(metadata.get('note') or '').strip(),
        evidence_url=_text(metadata.get('evidence_url')),
        import_batch=metadata.get('import_batch'),
        status=AsnSerialRecord.DAMAGED if damaged else _scan_status_without_pack_list(openid, asn_code),
        is_expected=False,
        is_received=True,
        scan_count=1,
        damaged=bool(damaged),
        received_by=_operator_name(request, openid),
        received_at=now,
    )
    return record, True


class SerialRecordsView(APIView):
    def get(self, request):
        openid = _openid(request)
        asn_code = _clean(request.query_params.get('asn_code'))
        if not asn_code:
            raise APIException({'detail': 'ASN Code is required'})
        records = AsnSerialRecord.objects.filter(openid=openid, asn_code=asn_code)
        goods_code = _clean(request.query_params.get('goods_code'))
        status = _clean(request.query_params.get('status'))
        if goods_code:
            records = records.filter(goods_code=goods_code)
        if status:
            records = records.filter(status=status)
        limit = min(max(int(request.query_params.get('limit', 500)), 1), 5000)
        return Response({'count': records.count(), 'results': [_record_json(r) for r in records[:limit]]})


def _resolution_note(data):
    return str(data.get('note') or data.get('resolution_note') or '').strip()


class SerialExceptionsView(APIView):
    """List current SN and quantity exceptions for QC follow-up."""

    def get(self, request):
        openid = _openid(request)
        asn_code = _clean(request.query_params.get('asn_code'))
        if not asn_code:
            raise APIException({'detail': 'ASN Code is required'})
        records = AsnSerialRecord.objects.filter(openid=openid, asn_code=asn_code)
        exception_statuses = EXCEPTION_STATUSES
        results = []
        for record in records.filter(status__in=exception_statuses) | records.filter(is_expected=True, is_received=False):
            if record.exception_resolved:
                continue
            kind = {
                AsnSerialRecord.UNEXPECTED: 'UNEXPECTED_SN',
                AsnSerialRecord.DUPLICATE: 'DUPLICATE_SN',
                AsnSerialRecord.WRONG_SKU: 'WRONG_SKU',
                AsnSerialRecord.DAMAGED: 'DAMAGED_SN',
                AsnSerialRecord.REJECTED: 'REJECTED_SN',
            }.get(record.status, 'MISSING_SN')
            results.append({
                'type': 'SERIAL',
                'id': record.id,
                'asn_code': record.asn_code,
                'goods_code': record.goods_code,
                'serial_number': record.serial_number,
                'kind': kind,
                'status': record.status,
                'quantity': 1,
                'exception_resolved': record.exception_resolved,
                'note': record.note,
                'evidence_url': record.evidence_url,
                'resolution_location': record.exception_resolution_location,
            })

        details = AsnDetailModel.objects.filter(openid=openid, asn_code=asn_code, is_delete=False)
        for detail in details:
            quantity = int(detail.goods_shortage_qty or 0) + int(detail.goods_more_qty or 0) + int(detail.goods_damage_qty or 0)
            if quantity <= 0 or detail.exception_resolved:
                continue
            if detail.goods_shortage_qty:
                kind = 'SHORTAGE'
                quantity = int(detail.goods_shortage_qty)
            elif detail.goods_more_qty:
                kind = 'OVERAGE'
                quantity = int(detail.goods_more_qty)
            else:
                kind = 'DAMAGED_QTY'
                quantity = int(detail.goods_damage_qty)
            results.append({
                'type': 'QUANTITY',
                'id': detail.id,
                'asn_code': detail.asn_code,
                'goods_code': detail.goods_code,
                'serial_number': '',
                'kind': kind,
                'status': 'OPEN',
                'quantity': quantity,
                'exception_resolved': detail.exception_resolved,
                'note': detail.exception_resolution_note,
                'resolution_location': detail.exception_resolution_location,
            })
        return Response({'count': len(results), 'results': results})


class SerialExceptionResolveView(APIView):
    """Resolve or reopen one serial exception with an audit note."""

    def post(self, request):
        openid = _openid(request)
        data = request.data
        try:
            record_id = int(data.get('id'))
        except (TypeError, ValueError):
            raise APIException({'detail': 'Serial record id is required'})
        action = str(data.get('action') or '').strip().upper()
        if action not in SERIAL_EXCEPTION_ACTIONS:
            raise APIException({
                'detail': 'Action must be ACCEPT_FOR_PUTAWAY, HOLD_QUARANTINE, REJECT_RETURN, WAIVE_MISSING, or REOPEN'
            })
        record = AsnSerialRecord.objects.filter(id=record_id, openid=openid).first()
        if not record:
            raise APIException({'detail': 'Serial record does not exist'})
        is_missing = record.is_expected and not record.is_received
        is_exception = record.status in EXCEPTION_STATUSES
        if action != 'REOPEN' and not is_missing and not is_exception:
            raise APIException({'detail': 'This serial record has no open exception'})
        if action == 'WAIVE_MISSING' and not is_missing:
            raise APIException({'detail': 'WAIVE_MISSING is only valid for an expected SN that was not received'})
        if action != 'REOPEN' and not _resolution_note(data):
            raise APIException({'detail': 'A resolution note is required'})
        resolution_location = _clean(data.get('resolution_location'))
        if action in NON_PUTAWAY_RESOLUTIONS and not resolution_location:
            raise APIException({'detail': 'A hold or return location is required'})
        if action == 'REOPEN':
            if not record.exception_resolved:
                raise APIException({'detail': 'This serial exception is already open'})
            record.exception_resolved = False
            record.exception_resolution_action = ''
            record.exception_resolution_note = ''
            record.exception_resolution_location = ''
            record.exception_resolved_by = ''
            record.exception_resolved_at = None
        else:
            record.exception_resolved = True
            record.exception_resolution_action = action
            record.exception_resolution_note = _resolution_note(data)
            record.exception_resolution_location = resolution_location
            record.exception_resolved_by = _operator_name(request, openid)
            record.exception_resolved_at = timezone.now()
        record.save(update_fields=[
            'exception_resolved',
            'exception_resolution_action',
            'exception_resolution_note',
            'exception_resolution_location',
            'exception_resolved_by',
            'exception_resolved_at',
            'update_time',
        ])
        return Response({
            'detail': 'Serial exception updated',
            'record': _record_json(record),
            'summary': _summary(openid, record.asn_code),
        })


class QuantityExceptionResolveView(APIView):
    """Resolve or reopen the quantity variance recorded during QC."""

    def post(self, request):
        openid = _openid(request)
        data = request.data
        asn_code = _clean(data.get('asn_code'))
        goods_code = _clean(data.get('goods_code'))
        action = str(data.get('action') or '').strip().upper()
        if not asn_code or not goods_code:
            raise APIException({'detail': 'ASN Code and Goods Code are required'})
        if action not in {
            ACCEPT_FOR_PUTAWAY,
            LEGACY_ACCEPT_EXCEPTION,
            HOLD_QUARANTINE,
            REJECT_RETURN,
            'REOPEN',
        }:
            raise APIException({
                'detail': 'Action must be ACCEPT_FOR_PUTAWAY, HOLD_QUARANTINE, REJECT_RETURN, or REOPEN'
            })
        detail = AsnDetailModel.objects.filter(
            openid=openid,
            asn_code=asn_code,
            goods_code=goods_code,
            is_delete=False,
        ).first()
        if not detail:
            raise APIException({'detail': 'ASN detail does not exist'})
        quantity = int(detail.goods_shortage_qty or 0) + int(detail.goods_more_qty or 0) + int(detail.goods_damage_qty or 0)
        if action != 'REOPEN' and quantity <= 0:
            raise APIException({'detail': 'This ASN detail has no quantity exception'})
        if action != 'REOPEN' and not _resolution_note(data):
            raise APIException({'detail': 'A resolution note is required'})
        resolution_location = _clean(data.get('resolution_location'))
        if action in NON_PUTAWAY_RESOLUTIONS and not resolution_location:
            raise APIException({'detail': 'A hold or return location is required'})
        if action == 'REOPEN':
            if not detail.exception_resolved:
                raise APIException({'detail': 'This quantity exception is already open'})
            detail.exception_resolved = False
            detail.exception_resolution_action = ''
            detail.exception_resolution_note = ''
            detail.exception_resolution_location = ''
            detail.exception_resolved_by = ''
            detail.exception_resolved_at = None
        else:
            detail.exception_resolved = True
            detail.exception_resolution_action = action
            detail.exception_resolution_note = _resolution_note(data)
            detail.exception_resolution_location = resolution_location
            detail.exception_resolved_by = _operator_name(request, openid)
            detail.exception_resolved_at = timezone.now()
        detail.save(update_fields=[
            'exception_resolved',
            'exception_resolution_action',
            'exception_resolution_note',
            'exception_resolution_location',
            'exception_resolved_by',
            'exception_resolved_at',
            'update_time',
        ])
        return Response({
            'detail': 'Quantity exception updated',
            'asn_detail_id': detail.id,
            'asn_code': detail.asn_code,
            'goods_code': detail.goods_code,
            'exception_resolved': detail.exception_resolved,
            'exception_resolution_action': detail.exception_resolution_action,
            'exception_resolution_note': detail.exception_resolution_note,
            'resolution_location': detail.exception_resolution_location,
            'summary': _summary(openid, detail.asn_code),
        })


class SerialSummaryView(APIView):
    def get(self, request):
        openid = _openid(request)
        asn_code = _clean(request.query_params.get('asn_code'))
        if not asn_code:
            raise APIException({'detail': 'ASN Code is required'})
        _asn = AsnListModel.objects.filter(openid=openid, asn_code=asn_code, is_delete=False).first()
        if not _asn:
            raise APIException({'detail': 'ASN Code does not exists'})
        return Response(_summary(openid, asn_code))


class ExpectedSerialView(APIView):
    def post(self, request):
        openid = _openid(request)
        data = request.data
        asn_code = _clean(data.get('asn_code'))
        default_goods = _clean(data.get('goods_code'))
        rows = data.get('rows') or []
        if not rows:
            rows = [{'serial_number': value, 'goods_code': default_goods} for value in (data.get('serial_numbers') or [])]
        if not asn_code or not rows:
            raise APIException({'detail': 'ASN Code and serial rows are required'})
        created = 0
        updated = 0
        results = []
        with transaction.atomic():
            for row in rows:
                if isinstance(row, str):
                    row = {'serial_number': row, 'goods_code': default_goods}
                goods_code = _clean(row.get('goods_code') or default_goods)
                record, was_created = _save_expected(openid, request, asn_code, goods_code, row.get('serial_number'), row=row)
                created += int(was_created)
                updated += int(not was_created)
                results.append(_record_json(record))
        return Response({'detail': 'success', 'created': created, 'updated': updated, 'results': results, 'summary': _summary(openid, asn_code)})


class ScanSerialView(APIView):
    def post(self, request):
        openid = _openid(request)
        data = request.data
        asn_code = _clean(data.get('asn_code'))
        goods_code = _clean(data.get('goods_code'))
        record, created = _scan(
            openid,
            request,
            asn_code,
            goods_code,
            data.get('serial_number'),
            damaged=bool(data.get('damaged', False)),
            row=data,
        )
        return Response({'detail': 'success', 'created': created, 'record': _record_json(record), 'summary': _summary(openid, asn_code)})


def _header_key(value):
    return ''.join(char for char in str(value or '').upper() if char.isalnum())


def _first_column(index, names):
    for name in names:
        if _header_key(name) in index:
            return index[_header_key(name)]
    return None


def _pack_list_rows_from_workbook(upload):
    try:
        file_bytes = upload.read()
        upload.seek(0)
        workbook = load_workbook(BytesIO(file_bytes), read_only=True, data_only=True)
        sheet = workbook.active
        values = list(sheet.iter_rows(values_only=True))
    except Exception as exc:
        raise APIException({'detail': 'Unable to read Pack List Excel file: ' + str(exc)})
    if not values:
        raise APIException({'detail': 'Pack List Excel file is empty'})
    index = {
        _header_key(value): position
        for position, value in enumerate(values[0])
        if _header_key(value)
    }
    sku_column = _first_column(index, ('SKU#', 'SKU', 'Goods Code', 'GoodsCode', 'Item', 'Part Number'))
    qty_column = _first_column(index, ('Item Qty', 'Qty', 'Quantity', 'Goods Qty', 'ASN Qty', 'Total Qty'))
    serial_column = _first_column(index, ('SN#', 'SN', 'Serial Number', 'Serial', 'Serial No'))
    customer_sku_column = _first_column(index, ('Customer SKU', 'Customer Part Number', 'Customer Item'))
    customer_ssku_column = _first_column(index, ('S-SKU', 'Customer S-SKU', 'Client SKU'))
    package_type_column = _first_column(index, ('Package Type', 'Package Code', 'Package ID', 'Package'))
    desc_column = _first_column(index, ('Description', 'Goods Description', 'Product Description'))
    weight_column = _first_column(index, ('Weight', 'Goods Weight'))
    volume_column = _first_column(index, ('Volume', 'Goods Volume'))
    total_column = _first_column(index, ('Total', 'Total Qty', 'Item Total'))
    if sku_column is None:
        raise APIException({'detail': 'Pack List must contain a SKU or Goods Code column'})
    rows = []
    for row_number, values_row in enumerate(values[1:], start=2):
        def value_at(column):
            return values_row[column] if column is not None and column < len(values_row) else ''

        goods_code = _clean(value_at(sku_column))
        serial_number = _clean(value_at(serial_column))
        if not goods_code and not serial_number:
            continue
        qty_value = value_at(qty_column)
        qty = int(_number(qty_value, Decimal('1') if serial_number else Decimal('0')))
        rows.append({
            'goods_code': goods_code,
            'customer_goods_code': _clean(value_at(customer_sku_column)),
            'customer_ssku': _clean(value_at(customer_ssku_column)),
            'package_type': _clean(value_at(package_type_column)),
            'serial_number': serial_number,
            'goods_qty': qty,
            'total_qty': int(_number(value_at(total_column), Decimal(str(qty))) or qty),
            'goods_desc': str(value_at(desc_column) or '').strip(),
            'goods_weight': _number(value_at(weight_column)),
            'goods_volume': _number(value_at(volume_column)),
            'source_row': row_number,
        })
    if not rows:
        raise APIException({'detail': 'Pack List contains no usable rows'})
    return rows, sha256(file_bytes).hexdigest()


def _validate_pack_list_rows(openid, asn_code, rows):
    asn = AsnListModel.objects.filter(openid=openid, asn_code=asn_code, is_delete=False).first()
    if not asn:
        raise APIException({'detail': 'ASN Code does not exists'})
    normalized_rows = []
    quantities = {}
    serial_numbers = set()
    has_serials = False
    for position, raw_row in enumerate(rows, start=1):
        if isinstance(raw_row, str):
            raw_row = {'goods_code': raw_row, 'goods_qty': 1}
        goods_code = _clean(raw_row.get('goods_code'))
        serial_number = _clean(raw_row.get('serial_number'))
        if not goods_code:
            raise APIException({'detail': 'Pack List row %s is missing internal SKU' % position})
        _, detail = _asn_detail(openid, asn_code, goods_code)
        qty = int(_number(raw_row.get('goods_qty'), Decimal('1') if serial_number else Decimal('0')))
        if qty <= 0:
            raise APIException({'detail': 'Pack List row %s quantity must be greater than 0' % position})
        quantities[goods_code] = quantities.get(goods_code, 0) + qty
        if quantities[goods_code] > int(detail.goods_qty):
            raise APIException({'detail': 'Pack List quantity exceeds ASN quantity for SKU ' + goods_code})
        has_serials = has_serials or bool(serial_number)
        if serial_number:
            if serial_number in serial_numbers:
                raise APIException({'detail': 'Pack List contains duplicate Serial Number ' + serial_number})
            serial_numbers.add(serial_number)
        normalized_rows.append({
            'goods_code': goods_code,
            'customer_goods_code': _clean(raw_row.get('customer_goods_code')),
            'customer_ssku': _clean(raw_row.get('customer_ssku')),
            'package_type': _clean(raw_row.get('package_type')),
            'serial_number': serial_number,
            'goods_qty': qty,
            'total_qty': int(_number(raw_row.get('total_qty'), Decimal(str(qty))) or qty),
            'goods_desc': str(raw_row.get('goods_desc') or '').strip(),
            'goods_weight': _number(raw_row.get('goods_weight')),
            'goods_volume': _number(raw_row.get('goods_volume')),
            'source_row': int(raw_row.get('source_row') or position),
        })
    return {
        'asn': asn,
        'rows': normalized_rows,
        'has_serials': has_serials,
        'total_qty': sum(row['goods_qty'] for row in normalized_rows),
        'expected_serial_count': len(serial_numbers),
    }


def _pack_list_preview_json(asn_code, validation, package_qty, content_hash, duplicate_document=None, current_document=None, receiving_started=False):
    return {
        'asn_code': asn_code,
        'status': 'DUPLICATE' if duplicate_document else 'PREVIEW',
        'content_hash': content_hash,
        'row_count': len(validation['rows']),
        'total_qty': validation['total_qty'],
        'has_serials': validation['has_serials'],
        'expected_serial_count': validation['expected_serial_count'],
        'package_qty': max(0, int(package_qty or 0)),
        'duplicate_document': _pack_list_json(duplicate_document) if duplicate_document else None,
        'current_document': _pack_list_json(current_document) if current_document else None,
        'replace_required': bool(current_document and not duplicate_document),
        'receiving_started': receiving_started,
        'late_reference_required': bool(receiving_started and not duplicate_document),
        'lines': [
            {
                'goods_code': row['goods_code'],
                'customer_goods_code': row['customer_goods_code'],
                'customer_ssku': row['customer_ssku'],
                'package_type': row['package_type'],
                'goods_qty': row['goods_qty'],
                'total_qty': row['total_qty'],
                'serial_number': row['serial_number'],
                'goods_desc': row['goods_desc'],
                'source_row': row['source_row'],
            }
            for row in validation['rows']
        ],
    }


def _create_pack_list(openid, request, asn_code, rows, source_type='AI_AGENT', content_hash='', note='', package_qty=0, replace=False, late_reference=False):
    validation = _validate_pack_list_rows(openid, asn_code, rows)
    asn = validation['asn']
    normalized_rows = validation['rows']
    has_serials = validation['has_serials']
    package_qty = max(0, int(package_qty or 0))
    source_type = source_type if source_type in dict(PackListDocument.SOURCE_TYPES) else 'MANUAL'
    document = PackListDocument.objects.select_for_update().filter(
        openid=openid,
        asn_code=asn_code,
        is_current=True,
    ).first()
    receiving_started = _receiving_started(openid, asn_code)
    next_version = 1
    if document:
        if document.content_hash == str(content_hash or ''):
            return document, None, False
        if not replace:
            raise APIException({
                'detail': 'A different Pack List already exists for this ASN. Preview the differences and use the explicit Replace action.',
                'code': 'PACK_LIST_REPLACE_REQUIRED',
                'document_id': document.id,
            })
        if receiving_started and not late_reference:
            raise APIException({
                'detail': 'Receiving has started; import this Pack List as a late reference revision.',
                'code': 'PACK_LIST_LATE_REFERENCE_REQUIRED',
            })
        if receiving_started:
            next_version = int(document.version or 0) + 1
            document.is_current = False
            document.status = PackListDocument.ARCHIVED
            document.save(update_fields=['is_current', 'status', 'update_time'])
            document = None
            late_reference = True
        else:
            document.serial_records.filter(is_expected=True, is_received=False).update(
                pack_list=None,
                is_expected=False,
                expected_goods_code='',
                status=AsnSerialRecord.UNVERIFIED,
            )
            document.lines.filter(is_current=True).update(is_current=False)
            document.version = int(document.version or 0) + 1
            document.has_serials = has_serials
            document.package_qty = package_qty
            document.note = str(note or '')
            document.source_type = source_type
            document.content_hash = str(content_hash or '')[:64]
            document.confirmed_by = ''
            document.confirmed_at = None
            document.status = PackListDocument.PENDING
            document.late_reference = False
            document.save(update_fields=[
                'version', 'source_type', 'content_hash', 'status', 'has_serials',
                'package_qty', 'note', 'late_reference', 'confirmed_by', 'confirmed_at', 'update_time',
            ])
    created_document = document is None
    if created_document:
        document = PackListDocument.objects.create(
            openid=openid,
            asn_code=asn_code,
            version=next_version,
            source_type=source_type,
            content_hash=str(content_hash or '')[:64],
            is_current=True,
            has_serials=has_serials,
            package_qty=package_qty,
            note=str(note or ''),
            late_reference=bool(late_reference or receiving_started),
            created_by=_operator_name(request, openid),
        )
    import_batch = None
    if content_hash:
        import_batch = PackListImportBatch.objects.create(
            openid=openid,
            asn_code=asn_code,
            import_type=PackListImportBatch.PACK_LIST,
            content_hash=str(content_hash)[:64],
            row_count=len(normalized_rows),
            source_type=source_type,
            imported_by=_operator_name(request, openid),
            note=str(note or ''),
        )
        document.import_batch = import_batch
        document.save(update_fields=['import_batch', 'update_time'])
    if document.package_qty > 0 and int(asn.package_qty or 0) != document.package_qty:
        asn.package_qty = document.package_qty
        asn.save(update_fields=['package_qty', 'update_time'])
    for row in normalized_rows:
        PackListLine.objects.create(
            pack_list=document,
            openid=openid,
            asn_code=asn_code,
            goods_code=row['goods_code'],
            customer_goods_code=row['customer_goods_code'],
            is_current=True,
            customer_ssku=row['customer_ssku'],
            goods_qty=row['goods_qty'],
            total_qty=row['total_qty'],
            package_type=row['package_type'],
            goods_desc=row['goods_desc'],
            goods_weight=row['goods_weight'],
            goods_volume=row['goods_volume'],
            source_row=row['source_row'],
        )
        if row['serial_number']:
            _save_expected(
                openid,
                request,
                asn_code,
                row['goods_code'],
                row['serial_number'],
                row=row,
                source='pack_list',
                pack_list=document,
                import_batch=import_batch,
            )
    return document, import_batch, created_document


def _reconcile_pack_list(document):
    expected = {
        record.serial_number: record.goods_code
        for record in document.serial_records.filter(is_expected=True)
    }
    records = AsnSerialRecord.objects.filter(openid=document.openid, asn_code=document.asn_code)
    for record in records.filter(status__in=[AsnSerialRecord.UNVERIFIED, AsnSerialRecord.UNEXPECTED]):
        expected_goods_code = expected.get(record.serial_number)
        record.pack_list = document
        if expected_goods_code and expected_goods_code == record.goods_code:
            record.is_expected = True
            record.expected_goods_code = expected_goods_code
            if record.damaged:
                record.status = AsnSerialRecord.DAMAGED
            elif record.scan_count > 1:
                record.status = AsnSerialRecord.DUPLICATE
            else:
                record.status = AsnSerialRecord.ACCEPTED
        elif document.has_serials:
            record.status = AsnSerialRecord.UNEXPECTED
        record.save(update_fields=['pack_list', 'is_expected', 'expected_goods_code', 'status', 'update_time'])


class PackListListView(APIView):
    def get(self, request):
        openid = _openid(request)
        asn_code = _clean(request.query_params.get('asn_code'))
        documents = PackListDocument.objects.filter(openid=openid)
        if asn_code:
            documents = documents.filter(asn_code=asn_code)
        return Response({
            'count': documents.count(),
            'results': [_pack_list_json(document) for document in documents],
            'summary': _summary(openid, asn_code) if asn_code else None,
            'inspection_batches': [
                _inspection_batch_json(batch)
                for batch in PackListImportBatch.objects.filter(
                    openid=openid,
                    asn_code=asn_code,
                    import_type=PackListImportBatch.RECEIVING_ACCEPTANCE,
                )[:50]
            ] if asn_code else [],
        })


class PackListCreateView(APIView):
    def post(self, request):
        openid = _openid(request)
        data = request.data
        asn_code = _clean(data.get('asn_code'))
        rows = data.get('rows') or []
        if not asn_code or not rows:
            raise APIException({'detail': 'ASN Code and Pack List rows are required'})
        with transaction.atomic():
            document, _, _ = _create_pack_list(
                openid,
                request,
                asn_code,
                rows,
                source_type=str(data.get('source_type') or 'AI_AGENT').upper(),
                note=data.get('note'),
                package_qty=data.get('package_qty'),
                replace=str(data.get('replace', '')).lower() == 'true',
                late_reference=str(data.get('late_reference', '')).lower() == 'true',
            )
        return Response({'detail': 'success', 'document': _pack_list_json(document), 'summary': _summary(openid, asn_code)})


class PackListPreviewView(APIView):
    def post(self, request):
        openid = _openid(request)
        upload = request.FILES.get('file')
        asn_code = _clean(request.data.get('asn_code'))
        if not upload:
            raise APIException({'detail': 'Pack List Excel file is required'})
        if upload.size > 20 * 1024 * 1024:
            raise APIException({'detail': 'Pack List file is too large'})
        if not asn_code:
            raise APIException({'detail': 'ASN Code is required'})
        rows, content_hash = _pack_list_rows_from_workbook(upload)
        validation = _validate_pack_list_rows(openid, asn_code, rows)
        current_document = PackListDocument.objects.filter(
            openid=openid,
            asn_code=asn_code,
            is_current=True,
        ).first()
        duplicate_document = current_document if current_document and current_document.content_hash == content_hash else None
        receiving_started = _receiving_started(openid, asn_code)
        return Response({
            'detail': 'preview',
            'preview': _pack_list_preview_json(
                asn_code,
                validation,
                request.data.get('package_qty'),
                content_hash,
                duplicate_document=duplicate_document,
                current_document=current_document,
                receiving_started=receiving_started,
            ),
        })


class PackListImportView(APIView):
    def post(self, request):
        openid = _openid(request)
        upload = request.FILES.get('file')
        asn_code = _clean(request.data.get('asn_code'))
        if not upload:
            raise APIException({'detail': 'Pack List Excel file is required'})
        if upload.size > 20 * 1024 * 1024:
            raise APIException({'detail': 'Pack List file is too large'})
        if not asn_code:
            raise APIException({'detail': 'ASN Code is required'})
        rows, content_hash = _pack_list_rows_from_workbook(upload)
        validation = _validate_pack_list_rows(openid, asn_code, rows)
        existing_document = PackListDocument.objects.filter(
            openid=openid,
            asn_code=asn_code,
            is_current=True,
        ).first()
        if existing_document and existing_document.content_hash == content_hash:
            return Response({
                'detail': 'already_exists',
                'duplicate': True,
                'document': _pack_list_json(existing_document),
                'summary': _summary(openid, asn_code),
            })
        replaced = bool(existing_document)
        receiving_started = _receiving_started(openid, asn_code)
        late_reference = str(request.data.get('late_reference', '')).lower() == 'true'
        with transaction.atomic():
            document, _, created = _create_pack_list(
                openid,
                request,
                asn_code,
                rows,
                source_type=str(request.data.get('source_type') or 'AI_AGENT').upper(),
                content_hash=content_hash,
                note=request.data.get('note'),
                package_qty=request.data.get('package_qty'),
                replace=str(request.data.get('replace', '')).lower() == 'true',
                late_reference=late_reference,
            )
        return Response({
            'detail': 'success' if created else 'already_exists',
            'duplicate': not created,
            'replaced': replaced,
            'late_reference': late_reference or receiving_started,
            'document': _pack_list_json(document),
            'summary': _summary(openid, asn_code),
        })


class PackListConfirmView(APIView):
    def post(self, request):
        openid = _openid(request)
        try:
            document_id = int(request.data.get('id'))
        except (TypeError, ValueError):
            raise APIException({'detail': 'Pack List id is required'})
        document = PackListDocument.objects.filter(id=document_id, openid=openid, is_current=True).first()
        if not document:
            raise APIException({'detail': 'Pack List does not exist'})
        with transaction.atomic():
            document.status = PackListDocument.CONFIRMED
            document.confirmed_by = _operator_name(request, openid)
            document.confirmed_at = timezone.now()
            document.save(update_fields=['status', 'confirmed_by', 'confirmed_at', 'update_time'])
            _reconcile_pack_list(document)
        return Response({'detail': 'success', 'document': _pack_list_json(document), 'summary': _summary(openid, document.asn_code)})


class SerialImportView(APIView):
    def post(self, request, inspection=False):
        openid = _openid(request)
        upload = request.FILES.get('file')
        if not upload:
            raise APIException({'detail': 'Excel file is required'})
        if upload.size > 10 * 1024 * 1024:
            raise APIException({'detail': 'Excel file is too large'})
        mode = 'receive' if inspection else str(request.data.get('mode') or 'expected').lower()
        if mode not in ('expected', 'receive'):
            raise APIException({'detail': 'Mode must be expected or receive'})
        asn_code = _clean(request.data.get('asn_code'))
        inbound_po = _clean(request.data.get('inbound_po'))
        shipout_ref = _clean(request.data.get('shipout_ref'))
        evidence_url = _text(request.data.get('evidence_url'))
        if not asn_code:
            raise APIException({'detail': 'ASN Code is required'})
        if not inbound_po and not shipout_ref and str(request.data.get('allow_all', '')).lower() != 'true':
            raise APIException({'detail': 'Provide inbound_po or shipout_ref before importing a mixed scan sheet'})
        try:
            file_bytes = upload.read()
            upload.seek(0)
            workbook = load_workbook(BytesIO(file_bytes), read_only=True, data_only=True)
            sheet = workbook.active
            raw_headers = [cell.value for cell in next(sheet.iter_rows(min_row=1, max_row=1))]
            headers = [' '.join(str(value or '').strip().split()) for value in raw_headers]
            index = {_header_key(header): pos for pos, header in enumerate(headers) if header}
        except Exception as exc:
            raise APIException({'detail': 'Unable to read Excel file: ' + str(exc)})
        sku_column = _first_column(index, ('SKU#', 'SKU', 'Part Number', 'Goods Code', 'Item'))
        serial_column = _first_column(index, ('SN#', 'SN', 'Serial Number', 'Serial', 'Serial No'))
        if sku_column is None or serial_column is None:
            raise APIException({'detail': 'Excel must contain a SKU/Part Number and SN/Serial Number column'})
        content_hash = sha256((mode + ':' ).encode('utf-8') + file_bytes).hexdigest()
        existing_batch = PackListImportBatch.objects.filter(
            openid=openid,
            asn_code=asn_code,
            import_type=(
                PackListImportBatch.RECEIVING_ACCEPTANCE
                if mode == 'receive' else PackListImportBatch.EXPECTED_SERIALS
            ),
            content_hash=content_hash,
        ).first()
        if existing_batch:
            return Response({
                'detail': 'already_exists',
                'duplicate': True,
                'mode': mode,
                'batch_id': existing_batch.id,
                'matched_rows': existing_batch.row_count,
                'created': 0,
                'updated': 0,
                'skipped': 0,
                'errors': [],
                'batch': _inspection_batch_json(existing_batch),
                'summary': _summary(openid, asn_code),
            })
        import_batch = PackListImportBatch.objects.create(
            openid=openid,
            asn_code=asn_code,
            import_type=(
                PackListImportBatch.RECEIVING_ACCEPTANCE
                if mode == 'receive' else PackListImportBatch.EXPECTED_SERIALS
            ),
            content_hash=content_hash,
            imported_by=_operator_name(request, openid),
            note=str(request.data.get('note') or ('QC inspection import' if mode == 'receive' else 'Expected serial import')),
            evidence_url=evidence_url,
            source_type=str(request.data.get('source_type') or 'AI_AGENT').upper(),
        )
        matched = 0
        created = 0
        updated = 0
        skipped = 0
        errors = []
        for row_number, values in enumerate(sheet.iter_rows(min_row=2, values_only=True), start=2):
            def value(*names):
                pos = _first_column(index, names)
                return values[pos] if pos is not None and pos < len(values) else ''

            row_po = _clean(value('Inbound PO#', 'Inbound PO', 'PO#'))
            row_shipout = _clean(value('SHIPOUT#', 'Shipout Ref', 'Shipout'))
            if inbound_po and row_po != inbound_po:
                continue
            if shipout_ref and row_shipout != shipout_ref:
                continue
            if _first_column(index, ('Inbound PO#', 'Inbound PO', 'PO#')) is not None and not row_po and not shipout_ref:
                continue
            goods_code = _clean(value('SKU#', 'SKU', 'Part Number', 'Goods Code', 'Item'))
            serial_number = _clean(value('SN#', 'SN', 'Serial Number', 'Serial', 'Serial No'))
            if not goods_code or not serial_number:
                continue
            matched += 1
            inspection_result = value('Inspection Result', 'QC Result', 'Check Result', 'Condition', 'Result')
            row_data = {
                'double_scan_sn': value('Double-Scan SN#', 'Double Scan SN', 'Double-Scan SN'),
                'inbound_po': row_po,
                'inbound_date': value('Inbound Date', 'Date'),
                'source_location': value('Location'),
                'shipout_ref': row_shipout,
                'damaged': _is_damage_flag(value('Damaged', 'Damage', 'Damage Flag', 'Damage Status')) or _is_damage_flag(inspection_result),
                'note': value('QC Note', 'Inspection Note', 'Check Note', 'Note', 'Remarks') or inspection_result,
                'evidence_url': _text(value('Evidence URL', 'Photo URL', 'Video URL', 'Google Drive', 'Google Drive URL')) or evidence_url,
                'source_row': row_number,
                'import_batch': import_batch,
            }
            try:
                if mode == 'expected':
                    record, was_created = _save_expected(openid, request, asn_code, goods_code, serial_number, row=row_data, source='excel', import_batch=import_batch)
                else:
                    record, was_created = _scan(
                        openid,
                        request,
                        asn_code,
                        goods_code,
                        serial_number,
                        damaged=row_data['damaged'],
                        row=row_data,
                        source='inspection' if mode == 'receive' else 'excel',
                        import_batch=import_batch,
                    )
                created += int(was_created)
                updated += int(not was_created)
            except Exception as exc:
                skipped += 1
                if len(errors) < 50:
                    errors.append({'row': row_number, 'sku': goods_code, 'sn': serial_number, 'detail': str(exc)})
        import_batch.row_count = matched
        import_batch.matched_count = matched
        touched_records = AsnSerialRecord.objects.filter(import_batch=import_batch)
        import_batch.accepted_count = touched_records.filter(status=AsnSerialRecord.ACCEPTED).count()
        import_batch.exception_count = touched_records.filter(
            status__in=EXCEPTION_STATUSES,
            exception_resolved=False,
        ).count()
        import_batch.status = (
            PackListImportBatch.PARTIAL if errors else
            PackListImportBatch.EXCEPTION if import_batch.exception_count else
            PackListImportBatch.PASSED
        )
        import_batch.save(update_fields=[
            'row_count', 'matched_count', 'accepted_count', 'exception_count', 'status',
        ])
        return Response({
            'detail': 'success' if not errors else 'partial_success',
            'mode': mode,
            'batch_id': import_batch.id,
            'matched_rows': matched,
            'created': created,
            'updated': updated,
            'skipped': skipped,
            'errors': errors,
            'batch': _inspection_batch_json(import_batch),
            'summary': _summary(openid, asn_code),
        })


class InspectionBatchListView(APIView):
    """Return QC inspection import history without exposing uploaded files."""

    def get(self, request):
        openid = _openid(request)
        asn_code = _clean(request.query_params.get('asn_code'))
        if not asn_code:
            raise APIException({'detail': 'ASN Code is required'})
        batches = PackListImportBatch.objects.filter(
            openid=openid,
            asn_code=asn_code,
            import_type=PackListImportBatch.RECEIVING_ACCEPTANCE,
        )[:50]
        return Response({
            'count': batches.count(),
            'results': [_inspection_batch_json(batch) for batch in batches],
        })
