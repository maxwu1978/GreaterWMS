from collections import defaultdict

from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import serializers as drf_serializers

from asn.models import AsnDetailModel, AsnListModel
from asnserial.models import AsnSerialRecord
from binset.models import ListModel as BinModel
from cyclecount.models import QTYRecorder
from dn.models import DnDetailModel, DnListModel, DnSerialAllocation
from driver.models import ListModel as DriverModel
from goods.models import ListModel as GoodsModel
from stock.models import StockBinModel, StockListModel
from utils.md5 import Md5

from .models import (
    ReceivingDetail,
    ReceivingPutaway,
    ReceivingRecord,
    ReceivingReconciliationEvent,
    ReceivingSerial,
)
from .serializers import ReceivingRecordSerializer
from .services import assert_receiving_can_claim_asn


ACCEPT_FOR_PUTAWAY = 'ACCEPT_FOR_PUTAWAY'
HOLD_QUARANTINE = 'HOLD_QUARANTINE'
REJECT_RETURN = 'REJECT_RETURN'
ACCEPT_VARIANCE = 'ACCEPT_VARIANCE'
RECOUNT_REQUIRED = 'RECOUNT_REQUIRED'


def _openid(request):
    value = getattr(getattr(request, 'auth', None), 'openid', '')
    if not value:
        raise APIException({'detail': 'Authentication is required'})
    return value


def _operator_name(request):
    identity = getattr(request, 'auth', None)
    operator_id = request.META.get('HTTP_OPERATOR', '')
    if operator_id and not getattr(identity, 'is_admin', False):
        from staff.models import ListModel as StaffModel
        staff = StaffModel.objects.filter(
            openid=_openid(request),
            id=operator_id,
            is_delete=False,
        ).first()
        if staff is None:
            raise ValidationError({'detail': 'Operator does not exist'})
        return staff.staff_name
    return str(getattr(identity, 'staff_name', '') or '')


def _ensure_roles(request, *roles):
    identity = getattr(request, 'auth', None)
    if getattr(identity, 'is_admin', False):
        return
    role = str(getattr(identity, 'staff_type', '') or '').strip().casefold()
    if role not in {value.casefold() for value in roles}:
        raise ValidationError({'detail': 'This operation is not allowed for your role'})


def _parse_datetime(value, label):
    if value in (None, ''):
        return timezone.now()
    try:
        parsed = drf_serializers.DateTimeField().to_internal_value(value)
    except Exception as exc:
        raise ValidationError({'detail': '%s is invalid: %s' % (label, exc)})
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


def _integer(value, label, minimum=0):
    try:
        result = int(value or 0)
    except (TypeError, ValueError):
        raise ValidationError({'detail': '%s must be an integer' % label})
    if result < minimum:
        raise ValidationError({'detail': '%s must be >= %s' % (label, minimum)})
    return result


def _receipt_no(openid):
    prefix = 'RC' + timezone.now().strftime('%Y%m%d')
    existing = ReceivingRecord.objects.filter(openid=openid, receipt_no__startswith=prefix).count()
    number = existing + 1
    candidate = '%s-%04d' % (prefix, number)
    while ReceivingRecord.objects.filter(openid=openid, receipt_no=candidate).exists():
        number += 1
        candidate = '%s-%04d' % (prefix, number)
    return candidate


def _record_data(record):
    return ReceivingRecordSerializer(record).data


def _detail_has_open_exception(detail):
    return bool(detail.exception_note) and detail.resolution_action not in (
        ACCEPT_FOR_PUTAWAY,
        REJECT_RETURN,
    )


def _all_accepted_putaway(record):
    return all(
        not _detail_has_open_exception(detail)
        and int(detail.putaway_qty or 0) >= int(detail.accepted_qty or 0)
        for detail in record.details.all()
    )


def _refresh_record_after_putaway(record, operator=''):
    if any(_detail_has_open_exception(detail) for detail in record.details.all()):
        record.status = ReceivingRecord.QC_EXCEPTION
        return
    if not _all_accepted_putaway(record):
        record.status = ReceivingRecord.PUTAWAY_PENDING
        return
    record.status = ReceivingRecord.PUTAWAY_COMPLETE
    if record.reconciliation_status in (ReceivingRecord.MATCHED, ReceivingRecord.RESOLVED):
        record.status = ReceivingRecord.CLOSED
        record.closed_by = operator
        record.closed_at = timezone.now()


def _goods_master(openid, goods_code):
    goods = GoodsModel.objects.filter(
        openid=openid,
        goods_code=goods_code,
        is_delete=False,
    ).first()
    if goods is None:
        raise ValidationError({'detail': 'SKU does not exist: %s' % goods_code})
    return goods


def _stock_for_update(openid, goods_code, goods_master):
    stock = StockListModel.objects.select_for_update().filter(
        openid=openid,
        goods_code=goods_code,
    ).first()
    if stock is None:
        stock = StockListModel(
            openid=openid,
            goods_code=goods_code,
            goods_desc=goods_master.goods_desc,
            goods_qty=0,
            onhand_stock=0,
            can_order_stock=0,
            supplier=goods_master.goods_supplier or '',
        )
        stock.save()
    return stock


