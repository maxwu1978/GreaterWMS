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

from .models import AsnSerialRecord, PackListDocument, PackListLine


EXCEPTION_STATUSES = {
    AsnSerialRecord.UNEXPECTED,
    AsnSerialRecord.DUPLICATE,
    AsnSerialRecord.WRONG_SKU,
    AsnSerialRecord.DAMAGED,
    AsnSerialRecord.REJECTED,
}


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
        status=PackListDocument.CONFIRMED,
    ).order_by('-version', '-id').first()


def _pack_list_json(document):
    serials = document.serial_records.all()
    return {
        'id': document.id,
        'asn_code': document.asn_code,
        'version': document.version,
        'source_type': document.source_type,
        'source_file': document.source_file,
        'source_sha256': document.source_sha256,
        'source_url': document.source_url,
        'status': document.status,
        'has_serials': document.has_serials,
        'package_qty': document.package_qty,
        'note': document.note,
        'created_by': document.created_by,
        'confirmed_by': document.confirmed_by,
        'confirmed_at': document.confirmed_at.isoformat() if document.confirmed_at else None,
        'create_time': document.create_time.isoformat() if document.create_time else None,
        'line_count': document.lines.count(),
        'total_qty': sum(line.goods_qty for line in document.lines.all()),
        'lines': [
            {
                'goods_code': line.goods_code,
                'customer_goods_code': line.customer_goods_code,
                'goods_qty': line.goods_qty,
                'goods_desc': line.goods_desc,
                'source_row': line.source_row,
            }
            for line in document.lines.all()
        ],
        'expected_serial_count': serials.filter(is_expected=True).count(),
        'received_serial_count': serials.filter(is_received=True).count(),
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
        'source_file': record.source_file,
        'source_row': record.source_row,
        'status': record.status,
        'is_expected': record.is_expected,
        'is_received': record.is_received,
        'scan_count': record.scan_count,
        'damaged': record.damaged,
        'note': record.note,
        'exception_resolved': record.exception_resolved,
        'exception_resolution_action': record.exception_resolution_action,
        'exception_resolution_note': record.exception_resolution_note,
        'exception_resolved_by': record.exception_resolved_by,
        'exception_resolved_at': record.exception_resolved_at.isoformat() if record.exception_resolved_at else None,
        'expected_by': record.expected_by,
        'received_by': record.received_by,
        'expected_at': record.expected_at.isoformat() if record.expected_at else None,
        'received_at': record.received_at.isoformat() if record.received_at else None,
        'pack_list_id': record.pack_list_id,
    }


