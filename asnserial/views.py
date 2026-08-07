from datetime import date, datetime

from django.db import IntegrityError, transaction
from django.utils import timezone
from openpyxl import load_workbook
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.exceptions import APIException

from asn.models import AsnDetailModel, AsnListModel
from staff.models import ListModel as Staff

from .models import AsnSerialRecord


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
        'expected_by': record.expected_by,
        'received_by': record.received_by,
        'expected_at': record.expected_at.isoformat() if record.expected_at else None,
        'received_at': record.received_at.isoformat() if record.received_at else None,
    }


def _summary(openid, asn_code):
    details = AsnDetailModel.objects.filter(openid=openid, asn_code=asn_code, is_delete=False)
    records = AsnSerialRecord.objects.filter(openid=openid, asn_code=asn_code)
    lines = []
    for detail in details:
        line_records = records.filter(goods_code=detail.goods_code)
        expected_count = line_records.filter(is_expected=True).count()
        received_count = line_records.filter(is_received=True).count()
        accepted_count = line_records.filter(status=AsnSerialRecord.ACCEPTED).count()
        exception_count = line_records.filter(status__in=EXCEPTION_STATUSES).count()
        missing_count = line_records.filter(is_expected=True, is_received=False).count()
        lines.append({
            'goods_code': detail.goods_code,
            'planned_qty': detail.goods_qty,
            'expected_serial_count': expected_count,
            'received_serial_count': received_count,
            'accepted_serial_count': accepted_count,
            'missing_serial_count': missing_count,
            'exception_count': exception_count,
            'ready_for_putaway': (
                not line_records.exists()
                or (missing_count == 0 and exception_count == 0 and accepted_count >= detail.goods_actual_qty)
            ),
        })
    exception_total = records.filter(status__in=EXCEPTION_STATUSES).count()
    missing_total = records.filter(is_expected=True, is_received=False).count()
    return {
        'asn_code': asn_code,
        'lines': lines,
        'total_expected_serials': records.filter(is_expected=True).count(),
        'total_received_serials': records.filter(is_received=True).count(),
        'total_accepted_serials': records.filter(status=AsnSerialRecord.ACCEPTED).count(),
        'total_exception_serials': exception_total,
        'total_missing_serials': missing_total,
        'ready_for_putaway': records.count() == 0 or (exception_total == 0 and missing_total == 0),
    }


def _save_expected(openid, request, asn_code, goods_code, serial_number, row=None, source='manual'):
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
        record.expected_by = _operator_name(request, openid)
        record.expected_at = record.expected_at or now
        if record.is_received and record.scanned_goods_code == goods_code and record.status not in EXCEPTION_STATUSES:
            record.status = AsnSerialRecord.ACCEPTED
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
    )
    return record, True


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
            record.status = AsnSerialRecord.UNEXPECTED
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
        status=AsnSerialRecord.DAMAGED if damaged else AsnSerialRecord.UNEXPECTED,
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
            index = {header: pos for pos, header in enumerate(headers) if header}
        except Exception as exc:
            raise APIException({'detail': 'Unable to read Excel file: ' + str(exc)})
        if 'SKU#' not in index or 'SN#' not in index:
            raise APIException({'detail': 'Excel must contain SKU# and SN# columns'})
        source_file = str(upload.name)[:255]
        matched = 0
        created = 0
        updated = 0
        skipped = 0
        errors = []
        for row_number, values in enumerate(sheet.iter_rows(min_row=2, values_only=True), start=2):
            def value(name):
                pos = index.get(name)
                return values[pos] if pos is not None and pos < len(values) else ''

            row_po = _clean(value('Inbound PO#'))
            row_shipout = _clean(value('SHIPOUT#'))
            if inbound_po and row_po != inbound_po:
                continue
            if shipout_ref and row_shipout != shipout_ref:
                continue
            if 'Inbound PO#' in index and not row_po and not shipout_ref:
                continue
            goods_code = _clean(value('SKU#'))
            serial_number = _clean(value('SN#'))
            if not goods_code or not serial_number:
                continue
            matched += 1
            row_data = {
                'double_scan_sn': value('Double-Scan SN#'),
                'inbound_po': row_po,
                'inbound_date': value('Inbound Date'),
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