def _apply_linked_asn_inventory(record, detail, actual_qty):
    """Move a linked ASN reservation to the received total exactly once."""
    if not record.linked_asn_code:
        return
    asn_detail = AsnDetailModel.objects.select_for_update().filter(
        openid=record.openid,
        asn_code=record.linked_asn_code,
        goods_code=detail.goods_code,
        is_delete=False,
    ).first()
    if asn_detail is None:
        raise ValidationError({'detail': 'Linked ASN SKU does not exist: %s' % detail.goods_code})
    goods_master = _goods_master(record.openid, detail.goods_code)
    stock = _stock_for_update(record.openid, detail.goods_code, goods_master)
    expected_qty = int(detail.asn_expected_qty or asn_detail.goods_qty or 0)
    if not detail.asn_stock_released:
        reserved_qty = min(max(int(stock.asn_stock or 0), 0), expected_qty)
        stock.goods_qty = max(
            0,
            int(stock.goods_qty or 0) + int(actual_qty) - reserved_qty,
        )
        stock.asn_stock = max(int(stock.asn_stock or 0) - reserved_qty, 0)
        detail.asn_expected_qty = expected_qty
        detail.asn_stock_released = True
    else:
        stock.goods_qty = max(
            0,
            int(stock.goods_qty or 0) + int(actual_qty) - int(detail.inventory_qty_applied or 0),
        )
    detail.inventory_qty_applied = int(actual_qty)
    stock.save(update_fields=['goods_qty', 'asn_stock', 'update_time'])


def _release_arrived_asn_reservation(record, asn_code):
    """Remove an ASN reservation when a prior unlinked receipt is reconciled."""
    asn_details = {
        detail.goods_code: detail
        for detail in AsnDetailModel.objects.select_for_update().filter(
            openid=record.openid,
            asn_code=asn_code,
            is_delete=False,
        )
    }
    for receiving_detail in record.details.select_for_update():
        asn_detail = asn_details.get(receiving_detail.goods_code)
        if asn_detail is None:
            raise ValidationError({'detail': 'ASN SKU does not match receiving SKU: %s' % receiving_detail.goods_code})
        if receiving_detail.asn_stock_released:
            continue
        goods_master = _goods_master(record.openid, receiving_detail.goods_code)
        stock = _stock_for_update(record.openid, receiving_detail.goods_code, goods_master)
        expected_qty = int(asn_detail.goods_qty or 0)
        reserved_qty = min(max(int(stock.asn_stock or 0), 0), expected_qty)
        stock.goods_qty = max(int(stock.goods_qty or 0) - reserved_qty, 0)
        stock.asn_stock = max(int(stock.asn_stock or 0) - reserved_qty, 0)
        stock.save(update_fields=['goods_qty', 'asn_stock', 'update_time'])
        receiving_detail.asn_expected_qty = expected_qty
        receiving_detail.asn_stock_released = True
        receiving_detail.save(update_fields=['asn_expected_qty', 'asn_stock_released', 'update_time'])


def _validate_storage_bin(openid, bin_name):
    bin_detail = BinModel.objects.filter(
        openid=openid,
        bin_name=bin_name,
        is_delete=False,
    ).first()
    if bin_detail is None:
        raise ValidationError({'detail': 'Bin does not exist: %s' % bin_name})
    if bin_detail.location_role == 'STAGING':
        raise ValidationError({'detail': 'Staging locations cannot be used for final putaway'})
    if bin_detail.bin_property in ('Damage', 'Holding', 'Inspection'):
        raise ValidationError({'detail': 'Use a storage bin for accepted inventory'})
    return bin_detail


def _serial_payload(value):
    if value is None:
        return None
    if not isinstance(value, list):
        raise ValidationError({'detail': 'serials must be a list'})
    normalized = []
    for item in value:
        if isinstance(item, dict):
            serial_number = str(item.get('serial_number') or item.get('sn') or '').strip()
            status = str(item.get('status') or ReceivingSerial.ACCEPTED).upper()
            note = str(item.get('note') or '').strip()
            evidence_url = str(item.get('evidence_url') or '').strip()
        else:
            serial_number = str(item or '').strip()
            status = ReceivingSerial.ACCEPTED
            note = ''
            evidence_url = ''
        if not serial_number:
            raise ValidationError({'detail': 'Serial number cannot be empty'})
        normalized.append({
            'serial_number': serial_number,
            'status': status,
            'note': note,
            'evidence_url': evidence_url,
        })
    return normalized


def _returned_qty(openid, source_reference, goods_code):
    return int(ReceivingDetail.objects.filter(
        openid=openid,
        goods_code=goods_code,
        receipt__openid=openid,
        receipt__source_type='OUTBOUND_RETURN',
        receipt__source_reference=source_reference,
    ).exclude(
        receipt__status=ReceivingRecord.CANCELLED,
    ).aggregate(total=Sum('actual_qty')).get('total') or 0)