def _summary(openid, asn_code):
    details = AsnDetailModel.objects.filter(openid=openid, asn_code=asn_code, is_delete=False)
    records = AsnSerialRecord.objects.filter(openid=openid, asn_code=asn_code)
    pack_lists = PackListDocument.objects.filter(openid=openid, asn_code=asn_code)
    current_pack_list = _current_pack_list(openid, asn_code)
    pending_pack_list = pack_lists.filter(status=PackListDocument.PENDING).order_by('-version', '-id').first()
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
        exception_count = line_records.filter(status__in=exception_statuses, exception_resolved=False).count()
        missing_count = line_records.filter(is_expected=True, is_received=False, exception_resolved=False).count()
        accepted_for_putaway = accepted_count + resolved_count
        quantity_exception_qty = 0 if detail.exception_resolved else (
            int(detail.goods_shortage_qty or 0)
            + int(detail.goods_more_qty or 0)
            + int(detail.goods_damage_qty or 0)
        )
        lines.append({
            'goods_code': detail.goods_code,
            'planned_qty': detail.goods_qty,
            'expected_serial_count': expected_count,
            'received_serial_count': received_count,
            'accepted_serial_count': accepted_count,
            'resolved_exception_count': resolved_count,
            'missing_serial_count': missing_count,
            'exception_count': exception_count,
            'quantity_exception_qty': quantity_exception_qty,
            'quantity_exception_resolved': bool(detail.exception_resolved),
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
    quantity_exception_total = sum(
        0 if detail.exception_resolved else (
            int(detail.goods_shortage_qty or 0)
            + int(detail.goods_more_qty or 0)
            + int(detail.goods_damage_qty or 0)
        )
        for detail in details
    )
    return {
        'asn_code': asn_code,
        'pack_list_present': pack_lists.exists(),
        'pack_list_confirmed': bool(current_pack_list),
        'pack_list_has_serials': bool(current_pack_list and current_pack_list.has_serials),
        'current_pack_list': _pack_list_json(current_pack_list) if current_pack_list else None,
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
        'total_expected_serials': records.filter(is_expected=True).count(),
        'total_received_serials': records.filter(is_received=True).count(),
        'total_accepted_serials': accepted_total,
        'total_resolved_exceptions': resolved_total,
        'total_accepted_for_putaway': accepted_total + resolved_total,
        'total_exception_serials': exception_total,
        'total_missing_serials': missing_total,
        'total_quantity_exceptions': quantity_exception_total,
        'ready_for_putaway': (
            quantity_exception_total == 0 and (
                records.count() == 0
                or (not strict_serial_check and exception_total == 0)
                or (strict_serial_check and exception_total == 0 and missing_total == 0 and accepted_total + resolved_total >= records.filter(is_expected=True).count())
            )
        ),
    }


def _save_expected(openid, request, asn_code, goods_code, serial_number, row=None, source='manual', pack_list=None):
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
        record.source_file = str(metadata.get('source_file') or record.source_file)
        record.source_row = int(metadata.get('source_row') or record.source_row or 0)
        record.pack_list = pack_list or record.pack_list
        record.expected_by = _operator_name(request, openid)
        record.expected_at = record.expected_at or now
        if record.is_received and record.scanned_goods_code == goods_code and record.status not in EXCEPTION_STATUSES:
            record.status = AsnSerialRecord.ACCEPTED
            record.exception_resolved = False
            record.exception_resolution_action = ''
            record.exception_resolution_note = ''
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
        source_file=str(metadata.get('source_file') or ''),
        source_row=int(metadata.get('source_row') or 0),
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


def _scan(openid, request, asn_code, goods_code, serial_number, damaged=False, row=None, source='manual'):
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
    if record:
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
        record.source_file = str(metadata.get('source_file') or record.source_file)
        record.source_row = int(metadata.get('source_row') or record.source_row or 0)
        record.damaged = record.damaged or bool(damaged)
        if record.scan_count > 1:
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
        source_file=str(metadata.get('source_file') or ''),
        source_row=int(metadata.get('source_row') or 0),
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


SERIAL_EXCEPTION_ACTIONS = {'ACCEPT_EXCEPTION', 'WAIVE_MISSING', 'REOPEN'}


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
            raise APIException({'detail': 'Action must be ACCEPT_EXCEPTION, WAIVE_MISSING, or REOPEN'})
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
        if action == 'REOPEN':
            if not record.exception_resolved:
                raise APIException({'detail': 'This serial exception is already open'})
            record.exception_resolved = False
            record.exception_resolution_action = ''
            record.exception_resolution_note = ''
            record.exception_resolved_by = ''
            record.exception_resolved_at = None
        else:
            record.exception_resolved = True
            record.exception_resolution_action = action
            record.exception_resolution_note = _resolution_note(data)
            record.exception_resolved_by = _operator_name(request, openid)
            record.exception_resolved_at = timezone.now()
        record.save(update_fields=[
            'exception_resolved',
            'exception_resolution_action',
            'exception_resolution_note',
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
        if action not in {'ACCEPT_EXCEPTION', 'REOPEN'}:
            raise APIException({'detail': 'Action must be ACCEPT_EXCEPTION or REOPEN'})
        detail = AsnDetailModel.objects.filter(
            openid=openid,
            asn_code=asn_code,
            goods_code=goods_code,
            is_delete=False,
        ).first()
        if not detail:
            raise APIException({'detail': 'ASN detail does not exist'})
        quantity = int(detail.goods_shortage_qty or 0) + int(detail.goods_more_qty or 0) + int(detail.goods_damage_qty or 0)
        if action == 'ACCEPT_EXCEPTION' and quantity <= 0:
            raise APIException({'detail': 'This ASN detail has no quantity exception'})
        if action == 'ACCEPT_EXCEPTION' and not _resolution_note(data):
            raise APIException({'detail': 'A resolution note is required'})
        if action == 'REOPEN':
            if not detail.exception_resolved:
                raise APIException({'detail': 'This quantity exception is already open'})
            detail.exception_resolved = False
            detail.exception_resolution_action = ''
            detail.exception_resolution_note = ''
            detail.exception_resolved_by = ''
            detail.exception_resolved_at = None
        else:
            detail.exception_resolved = True
            detail.exception_resolution_action = action
            detail.exception_resolution_note = _resolution_note(data)
            detail.exception_resolved_by = _operator_name(request, openid)
            detail.exception_resolved_at = timezone.now()
        detail.save(update_fields=[
            'exception_resolved',
            'exception_resolution_action',
            'exception_resolution_note',
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
    qty_column = _first_column(index, ('Qty', 'Quantity', 'Total Qty', 'Goods Qty', 'ASN Qty'))
    serial_column = _first_column(index, ('SN#', 'SN', 'Serial Number', 'Serial', 'Serial No'))
    customer_sku_column = _first_column(index, ('Customer SKU', 'Customer Part Number', 'Customer Item'))
    desc_column = _first_column(index, ('Description', 'Goods Description', 'Product Description'))
    weight_column = _first_column(index, ('Weight', 'Goods Weight'))
    volume_column = _first_column(index, ('Volume', 'Goods Volume'))
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
            'serial_number': serial_number,
            'goods_qty': qty,
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
            'serial_number': serial_number,
            'goods_qty': qty,
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


def _pack_list_preview_json(asn_code, validation, package_qty, source_sha256, duplicate_document=None):
    return {
        'asn_code': asn_code,
        'status': 'DUPLICATE' if duplicate_document else 'PREVIEW',
        'source_sha256': source_sha256,
        'row_count': len(validation['rows']),
        'total_qty': validation['total_qty'],
        'has_serials': validation['has_serials'],
        'expected_serial_count': validation['expected_serial_count'],
        'package_qty': max(0, int(package_qty or 0)),
        'duplicate_document': _pack_list_json(duplicate_document) if duplicate_document else None,
        'lines': [
            {
                'goods_code': row['goods_code'],
                'customer_goods_code': row['customer_goods_code'],
                'goods_qty': row['goods_qty'],
                'serial_number': row['serial_number'],
                'goods_desc': row['goods_desc'],
                'source_row': row['source_row'],
            }
            for row in validation['rows']
        ],
    }


def _create_pack_list(openid, request, asn_code, rows, source_type='MANUAL', source_file='', source_sha256='', source_url='', note='', package_qty=0):
    validation = _validate_pack_list_rows(openid, asn_code, rows)
    asn = validation['asn']
    normalized_rows = validation['rows']
    has_serials = validation['has_serials']
    last_version = PackListDocument.objects.filter(openid=openid, asn_code=asn_code).order_by('-version').values_list('version', flat=True).first() or 0
    document = PackListDocument.objects.create(
        openid=openid,
        asn_code=asn_code,
        version=int(last_version) + 1,
        source_type=source_type if source_type in dict(PackListDocument.SOURCE_TYPES) else 'MANUAL',
        source_file=str(source_file or '')[:255],
        source_sha256=str(source_sha256 or '')[:64],
        source_url=str(source_url or '')[:1000],
        has_serials=has_serials,
        package_qty=max(0, int(package_qty or 0)),
        note=str(note or ''),
        raw_payload={'row_count': len(normalized_rows), 'has_serials': has_serials},
        created_by=_operator_name(request, openid),
    )
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
            goods_qty=row['goods_qty'],
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
            )
    return document


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
            document = _create_pack_list(
                openid,
                request,
                asn_code,
                rows,
                source_type=str(data.get('source_type') or 'MANUAL').upper(),
                source_url=data.get('source_url'),
                note=data.get('note'),
                package_qty=data.get('package_qty'),
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
        rows, file_hash = _pack_list_rows_from_workbook(upload)
        validation = _validate_pack_list_rows(openid, asn_code, rows)
        duplicate_document = PackListDocument.objects.filter(
            openid=openid,
            asn_code=asn_code,
            source_sha256=file_hash,
        ).order_by('-id').first()
        return Response({
            'detail': 'preview',
            'preview': _pack_list_preview_json(
                asn_code,
                validation,
                request.data.get('package_qty'),
                file_hash,
                duplicate_document=duplicate_document,
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
        rows, file_hash = _pack_list_rows_from_workbook(upload)
        existing_document = PackListDocument.objects.filter(
            openid=openid,
            asn_code=asn_code,
            source_sha256=file_hash,
        ).order_by('-id').first()
        if existing_document:
            return Response({
                'detail': 'already_exists',
                'duplicate': True,
                'document': _pack_list_json(existing_document),
                'summary': _summary(openid, asn_code),
            })
        with transaction.atomic():
            document = _create_pack_list(
                openid,
                request,
                asn_code,
                rows,
                source_type=str(request.data.get('source_type') or 'UPLOAD').upper(),
                source_file=upload.name,
                source_sha256=file_hash,
                source_url=request.data.get('source_url'),
                note=request.data.get('note'),
                package_qty=request.data.get('package_qty'),
            )
        return Response({
            'detail': 'success',
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
        document = PackListDocument.objects.filter(id=document_id, openid=openid).first()
        if not document:
            raise APIException({'detail': 'Pack List does not exist'})
        with transaction.atomic():
            PackListDocument.objects.filter(
                openid=openid,
                asn_code=document.asn_code,
                status=PackListDocument.CONFIRMED,
            ).exclude(id=document.id).update(status=PackListDocument.ARCHIVED)
            document.status = PackListDocument.CONFIRMED
            document.confirmed_by = _operator_name(request, openid)
            document.confirmed_at = timezone.now()
            document.save(update_fields=['status', 'confirmed_by', 'confirmed_at', 'update_time'])
            _reconcile_pack_list(document)
        return Response({'detail': 'success', 'document': _pack_list_json(document), 'summary': _summary(openid, document.asn_code)})


class SerialImportView(APIView):
    def post(self, request):
        openid = _openid(request)
        upload = request.FILES.get('file')
        if not upload:
            raise APIException({'detail': 'Excel file is required'})
        if upload.size > 10 * 1024 * 1024:
            raise APIException({'detail': 'Excel file is too large'})
        mode = str(request.data.get('mode') or 'expected').lower()
        if mode not in ('expected', 'receive'):
            raise APIException({'detail': 'Mode must be expected or receive'})
        asn_code = _clean(request.data.get('asn_code'))
        inbound_po = _clean(request.data.get('inbound_po'))
        shipout_ref = _clean(request.data.get('shipout_ref'))
        if not asn_code:
            raise APIException({'detail': 'ASN Code is required'})
        if not inbound_po and not shipout_ref and str(request.data.get('allow_all', '')).lower() != 'true':
            raise APIException({'detail': 'Provide inbound_po or shipout_ref before importing a mixed scan sheet'})
        try:
            workbook = load_workbook(upload, read_only=True, data_only=True)
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
        source_file = str(upload.name)[:255]
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
            row_data = {
                'double_scan_sn': value('Double-Scan SN#', 'Double Scan SN', 'Double-Scan SN'),
                'inbound_po': row_po,
                'inbound_date': value('Inbound Date', 'Date'),
                'source_location': value('Location'),
                'shipout_ref': row_shipout,
                'source_file': source_file,
                'source_row': row_number,
            }
            try:
                if mode == 'expected':
                    record, was_created = _save_expected(openid, request, asn_code, goods_code, serial_number, row=row_data, source='excel')
                else:
                    record, was_created = _scan(openid, request, asn_code, goods_code, serial_number, row=row_data, source='excel')
                created += int(was_created)
                updated += int(not was_created)
            except Exception as exc:
                skipped += 1
                if len(errors) < 50:
                    errors.append({'row': row_number, 'sku': goods_code, 'sn': serial_number, 'detail': str(exc)})
        return Response({
            'detail': 'success' if not errors else 'partial_success',
            'mode': mode,
            'source_file': source_file,
            'matched_rows': matched,
            'created': created,
            'updated': updated,
            'skipped': skipped,
            'errors': errors,
            'summary': _summary(openid, asn_code),
        })