class ReceivingRecordListView(APIView):
    def get(self, request):
        qs = ReceivingRecord.objects.filter(openid=_openid(request))
        status = request.GET.get('status')
        receipt_no = str(request.GET.get('receipt_no') or '').strip()
        if status:
            qs = qs.filter(status=status)
        if receipt_no:
            qs = qs.filter(receipt_no=receipt_no)
        return Response({
            'count': qs.count(),
            'results': [_record_data(record) for record in qs[:200]],
        })

    @transaction.atomic
    def post(self, request):
        _ensure_roles(request, 'Manager', 'Supervisor', 'Warehouse', 'Inbound')
        openid = _openid(request)
        data = request.data
        customer = str(data.get('customer') or data.get('owner') or '').strip()
        if not customer:
            raise ValidationError({'detail': 'Customer is required'})
        raw_details = data.get('details') or data.get('goodsData') or []
        if not isinstance(raw_details, list) or not raw_details:
            raise ValidationError({'detail': 'At least one receiving detail is required'})
        linked_asn_code = str(data.get('linked_asn_code') or '').strip()
        raw_goods_codes = []
        for raw in raw_details:
            if not isinstance(raw, dict):
                raise ValidationError({'detail': 'Each receiving detail must be an object'})
            raw_goods_codes.append(str(raw.get('goods_code') or raw.get('sku') or '').strip())

        source_type = str(data.get('source_type') or 'OPERATOR').strip().upper()
        source_reference = str(data.get('source_reference') or '').strip()
        return_details = {}
        returned_qty = {}
        linked_asn_expected_qty = {}
        if source_type != 'OUTBOUND_RETURN':
            assert_receiving_can_claim_asn(openid, customer, raw_goods_codes, linked_asn_code)
            if linked_asn_code:
                linked_asn_expected_qty = dict(AsnDetailModel.objects.filter(
                    openid=openid,
                    asn_code=linked_asn_code,
                    goods_code__in=raw_goods_codes,
                    is_delete=False,
                ).values_list('goods_code', 'goods_qty'))
        if source_type == 'OUTBOUND_RETURN':
            if not source_reference:
                raise ValidationError({'detail': 'Outbound return requires source_reference'})
            return_dn = DnListModel.objects.select_for_update().filter(
                openid=openid,
                dn_code=source_reference,
                dn_status=7,
                is_delete=False,
            ).first()
            if return_dn is None:
                raise ValidationError({'detail': 'Canceled outbound delivery note does not exist'})
            if customer and return_dn.customer and customer.casefold() != return_dn.customer.casefold():
                raise ValidationError({'detail': 'Return customer does not match the canceled delivery note'})
            return_details = {
                detail.goods_code: detail
                for detail in DnDetailModel.objects.select_for_update().filter(
                    openid=openid,
                    dn_code=source_reference,
                    dn_status=7,
                    is_delete=False,
                )
            }
            if not return_details:
                raise ValidationError({'detail': 'Canceled outbound delivery note has no returnable details'})
            returned_qty = {
                goods_code: max(
                    int(detail.returned_qty or 0),
                    _returned_qty(openid, source_reference, goods_code),
                )
                for goods_code, detail in return_details.items()
            }

        receipt_no = str(data.get('receipt_no') or '').strip() or _receipt_no(openid)
        if ReceivingRecord.objects.filter(openid=openid, receipt_no=receipt_no).exists():
            raise ValidationError({'detail': 'Receiving record already exists'})
        record = ReceivingRecord.objects.create(
            openid=openid,
            receipt_no=receipt_no,
            customer=customer,
            source_reference=source_reference,
            container_tracking=str(data.get('container_tracking') or '').strip(),
            received_at=_parse_datetime(data.get('received_at'), 'received_at'),
            status=ReceivingRecord.QC_PENDING,
            reconciliation_status=ReceivingRecord.PENDING if linked_asn_code else ReceivingRecord.NO_ASN,
            linked_asn_code=linked_asn_code,
            source_type=source_type,
            source_hash=str(data.get('source_hash') or '').strip(),
            created_by=_operator_name(request),
        )
        seen = set()
        for raw in raw_details:
            goods_code = str(raw.get('goods_code') or raw.get('sku') or '').strip()
            if not goods_code:
                raise ValidationError({'detail': 'Receiving SKU is required'})
            if goods_code in seen:
                raise ValidationError({'detail': 'Duplicate receiving SKU: %s' % goods_code})
            seen.add(goods_code)
            goods_master = _goods_master(openid, goods_code)
            return_detail = return_details.get(goods_code)
            if source_type == 'OUTBOUND_RETURN' and return_detail is None:
                raise ValidationError({'detail': 'Return SKU does not belong to the canceled delivery note: %s' % goods_code})
            default_expected_qty = int(return_detail.cancelled_qty or 0) if return_detail else 0
            expected_qty = _integer(
                raw.get('expected_qty', raw.get('goods_qty', default_expected_qty)),
                'expected_qty',
            )
            actual_qty = _integer(raw.get('actual_qty', raw.get('received_qty', 0)), 'actual_qty')
            damage_qty = _integer(raw.get('damage_qty', 0), 'damage_qty')
            if damage_qty > actual_qty:
                raise ValidationError({'detail': 'Damage quantity cannot exceed actual quantity'})
            if return_detail:
                remaining_return_qty = int(return_detail.cancelled_qty or 0) - int(returned_qty.get(goods_code, 0))
                if actual_qty > remaining_return_qty:
                    raise ValidationError({
                        'detail': 'Returned quantity exceeds the remaining canceled quantity for %s (remaining: %s)' % (
                            goods_code,
                            max(remaining_return_qty, 0),
                        ),
                    })
            ReceivingDetail.objects.create(
                receipt=record,
                openid=openid,
                goods_code=goods_code,
                customer_goods_code=str(raw.get('customer_goods_code') or '').strip(),
                goods_desc=str(raw.get('goods_desc') or goods_master.goods_desc or ''),
                expected_qty=expected_qty,
                actual_qty=actual_qty,
                accepted_qty=actual_qty - damage_qty,
                damage_qty=damage_qty,
                hold_qty=damage_qty,
                asn_expected_qty=int(linked_asn_expected_qty.get(goods_code, 0)),
                exception_note=str(raw.get('exception_note') or '').strip(),
            )
            if return_detail:
                returned_qty[goods_code] = int(returned_qty.get(goods_code, 0)) + actual_qty
                return_detail.returned_qty = returned_qty[goods_code]
                return_detail.save(update_fields=['returned_qty', 'update_time'])
        ReceivingReconciliationEvent.objects.create(
            receipt=record,
            openid=openid,
            event_type='RECEIVING_CREATED',
            operator=_operator_name(request),
            payload={'source_type': record.source_type},
        )
        return Response(_record_data(record), status=201)


class ReceivingRecordDetailView(APIView):
    def get(self, request, pk):
        record = ReceivingRecord.objects.filter(openid=_openid(request), id=pk).first()
        if record is None:
            raise ValidationError({'detail': 'Receiving record does not exist'})
        return Response(_record_data(record))


class ReceivingPutawayAssignView(APIView):
    """Assign the driver who owns the remaining receiving putaway work."""

    @transaction.atomic
    def post(self, request):
        _ensure_roles(request, 'Manager', 'Supervisor', 'Warehouse', 'Inbound')
        openid = _openid(request)
        receipt_no = str(request.data.get('receipt_no') or '').strip()
        driver_name = str(request.data.get('driver_name') or request.data.get('driver') or '').strip()
        if not receipt_no or not driver_name:
            raise ValidationError({'detail': 'receipt_no and driver_name are required'})
        record = ReceivingRecord.objects.select_for_update().filter(
            openid=openid,
            receipt_no=receipt_no,
        ).first()
        if record is None:
            raise ValidationError({'detail': 'Receiving record does not exist'})
        if record.status != ReceivingRecord.PUTAWAY_PENDING:
            raise ValidationError({'detail': 'Driver can only be assigned when putaway is pending'})
        if not DriverModel.objects.filter(
            openid=openid,
            driver_name=driver_name,
            is_delete=False,
        ).exists():
            raise ValidationError({'detail': 'Putaway driver does not exist'})
        remaining = sum(
            max(int(detail.accepted_qty or 0) - int(detail.putaway_qty or 0), 0)
            for detail in record.details.select_for_update()
        )
        if remaining <= 0:
            raise ValidationError({'detail': 'No remaining quantity requires putaway'})
        identity = getattr(request, 'auth', None)
        role = str(getattr(identity, 'staff_type', '') or '').strip().casefold()
        if record.putaway_driver and record.putaway_driver != driver_name and role not in ('manager', 'supervisor'):
            raise ValidationError({'detail': 'Only a manager or supervisor can reassign the putaway driver'})
        record.putaway_driver = driver_name
        record.putaway_assigned_by = _operator_name(request)
        record.putaway_assigned_at = timezone.now()
        record.save(update_fields=[
            'putaway_driver', 'putaway_assigned_by', 'putaway_assigned_at', 'update_time',
        ])
        ReceivingReconciliationEvent.objects.create(
            receipt=record,
            openid=openid,
            event_type='PUTAWAY_DRIVER_ASSIGNED',
            operator=_operator_name(request),
            note='Putaway driver assigned: %s' % driver_name,
            payload={'driver_name': driver_name},
        )
        return Response(_record_data(record))


class ReceivingQcCompleteView(APIView):
    @transaction.atomic
    def post(self, request):
        _ensure_roles(request, 'Manager', 'Supervisor', 'QC')
        openid = _openid(request)
        receipt_no = str(request.data.get('receipt_no') or '').strip()
        record = ReceivingRecord.objects.select_for_update().filter(
            openid=openid,
            receipt_no=receipt_no,
        ).first()
        if record is None:
            raise ValidationError({'detail': 'Receiving record does not exist'})
        if record.status not in (ReceivingRecord.QC_PENDING, ReceivingRecord.QC_EXCEPTION):
            raise ValidationError({'detail': 'Receiving record is not waiting for QC'})
        raw_details = request.data.get('details') or []
        if not isinstance(raw_details, list) or not raw_details:
            raise ValidationError({'detail': 'QC details are required'})
        details = {detail.goods_code: detail for detail in record.details.select_for_update()}
        submitted = set()
        has_exception = False
        for raw in raw_details:
            goods_code = str(raw.get('goods_code') or raw.get('sku') or '').strip()
            detail = details.get(goods_code)
            if detail is None:
                raise ValidationError({'detail': 'SKU does not belong to the receiving record: %s' % goods_code})
            if goods_code in submitted:
                raise ValidationError({'detail': 'Duplicate QC detail: %s' % goods_code})
            submitted.add(goods_code)
            actual_qty = _integer(raw.get('actual_qty', detail.actual_qty), 'actual_qty')
            damage_qty = _integer(raw.get('damage_qty', detail.damage_qty), 'damage_qty')
            if damage_qty > actual_qty:
                raise ValidationError({'detail': 'Damage quantity cannot exceed actual quantity'})
            serials = _serial_payload(raw.get('serials'))
            expected_serials = [str(value).strip() for value in (raw.get('expected_serials') or []) if str(value).strip()]
            serial_exception = False
            accepted_qty = actual_qty - damage_qty
            returnable_serials = set()
            already_returned_serials = set()
            if record.source_type == 'OUTBOUND_RETURN' and serials:
                allocation_rows = DnSerialAllocation.objects.select_for_update().filter(
                    openid=openid,
                    dn_code=record.source_reference,
                    goods_code=goods_code,
                    serial_number__in=[item['serial_number'] for item in serials],
                    status__in=(
                        DnSerialAllocation.SHIPPED,
                        DnSerialAllocation.RELEASED,
                        DnSerialAllocation.RETURNED,
                    ),
                )
                returnable_serials = {
                    row.serial_number for row in allocation_rows
                    if row.status in (DnSerialAllocation.SHIPPED, DnSerialAllocation.RELEASED)
                }
                already_returned_serials = {
                    row.serial_number for row in allocation_rows
                    if row.status == DnSerialAllocation.RETURNED
                }
            if serials is not None:
                ReceivingSerial.objects.filter(detail=detail).delete()
                seen_serials = set()
                accepted_serials = 0
                for item in serials:
                    serial_number = item['serial_number']
                    status = item['status']
                    if serial_number in seen_serials:
                        serial_exception = True
                        continue
                    seen_serials.add(serial_number)
                    if status not in dict(ReceivingSerial.STATUS_CHOICES):
                        raise ValidationError({'detail': 'Unsupported serial status: %s' % status})
                    if record.source_type == 'OUTBOUND_RETURN':
                        if serial_number in already_returned_serials:
                            if status == ReceivingSerial.ACCEPTED:
                                status = ReceivingSerial.DUPLICATE
                            serial_exception = True
                        elif serial_number not in returnable_serials:
                            if status == ReceivingSerial.ACCEPTED:
                                status = ReceivingSerial.UNEXPECTED
                            serial_exception = True
                    duplicate_serial = ReceivingSerial.objects.filter(
                        openid=openid,
                        serial_number=serial_number,
                        status=ReceivingSerial.ACCEPTED,
                    ).exclude(receipt=record).exists() or AsnSerialRecord.objects.filter(
                        openid=openid,
                        serial_number=serial_number,
                        status=AsnSerialRecord.ACCEPTED,
                        is_received=True,
                    ).exists()
                    if duplicate_serial and serial_number not in returnable_serials and status == ReceivingSerial.ACCEPTED:
                        status = ReceivingSerial.DUPLICATE
                        serial_exception = True
                    if status == ReceivingSerial.ACCEPTED:
                        if expected_serials and serial_number not in expected_serials:
                            status = ReceivingSerial.UNEXPECTED
                            serial_exception = True
                        else:
                            accepted_serials += 1
                    if status != ReceivingSerial.ACCEPTED:
                        serial_exception = True
                    ReceivingSerial.objects.create(
                        detail=detail,
                        receipt=record,
                        openid=openid,
                        goods_code=goods_code,
                        serial_number=serial_number,
                        status=status,
                        scanned_goods_code=str(item.get('scanned_goods_code') or goods_code),
                        note=item['note'],
                        evidence_url=item['evidence_url'],
                        scanned_by=_operator_name(request),
                    )
                if expected_serials:
                    missing = set(expected_serials) - seen_serials
                    unexpected = seen_serials - set(expected_serials)
                    serial_exception = serial_exception or bool(missing or unexpected)
                if actual_qty != len(seen_serials):
                    serial_exception = True
                accepted_qty = min(accepted_qty, accepted_serials)
                if record.source_type == 'OUTBOUND_RETURN':
                    consumed_serials = returnable_serials.intersection(seen_serials)
                    if consumed_serials:
                        DnSerialAllocation.objects.select_for_update().filter(
                            openid=openid,
                            dn_code=record.source_reference,
                            goods_code=goods_code,
                            serial_number__in=consumed_serials,
                            status__in=(DnSerialAllocation.SHIPPED, DnSerialAllocation.RELEASED),
                        ).update(status=DnSerialAllocation.RETURNED, update_time=timezone.now())
            exception_note = str(raw.get('exception_note') or '').strip()
            if detail.expected_qty and actual_qty != detail.expected_qty:
                has_exception = True
            if damage_qty or serial_exception:
                has_exception = True
            detail.actual_qty = actual_qty
            detail.damage_qty = damage_qty
            detail.accepted_qty = max(accepted_qty, 0)
            detail.hold_qty = max(actual_qty - detail.accepted_qty, 0)
            detail.exception_note = exception_note
            if (detail.expected_qty and actual_qty != detail.expected_qty or damage_qty or serial_exception) and not exception_note:
                detail.exception_note = 'QC variance requires review'
            _apply_linked_asn_inventory(record, detail, actual_qty)
            detail.save()
        missing = set(details) - submitted
        if missing:
            raise ValidationError({'detail': 'Missing QC details: %s' % ', '.join(sorted(missing))})
        record.qc_by = _operator_name(request)
        record.status = ReceivingRecord.QC_EXCEPTION if has_exception else ReceivingRecord.PUTAWAY_PENDING
        record.reconciliation_status = ReceivingRecord.PENDING if record.linked_asn_code else ReceivingRecord.NO_ASN
        detail_notes = '; '.join(
            sorted({detail.exception_note for detail in details.values() if detail.exception_note})
        )
        record.exception_note = str(request.data.get('exception_note') or '').strip() or detail_notes
        record.save()
        ReceivingReconciliationEvent.objects.create(
            receipt=record,
            openid=openid,
            event_type='QC_COMPLETED',
            operator=_operator_name(request),
            note=record.exception_note,
            payload={'has_exception': has_exception},
        )
        return Response(_record_data(record))


class ReceivingExceptionResolveView(APIView):
    @transaction.atomic
    def post(self, request):
        _ensure_roles(request, 'Manager', 'Supervisor', 'QC', 'Warehouse')
        openid = _openid(request)
        receipt_no = str(request.data.get('receipt_no') or '').strip()
        record = ReceivingRecord.objects.select_for_update().filter(openid=openid, receipt_no=receipt_no).first()
        if record is None:
            raise ValidationError({'detail': 'Receiving record does not exist'})
        action = str(request.data.get('action') or '').strip().upper()
        if action not in (ACCEPT_FOR_PUTAWAY, HOLD_QUARANTINE, REJECT_RETURN):
            raise ValidationError({'detail': 'Unsupported exception action'})
        raw_details = request.data.get('details') or []
        details = {detail.goods_code: detail for detail in record.details.select_for_update()}
        if not raw_details:
            raw_details = [{'goods_code': goods_code} for goods_code in details]
        for raw in raw_details:
            goods_code = str(raw.get('goods_code') or '').strip()
            detail = details.get(goods_code)
            if detail is None:
                raise ValidationError({'detail': 'SKU does not belong to the receiving record: %s' % goods_code})
            note = str(raw.get('note') or request.data.get('note') or '').strip()
            if not note:
                raise ValidationError({'detail': 'An exception resolution note is required'})
            detail.resolution_action = action
            detail.resolution_note = note
            if action == ACCEPT_FOR_PUTAWAY:
                accepted_qty = _integer(
                    raw.get('accepted_qty', detail.accepted_qty),
                    'accepted_qty',
                )
                max_accepted = max(int(detail.actual_qty or 0) - int(detail.damage_qty or 0), 0)
                if accepted_qty > max_accepted:
                    raise ValidationError({'detail': 'Accepted quantity exceeds non-damaged quantity'})
                detail.accepted_qty = accepted_qty
                detail.hold_qty = max(int(detail.actual_qty or 0) - int(detail.damage_qty or 0) - accepted_qty, 0)
                detail.rejected_qty = 0
            elif action == HOLD_QUARANTINE:
                detail.accepted_qty = 0
                detail.hold_qty = int(detail.actual_qty or 0)
                detail.rejected_qty = 0
            else:
                detail.accepted_qty = 0
                detail.hold_qty = 0
                detail.rejected_qty = int(detail.actual_qty or 0)
            detail.save()
        open_exceptions = any(_detail_has_open_exception(detail) for detail in details.values())
        has_accepted_qty = any(int(detail.accepted_qty or 0) > 0 for detail in details.values())
        fully_rejected = all(
            int(detail.actual_qty or 0) == 0
            or (
                int(detail.accepted_qty or 0) == 0
                and int(detail.hold_qty or 0) == 0
                and int(detail.rejected_qty or 0) >= int(detail.actual_qty or 0)
            )
            for detail in details.values()
        )
        if open_exceptions:
            record.status = ReceivingRecord.QC_EXCEPTION
        elif action == REJECT_RETURN and fully_rejected:
            record.status = ReceivingRecord.CLOSED
            record.closed_by = _operator_name(request)
            record.closed_at = timezone.now()
        elif has_accepted_qty:
            record.status = ReceivingRecord.PUTAWAY_PENDING
        else:
            record.status = ReceivingRecord.QC_EXCEPTION
        resolution_notes = '; '.join(
            sorted({detail.resolution_note for detail in details.values() if detail.resolution_note})
        )
        record.resolution_action = action
        record.resolution_note = resolution_notes
        record.exception_note = str(request.data.get('note') or '').strip() or resolution_notes
        record.save()
        ReceivingReconciliationEvent.objects.create(
            receipt=record,
            openid=openid,
            event_type='QC_EXCEPTION_RESOLVED',
            operator=_operator_name(request),
            note=record.exception_note,
            payload={'action': action},
        )
        return Response(_record_data(record))


class ReceivingPutawayView(APIView):
    @transaction.atomic
    def post(self, request):
        _ensure_roles(request, 'Manager', 'Supervisor', 'Warehouse', 'Driver')
        openid = _openid(request)
        receipt_no = str(request.data.get('receipt_no') or '').strip()
        goods_code = str(request.data.get('goods_code') or request.data.get('sku') or '').strip()
        bin_name = str(request.data.get('bin_name') or '').strip()
        quantity = _integer(request.data.get('quantity', request.data.get('qty')), 'quantity', minimum=1)
        if not goods_code or not bin_name:
            raise ValidationError({'detail': 'receipt_no, goods_code and bin_name are required'})
        record = ReceivingRecord.objects.select_for_update().filter(openid=openid, receipt_no=receipt_no).first()
        if record is None:
            raise ValidationError({'detail': 'Receiving record does not exist'})
        if record.status not in (ReceivingRecord.PUTAWAY_PENDING, ReceivingRecord.QC_EXCEPTION):
            raise ValidationError({'detail': 'Receiving record is not ready for putaway'})
        detail = ReceivingDetail.objects.select_for_update().filter(
            receipt=record,
            openid=openid,
            goods_code=goods_code,
        ).first()
        if detail is None:
            raise ValidationError({'detail': 'Receiving SKU does not exist'})
        if detail.resolution_action not in ('', ACCEPT_FOR_PUTAWAY):
            raise ValidationError({'detail': 'This SKU is held or rejected and cannot be put away'})
        if detail.exception_note and detail.resolution_action != ACCEPT_FOR_PUTAWAY:
            raise ValidationError({'detail': 'Resolve the QC exception before putaway'})
        remaining = int(detail.accepted_qty or 0) - int(detail.putaway_qty or 0)
        if quantity > remaining:
            raise ValidationError({'detail': 'Putaway quantity exceeds accepted quantity'})
        driver_name = str(request.data.get('driver_name') or request.data.get('driver') or '').strip()
        if not driver_name:
            raise ValidationError({'detail': 'A putaway driver is required'})
        if record.putaway_driver and driver_name != record.putaway_driver:
            raise ValidationError({'detail': 'This receiving record is assigned to putaway driver %s' % record.putaway_driver})
        if not DriverModel.objects.filter(openid=openid, driver_name=driver_name, is_delete=False).exists():
            raise ValidationError({'detail': 'Putaway driver does not exist'})
        identity = getattr(request, 'auth', None)
        if str(getattr(identity, 'staff_type', '') or '').casefold() == 'driver' and driver_name.casefold() != str(getattr(identity, 'staff_name', '') or '').casefold():
            raise ValidationError({'detail': 'A driver can only execute their own putaway task'})
        bin_detail = _validate_storage_bin(openid, bin_name)
        idempotency_key = str(request.data.get('idempotency_key') or '').strip()
        if idempotency_key:
            replay = ReceivingPutaway.objects.filter(openid=openid, idempotency_key=idempotency_key).first()
            if replay:
                return Response(_record_data(record))
        if record.linked_asn_code and not detail.asn_stock_released:
            _apply_linked_asn_inventory(record, detail, int(detail.actual_qty or 0))
        if not record.putaway_driver:
            record.putaway_driver = driver_name
            record.putaway_assigned_by = _operator_name(request)
            record.putaway_assigned_at = timezone.now()
        goods_master = _goods_master(openid, goods_code)
        stock = _stock_for_update(openid, goods_code, goods_master)
        if not record.linked_asn_code:
            stock.goods_qty = int(stock.goods_qty or 0) + quantity
        stock.onhand_stock = int(stock.onhand_stock or 0) + quantity
        stock.can_order_stock = int(stock.can_order_stock or 0) + quantity
        stock.save()
        store_code = Md5.md5('%s:%s:%s' % (record.receipt_no, goods_code, bin_name))
        StockBinModel.objects.create(
            openid=openid,
            bin_name=bin_name,
            goods_code=goods_code,
            goods_desc=goods_master.goods_desc,
            goods_qty=quantity,
            bin_size=bin_detail.bin_size,
            bin_property=bin_detail.bin_property,
            t_code=store_code,
            create_time=detail.create_time,
        )
        QTYRecorder.objects.create(
            openid=openid,
            mode_code=record.receipt_no,
            bin_name=bin_name,
            goods_code=goods_code,
            goods_desc=goods_master.goods_desc,
            goods_qty=quantity,
            store_code=store_code,
            creater=_operator_name(request),
        )
        ReceivingPutaway.objects.create(
            receipt=record,
            detail=detail,
            openid=openid,
            goods_code=goods_code,
            bin_name=bin_name,
            quantity=quantity,
            driver_name=driver_name,
            operator=_operator_name(request),
            idempotency_key=idempotency_key,
        )
        detail.putaway_qty = int(detail.putaway_qty or 0) + quantity
        if not record.linked_asn_code:
            detail.inventory_qty_applied = int(detail.inventory_qty_applied or 0) + quantity
        detail.bin_name = bin_name
        detail.save()
        bin_detail.empty_label = False
        bin_detail.save(update_fields=['empty_label', 'update_time'])
        _refresh_record_after_putaway(record, _operator_name(request))
        record.putaway_by = _operator_name(request)
        record.save()
        ReceivingReconciliationEvent.objects.create(
            receipt=record,
            openid=openid,
            event_type='PUTAWAY_COMPLETED',
            operator=_operator_name(request),
            payload={'goods_code': goods_code, 'quantity': quantity, 'bin_name': bin_name},
        )
        return Response(_record_data(record))


class ReceivingReconcileView(APIView):
    @transaction.atomic
    def post(self, request):
        _ensure_roles(request, 'Manager', 'Supervisor', 'Warehouse', 'Inbound')
        openid = _openid(request)
        receipt_no = str(request.data.get('receipt_no') or '').strip()
        asn_code = str(request.data.get('asn_code') or '').strip()
        if not receipt_no or not asn_code:
            raise ValidationError({'detail': 'receipt_no and asn_code are required'})
        record = ReceivingRecord.objects.select_for_update().filter(openid=openid, receipt_no=receipt_no).first()
        asn = AsnListModel.objects.select_for_update().filter(
            openid=openid,
            asn_code=asn_code,
            is_delete=False,
        ).first()
        if record is None or asn is None:
            raise ValidationError({'detail': 'Receiving record or ASN does not exist'})
        if record.status not in (ReceivingRecord.PUTAWAY_COMPLETE, ReceivingRecord.CLOSED):
            raise ValidationError({'detail': 'Complete QC and putaway before ASN reconciliation'})
        if record.customer and asn.supplier and record.customer.casefold() != asn.supplier.casefold():
            raise ValidationError({'detail': 'Customer does not match the ASN owner'})
        assert_receiving_can_claim_asn(
            openid,
            record.customer,
            [detail.goods_code for detail in record.details.all()],
            asn_code,
            exclude_receipt_no=record.receipt_no,
        )
        if not record.linked_asn_code:
            _release_arrived_asn_reservation(record, asn_code)
        actual = defaultdict(int)
        for detail in record.details.all():
            actual[detail.goods_code] += int(detail.actual_qty or 0)
        expected = defaultdict(int)
        for detail in AsnDetailModel.objects.filter(openid=openid, asn_code=asn_code, is_delete=False):
            expected[detail.goods_code] += int(detail.goods_qty or 0)
        variance = {
            goods_code: {
                'received_qty': actual.get(goods_code, 0),
                'asn_qty': expected.get(goods_code, 0),
            }
            for goods_code in sorted(set(actual) | set(expected))
            if actual.get(goods_code, 0) != expected.get(goods_code, 0)
        }
        record.linked_asn_code = asn_code
        record.reconciliation_status = ReceivingRecord.MATCHED if not variance else ReceivingRecord.EXCEPTION
        record.exception_note = '' if not variance else 'ASN variance requires customer review'
        if not variance and record.status == ReceivingRecord.PUTAWAY_COMPLETE:
            record.status = ReceivingRecord.CLOSED
            record.closed_by = _operator_name(request)
            record.closed_at = timezone.now()
        record.save()
        ReceivingReconciliationEvent.objects.create(
            receipt=record,
            openid=openid,
            event_type='ASN_RECONCILED',
            operator=_operator_name(request),
            note=record.exception_note,
            payload={'asn_code': asn_code, 'variance': variance},
        )
        return Response({'record': _record_data(record), 'variance': variance})


class ReceivingReconcileResolveView(APIView):
    @transaction.atomic
    def post(self, request):
        _ensure_roles(request, 'Manager', 'Supervisor', 'Warehouse', 'Inbound')
        openid = _openid(request)
        receipt_no = str(request.data.get('receipt_no') or '').strip()
        decision = str(request.data.get('decision') or '').strip().upper()
        note = str(request.data.get('note') or '').strip()
        if decision not in (ACCEPT_VARIANCE, RECOUNT_REQUIRED):
            raise ValidationError({'detail': 'Unsupported reconciliation decision'})
        if not note:
            raise ValidationError({'detail': 'A reconciliation note is required'})
        record = ReceivingRecord.objects.select_for_update().filter(openid=openid, receipt_no=receipt_no).first()
        if record is None:
            raise ValidationError({'detail': 'Receiving record does not exist'})
        if record.reconciliation_status not in (ReceivingRecord.EXCEPTION, ReceivingRecord.DISPUTED):
            raise ValidationError({'detail': 'Receiving record has no open reconciliation exception'})
        record.resolution_action = decision
        record.resolution_note = note
        record.exception_note = note
        if decision == ACCEPT_VARIANCE:
            record.reconciliation_status = ReceivingRecord.RESOLVED
            if record.status == ReceivingRecord.PUTAWAY_COMPLETE:
                record.status = ReceivingRecord.CLOSED
                record.closed_by = _operator_name(request)
                record.closed_at = timezone.now()
        else:
            record.reconciliation_status = ReceivingRecord.EXCEPTION
        record.save()
        ReceivingReconciliationEvent.objects.create(
            receipt=record,
            openid=openid,
            event_type='RECONCILIATION_RESOLVED',
            operator=_operator_name(request),
            note=note,
            payload={'decision': decision},
        )
        return Response(_record_data(record))


class ReceivingExceptionListView(APIView):
    def get(self, request):
        openid = _openid(request)
        qs = ReceivingRecord.objects.filter(openid=openid).filter(
            Q(status=ReceivingRecord.QC_EXCEPTION)
            | Q(reconciliation_status=ReceivingRecord.EXCEPTION)
            | Q(reconciliation_status=ReceivingRecord.DISPUTED)
        )
        return Response({
            'count': qs.count(),
            'results': [_record_data(record) for record in qs[:200]],
        })
