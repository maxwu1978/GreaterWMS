from collections import defaultdict
from dateutil.relativedelta import relativedelta
from rest_framework import viewsets
from .models import DnListModel, DnDetailModel, PickingListModel, DnSerialAllocation
from . import serializers
from .page import MyPageNumberPaginationDNList
from utils.page import MyPageNumberPagination
from utils.datasolve import sumOfList, transportation_calculate
from rest_framework.filters import OrderingFilter
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.response import Response
from .filter import DnListFilter, DnDetailFilter, DnPickingListFilter
from rest_framework.exceptions import APIException, PermissionDenied, ValidationError
from customer.models import ListModel as customer
from warehouse.models import ListModel as warehouse
from binset.models import ListModel as binset
from goods.models import ListModel as goods
from goods.units import numeric_value, weight_to_kg
from payment.models import TransportationFeeListModel as transportation
from stock.models import StockListModel as stocklist
from stock.models import StockBinModel as stockbin
from driver.models import ListModel as driverlist
from driver.models import DispatchListModel as driverdispatch
from scanner.models import ListModel as scanner
from cyclecount.models import QTYRecorder as qtychangerecorder
from cyclecount.models import CyclecountModeDayModel as cyclecount
from django.db.models import Q
from django.db.models import Sum
from django.db import IntegrityError, transaction
from utils.md5 import Md5
import re
from .serializers import FileListRenderSerializer, FileDetailRenderSerializer
from django.http import StreamingHttpResponse
from django.utils import timezone
from .files import FileListRenderCN, FileListRenderEN, FileDetailRenderCN, FileDetailRenderEN
from rest_framework.settings import api_settings
from staff.models import ListModel as staff
from staging.models import StagingAssignment
from staging.services import StagingError, occupy_staging_slot, release_staging_slot, reserve_staging_slot
from asnserial.models import AsnSerialRecord
from receiving.models import ReceivingRecord, ReceivingSerial
from transport.models import TransportOrder
from asnserial.agent import complete_preview, consume_preview, consume_web_preview, is_agent_request, request_payload


def _validate_outbound_detail_payload(data):
    """Reject malformed parallel arrays before legacy indexing can raise 500."""
    errors = {}
    for field in ('dn_code', 'customer'):
        if not str(data.get(field) or '').strip():
            errors[field] = ['This field is required.']

    goods_codes = data.get('goods_code')
    goods_qty = data.get('goods_qty')
    if not isinstance(goods_codes, list) or not goods_codes:
        errors['goods_code'] = ['Expected a non-empty list.']
    if not isinstance(goods_qty, list) or not goods_qty:
        errors['goods_qty'] = ['Expected a non-empty list.']
    if isinstance(goods_codes, list) and isinstance(goods_qty, list) and len(goods_codes) != len(goods_qty):
        errors['goods_qty'] = ['Must contain the same number of entries as goods_code.']
    if errors:
        raise ValidationError(errors)

    for index, value in enumerate(goods_qty):
        try:
            int(value)
        except (TypeError, ValueError):
            raise ValidationError({'goods_qty': ['Entry %s must be an integer.' % index]})


def _agent_preview(request, operation, resource_id='', asn_code=''):
    if operation not in {'outbound.create', 'outbound.detail.create'} and not is_agent_request(request):
        return None, None
    return consume_web_preview(
        request,
        operation,
        request_payload(request),
        'header' if operation == 'outbound.create' else 'detail',
        resource_id=str(resource_id or ''),
        asn_code=str(asn_code or ''),
    )


def _requested_serials_for_line(data, index):
    serial_numbers = data.get('serial_numbers')
    if serial_numbers is None:
        serial_numbers = data.get('requested_serials')
    if serial_numbers is None:
        return []
    if not isinstance(serial_numbers, list):
        raise APIException({'detail': 'serial_numbers must be a list of lists'})
    if len(serial_numbers) != len(data.get('goods_code', [])):
        raise APIException({'detail': 'serial_numbers must align with goods_code'})
    values = serial_numbers[index]
    if not isinstance(values, list):
        raise APIException({'detail': 'Each serial_numbers entry must be a list'})
    normalized = [str(value).strip() for value in values if str(value).strip()]
    if len(normalized) != len(set(normalized)):
        raise APIException({'detail': 'Duplicate serial number in outbound request'})
    return normalized


def _validate_outbound_serial_request(
    openid,
    dn,
    goods_codes,
    quantities,
    serial_numbers,
    expected_serials_by_goods=None,
):
    if dn.picking_mode != DnListModel.SN:
        return
    if len(serial_numbers) != len(goods_codes):
        raise APIException({'detail': 'SN picking requires serial_numbers for every SKU'})
    seen = set()
    for goods_code, quantity, values in zip(goods_codes, quantities, serial_numbers):
        if int(quantity) <= 0:
            raise APIException({'detail': 'SN picking quantity must be positive for %s' % goods_code})
        detail = DnDetailModel.objects.filter(
            openid=openid, dn_code=dn.dn_code, goods_code=goods_code, is_delete=False,
        ).first()
        if detail is None and expected_serials_by_goods is None:
            raise APIException({'detail': 'Outbound SKU does not exist: %s' % goods_code})
        expected = set(
            detail.requested_serials if detail is not None
            else expected_serials_by_goods.get(goods_code, [])
        )
        if len(values) != int(quantity):
            raise APIException({'detail': 'SN count must equal quantity for %s' % goods_code})
        if not set(values).issubset(expected):
            raise APIException({'detail': 'SN is not listed on the pick ticket for %s' % goods_code})
        overlap = seen.intersection(values)
        if overlap:
            raise APIException({'detail': 'Duplicate SN in pick request: %s' % sorted(overlap)[0]})
        seen.update(values)
        available_asn = set(AsnSerialRecord.objects.select_for_update().filter(
            openid=openid,
            goods_code=goods_code,
            serial_number__in=values,
            status=AsnSerialRecord.ACCEPTED,
            is_received=True,
        ).values_list('serial_number', flat=True))
        available_receiving = set(ReceivingSerial.objects.select_for_update().filter(
            openid=openid,
            goods_code=goods_code,
            serial_number__in=values,
            status=ReceivingSerial.ACCEPTED,
            receipt__status__in=(ReceivingRecord.PUTAWAY_COMPLETE, ReceivingRecord.CLOSED),
        ).values_list('serial_number', flat=True))
        unavailable = set(values) - available_asn - available_receiving
        if unavailable:
            raise APIException({'detail': 'SN is not available in received inventory: %s' % sorted(unavailable)[0]})
        allocated = set(DnSerialAllocation.objects.select_for_update().filter(
            openid=openid,
            serial_number__in=values,
            status__in=[
                DnSerialAllocation.REQUESTED,
                DnSerialAllocation.PICKED,
                DnSerialAllocation.IN_TRANSIT,
                DnSerialAllocation.SHIPPED,
                DnSerialAllocation.RELEASED,
            ],
        ).exclude(dn_code=dn.dn_code).values_list('serial_number', flat=True))
        if allocated:
            raise APIException({'detail': 'SN is already allocated: %s' % sorted(allocated)[0]})


def _mark_picked_serials(openid, dn, serials_by_goods):
    if dn.picking_mode != DnListModel.SN:
        return
    for goods_code, serials in serials_by_goods.items():
        for serial_number in serials:
            allocation = DnSerialAllocation.objects.select_for_update().filter(
                openid=openid,
                dn_code=dn.dn_code,
                goods_code=goods_code,
                serial_number=serial_number,
                status=DnSerialAllocation.REQUESTED,
            ).first()
            if allocation is None:
                raise APIException({'detail': 'SN is not available for picking: %s' % serial_number})
            allocation.status = DnSerialAllocation.PICKED
            allocation.save(update_fields=['status', 'update_time'])
        detail = DnDetailModel.objects.select_for_update().get(
            openid=openid, dn_code=dn.dn_code, goods_code=goods_code, is_delete=False,
        )
        detail.picked_serials = sorted(set(detail.picked_serials or []).union(serials))
        detail.save(update_fields=['picked_serials', 'update_time'])


def _require_all_picked_serials(openid, dn):
    if dn.picking_mode != DnListModel.SN:
        return
    if DnSerialAllocation.objects.filter(
        openid=openid,
        dn_code=dn.dn_code,
    ).exclude(status=DnSerialAllocation.PICKED).exists():
        raise APIException({'detail': 'All ticket SNs must be picked before dispatch'})


def _mark_serials(openid, dn_code, from_status, to_status):
    allocations = list(DnSerialAllocation.objects.select_for_update().filter(
        openid=openid, dn_code=dn_code, status=from_status,
    ))
    for allocation in allocations:
        allocation.status = to_status
        allocation.save(update_fields=['status', 'update_time'])


def _mark_shipped_serials(openid, dn_code):
    allocations = list(DnSerialAllocation.objects.select_for_update().filter(
        openid=openid,
        dn_code=dn_code,
        status=DnSerialAllocation.IN_TRANSIT,
    ))
    for allocation in allocations:
        allocation.status = DnSerialAllocation.SHIPPED
        allocation.save(update_fields=['status', 'update_time'])
    by_goods = defaultdict(list)
    for allocation in allocations:
        by_goods[allocation.goods_code].append(allocation.serial_number)
    for goods_code, serials in by_goods.items():
        detail = DnDetailModel.objects.filter(
            openid=openid, dn_code=dn_code, goods_code=goods_code, is_delete=False,
        ).first()
        if detail:
            detail.shipped_serials = sorted(set(detail.shipped_serials or []).union(serials))
            detail.save(update_fields=['shipped_serials', 'update_time'])


def _serials_from_pick_payload(goods_data):
    serials_by_goods = defaultdict(list)
    for row in goods_data:
        goods_code = str(row.get('goods_code') or '').strip()
        values = row.get('serial_numbers')
        if values is None:
            values = row.get('serials')
        if values is None:
            values = []
        if not isinstance(values, list):
            raise APIException({'detail': 'Pick serial_numbers must be a list'})
        normalized = [str(value).strip() for value in values if str(value).strip()]
        if len(normalized) != len(set(normalized)):
            raise APIException({'detail': 'Duplicate serial number in pick request'})
        serials_by_goods[goods_code].extend(normalized)
    return serials_by_goods


def _validate_pick_serials(openid, dn, goods_data):
    if dn.picking_mode != DnListModel.SN:
        return {}
    serials_by_goods = _serials_from_pick_payload(goods_data)
    goods_codes = [str(row.get('goods_code') or '').strip() for row in goods_data]
    goods_codes = list(dict.fromkeys(goods_codes))
    if not goods_codes or any(not serials_by_goods.get(code) for code in goods_codes):
        raise APIException({'detail': 'SN picking requires scanned serials for every SKU'})
    quantities = [len(serials_by_goods[code]) for code in goods_codes]
    _validate_outbound_serial_request(
        openid,
        dn,
        goods_codes,
        quantities,
        [serials_by_goods[code] for code in goods_codes],
    )
    return serials_by_goods


def _ensure_outbound_transport(request, dn, driver_name):
    if not dn.transport_required:
        return None
    transport_no = str(request.data.get('transport_order_no') or dn.transport_order_no or '').strip()
    if not transport_no:
        transport_no = 'TR-' + str(dn.dn_code)
    order, _ = TransportOrder.objects.get_or_create(
        openid=dn.openid,
        transport_no=transport_no,
        defaults={
            'direction': TransportOrder.OUTBOUND,
            'reference_type': 'DN',
            'reference_no': dn.dn_code,
            'customer': dn.customer,
            'delivery_location': dn.ship_to,
            'driver_name': driver_name,
            'status': TransportOrder.DRIVER_ASSIGNED,
            'created_by': str(getattr(request.auth, 'staff_name', '') or request.META.get('HTTP_OPERATOR', '')),
        },
    )
    if order.direction != TransportOrder.OUTBOUND or order.reference_no not in ('', dn.dn_code):
        raise APIException({'detail': 'Transport order does not match this delivery note'})
    if order.status == TransportOrder.CANCELLED:
        raise APIException({'detail': 'The linked transport order is cancelled'})
    if order.status not in (
        TransportOrder.REQUESTED,
        TransportOrder.SCHEDULED,
        TransportOrder.DRIVER_ASSIGNED,
    ):
        raise APIException({'detail': 'The linked transport order is not ready for dispatch'})
    if order.driver_name and order.driver_name.casefold() != driver_name.casefold():
        raise APIException({'detail': 'The linked transport order has a different driver'})
    if order.reference_no == '':
        order.reference_type = 'DN'
        order.reference_no = dn.dn_code
        order.customer = dn.customer
        order.delivery_location = dn.ship_to
    order.driver_name = driver_name
    order.status = TransportOrder.DRIVER_ASSIGNED
    order.save(update_fields=[
        'reference_type', 'reference_no', 'customer', 'delivery_location',
        'driver_name', 'status', 'update_time',
    ])
    if dn.transport_order_no != transport_no:
        dn.transport_order_no = transport_no
        dn.save(update_fields=['transport_order_no', 'update_time'])
    return order


def _mark_outbound_transport_in_transit(dn):
    if not dn.transport_order_no:
        return
    order = TransportOrder.objects.select_for_update().filter(
        openid=dn.openid,
        transport_no=dn.transport_order_no,
    ).first()
    if order is None:
        raise APIException({'detail': 'Linked transport order does not exist'})
    if order.status != TransportOrder.DRIVER_ASSIGNED:
        raise APIException({'detail': 'Linked transport order is not assigned to a driver'})
    order.status = TransportOrder.IN_TRANSIT
    order.save(update_fields=['status', 'update_time'])


def _complete_outbound_transport(request, dn):
    if not dn.transport_order_no:
        return
    order = TransportOrder.objects.select_for_update().filter(
        openid=dn.openid,
        transport_no=dn.transport_order_no,
    ).first()
    if order is None:
        raise APIException({'detail': 'Linked transport order does not exist'})
    if order.status == TransportOrder.CANCELLED:
        raise APIException({'detail': 'The linked transport order is cancelled'})
    if order.status == TransportOrder.COMPLETED:
        return
    if order.status not in (
        TransportOrder.DRIVER_ASSIGNED,
        TransportOrder.IN_TRANSIT,
        TransportOrder.ARRIVED,
    ):
        raise APIException({'detail': 'Linked transport order is not ready for POD'})
    pod_reference = str(
        request.data.get('transport_pod_reference')
        or request.data.get('pod_reference')
        or dn.dn_code
    ).strip()
    order.status = TransportOrder.COMPLETED
    order.pod_reference = pod_reference
    order.pod_note = str(request.data.get('transport_pod_note') or '').strip()
    order.completed_by = str(
        getattr(request.auth, 'staff_name', '') or request.META.get('HTTP_OPERATOR', '')
    )
    order.completed_at = timezone.now()
    order.save(update_fields=[
        'status', 'pod_reference', 'pod_note', 'completed_by',
        'completed_at', 'update_time',
    ])


def _cancel_outbound_transport(request, dn, note):
    if not dn.transport_order_no:
        return
    order = TransportOrder.objects.select_for_update().filter(
        openid=dn.openid,
        transport_no=dn.transport_order_no,
    ).first()
    if order is None or order.status in (TransportOrder.COMPLETED, TransportOrder.CANCELLED):
        return
    order.status = TransportOrder.CANCELLED
    order.note = note
    order.save(update_fields=['status', 'note', 'update_time'])

class DnListViewSet(viewsets.ModelViewSet):
    """
        retrieve:
            Response a data list（get）

        list:
            Response a data list（all）

        create:
            Create a data line（post）

        delete:
            Delete a data line（delete)

    """
    pagination_class = MyPageNumberPaginationDNList
    filter_backends = [DjangoFilterBackend, OrderingFilter, ]
    ordering_fields = ['id', "create_time", "update_time", ]
    filter_class = DnListFilter

    def get_project(self):
        try:
            id = self.kwargs.get('pk')
            return id
        except:
            return None

    def get_queryset(self):
        id = self.get_project()
        if self.request.user:
            empty_qs = DnListModel.objects.filter(
                Q(openid=self.request.auth.openid, dn_status=1, is_delete=False) & Q(customer=''))
            cur_date = timezone.now()
            date_check = relativedelta(day=1)
            if len(empty_qs) > 0:
                for i in range(len(empty_qs)):
                    if empty_qs[i].create_time <= cur_date - date_check:
                        empty_qs[i].delete()
            if id is None:
                return DnListModel.objects.filter(
                    Q(openid=self.request.auth.openid, is_delete=False) & ~Q(customer=''))
            else:
                return DnListModel.objects.filter(
                    Q(openid=self.request.auth.openid, id=id, is_delete=False) & ~Q(customer=''))
        else:
            return DnListModel.objects.none()

    def get_serializer_class(self):
        if self.action in ['list', 'retrieve', 'destroy']:
            return serializers.DNListGetSerializer
        elif self.action in ['create']:
            return serializers.DNListPostSerializer
        elif self.action in ['update']:
            return serializers.DNListUpdateSerializer
        elif self.action in ['partial_update']:
            return serializers.DNListPartialUpdateSerializer
        else:
            return self.http_method_not_allowed(request=self.request)

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        data = self.request.data.copy()
        command, replay = _agent_preview(request, 'outbound.create')
        if replay is not None:
            return Response(replay)
        picking_mode = str(data.get('picking_mode') or DnListModel.SKU_QTY).strip().upper()
        if picking_mode not in dict(DnListModel.PICKING_MODE_CHOICES):
            raise APIException({'detail': 'Unsupported picking_mode'})
        data['picking_mode'] = picking_mode
        data['openid'] = self.request.auth.openid
        custom_dn = self.request.GET.get('custom_dn', '')
        if custom_dn:
            data['dn_code'] = custom_dn
        else:
            qs_set = DnListModel.objects.filter(openid=self.request.auth.openid)
            order_day = str(timezone.now().strftime('%Y%m%d'))
            if len(qs_set) > 0:
                dn_last_code = qs_set.order_by('-id').first().dn_code
                if dn_last_code[2:10] == order_day:
                    order_create_no = str(int(dn_last_code[10:]) + 1)
                    data['dn_code'] = 'DN' + order_day + order_create_no
                else:
                    data['dn_code'] = 'DN' + order_day + '1'
            else:
                data['dn_code'] = 'DN' + order_day + '1'
        data['bar_code'] = Md5.md5(str(data['dn_code']))
        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        scanner.objects.create(openid=self.request.auth.openid, mode="DN", code=data['dn_code'],
                               bar_code=data['bar_code'])
        result = serializer.data
        complete_preview(command, result)
        headers = self.get_success_headers(serializer.data)
        return Response(result, status=200, headers=headers)

    def destroy(self, request, pk):
        qs = self.get_object()
        if qs.openid != self.request.auth.openid:
            raise APIException({"detail": "Cannot delete data which not yours"})
        else:
            if qs.dn_status == 1:
                qs.is_delete = True
                dn_detail_list = DnDetailModel.objects.filter(openid=self.request.auth.openid, dn_code=qs.dn_code,
                                              dn_status=1, is_delete=False)
                for i in range(len(dn_detail_list)):
                    goods_qty_change = stocklist.objects.filter(openid=self.request.auth.openid,
                                                                goods_code=str(dn_detail_list[i].goods_code)).first()
                    goods_qty_change.dn_stock = goods_qty_change.dn_stock - int(dn_detail_list[i].goods_qty)
                    goods_qty_change.save()
                dn_detail_list.update(is_delete=True)
                qs.save()
                return Response({"detail": "success"}, status=200)
            else:
                raise APIException({"detail": "This order has Confirmed or Deliveried"})

class DnDetailViewSet(viewsets.ModelViewSet):
    """
        retrieve:
            Response a data list（get）

        list:
            Response a data list（all）

        create:
            Create a data line（post）

        update:
            Update a data（put：update）
    """
    pagination_class = MyPageNumberPagination
    filter_backends = [DjangoFilterBackend, OrderingFilter, ]
    ordering_fields = ['id', "create_time", "update_time", ]
    filter_class = DnDetailFilter

    def get_project(self):
        try:
            id = self.kwargs.get('pk')
            return id
        except:
            return None

    def get_queryset(self):
        id = self.get_project()
        if self.request.user:
            if id is None:
                return DnDetailModel.objects.filter(openid=self.request.auth.openid, is_delete=False)
            else:
                return DnDetailModel.objects.filter(openid=self.request.auth.openid, id=id, is_delete=False)
        else:
            return DnDetailModel.objects.none()

    def get_serializer_class(self):
        if self.action in ['list', 'retrieve', 'destroy']:
            return serializers.DNDetailGetSerializer
        elif self.action in ['create']:
            return serializers.DNDetailPostSerializer
        elif self.action in ['update']:
            return serializers.DNDetailUpdateSerializer
        else:
            return self.http_method_not_allowed(request=self.request)

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        data = self.request.data
        _validate_outbound_detail_payload(data)
        command, replay = _agent_preview(
            request,
            'outbound.detail.create',
            resource_id=data.get('dn_code'),
        )
        if replay is not None:
            return Response(replay)
        if DnListModel.objects.filter(openid=self.request.auth.openid, dn_code=str(data['dn_code']), is_delete=False).exists():
            if customer.objects.filter(openid=self.request.auth.openid, customer_name=str(data['customer']), is_delete=False).exists():
                dn = DnListModel.objects.select_for_update().get(
                    openid=self.request.auth.openid,
                    dn_code=str(data['dn_code']),
                    is_delete=False,
                )
                serial_numbers = [
                    _requested_serials_for_line(data, index)
                    for index in range(len(data['goods_code']))
                ]
                goods_codes = [str(value) for value in data['goods_code']]
                quantities = [int(value) for value in data['goods_qty']]
                if dn.picking_mode == DnListModel.SN and len(goods_codes) != len(set(goods_codes)):
                    raise APIException({'detail': 'SN picking requires one line per SKU'})
                _validate_outbound_serial_request(
                    self.request.auth.openid,
                    dn,
                    goods_codes,
                    quantities,
                    serial_numbers,
                    expected_serials_by_goods={
                        goods_code: values
                        for goods_code, values in zip(goods_codes, serial_numbers)
                    },
                )
                staff_name = staff.objects.filter(openid=self.request.auth.openid,
                                                  id=self.request.META.get('HTTP_OPERATOR')).first().staff_name
                for i in range(len(data['goods_code'])):
                    if goods.objects.filter(openid=self.request.auth.openid,
                                            goods_code=str(data['goods_code'][i]),
                                            is_delete=False).exists():
                        check_data = {
                            'openid': self.request.auth.openid,
                            'dn_code': str(data['dn_code']),
                            'customer': str(data['customer']),
                            'goods_code': str(data['goods_code'][i]),
                            'goods_qty': int(data['goods_qty'][i]),
                            'creater': str(staff_name)
                        }
                        serializer = self.get_serializer(data=check_data)
                        serializer.is_valid(raise_exception=True)
                    else:
                        raise APIException({"detail": str(data['goods_code'][i]) + " does not exists"})
                post_data_list = []
                weight_list = []
                volume_list = []
                cost_list = []
                for j in range(len(data['goods_code'])):
                    goods_detail = goods.objects.filter(openid=self.request.auth.openid,
                                                        goods_code=str(data['goods_code'][j]),
                                                        is_delete=False).first()
                    goods_weight = round(weight_to_kg(goods_detail) * int(data['goods_qty'][j]), 4)
                    goods_volume = round(goods_detail.unit_volume * int(data['goods_qty'][j]), 4)
                    goods_cost = round(numeric_value(goods_detail.goods_price) * int(data['goods_qty'][j]), 2)
                    if stocklist.objects.filter(openid=self.request.auth.openid, goods_code=str(data['goods_code'][j]),
                                                can_order_stock__gte=0).exists():
                        goods_qty_change = stocklist.objects.filter(openid=self.request.auth.openid,
                                                                    goods_code=str(data['goods_code'][j])).first()
                        goods_qty_change.dn_stock = goods_qty_change.dn_stock + int(data['goods_qty'][j])
                        goods_qty_change.save()
                    else:
                        stocklist.objects.create(openid=self.request.auth.openid,
                                                 goods_code=str(data['goods_code'][j]),
                                                 goods_desc=goods_detail.goods_desc,
                                                 dn_stock=int(data['goods_qty'][j]))
                    post_data = DnDetailModel(openid=self.request.auth.openid,
                                              dn_code=str(data['dn_code']),
                                              customer=str(data['customer']),
                                              goods_code=str(data['goods_code'][j]),
                                              goods_desc=str(goods_detail.goods_desc),
                                              goods_qty=int(data['goods_qty'][j]),
                                              goods_weight=goods_weight,
                                              goods_volume=goods_volume,
                                              goods_cost=goods_cost,
                                              requested_serials=serial_numbers[j],
                                              creater=str(staff_name))
                    weight_list.append(goods_weight)
                    volume_list.append(goods_volume)
                    cost_list.append(goods_cost)
                    post_data_list.append(post_data)
                total_weight = sumOfList(weight_list, len(weight_list))
                total_volume = sumOfList(volume_list, len(volume_list))
                total_cost = sumOfList(cost_list, len(cost_list))
                customer_city = customer.objects.filter(openid=self.request.auth.openid,
                                                        customer_name=str(data['customer']),
                                                        is_delete=False).first().customer_city
                warehouse_city = warehouse.objects.filter(openid=self.request.auth.openid).first().warehouse_city
                transportation_fee = transportation.objects.filter(
                    Q(openid=self.request.auth.openid, send_city__icontains=warehouse_city, receiver_city__icontains=customer_city,
                      is_delete=False) | Q(openid='init_data', send_city__icontains=warehouse_city, receiver_city__icontains=customer_city,
                                           is_delete=False))
                transportation_res = {
                    "detail": []
                }
                if len(transportation_fee) >= 1:
                    transportation_list = []
                    for k in range(len(transportation_fee)):
                        transportation_cost = transportation_calculate(total_weight,
                                                                       total_volume,
                                                                       transportation_fee[k].weight_fee,
                                                                       transportation_fee[k].volume_fee,
                                                                       transportation_fee[k].min_payment)
                        transportation_detail = {
                            "transportation_supplier": transportation_fee[k].transportation_supplier,
                            "transportation_cost": transportation_cost
                        }
                        transportation_list.append(transportation_detail)
                    transportation_res['detail'] = transportation_list
                DnDetailModel.objects.bulk_create(post_data_list, batch_size=100)
                if dn.picking_mode == DnListModel.SN:
                    try:
                        with transaction.atomic():
                            DnSerialAllocation.objects.bulk_create([
                                DnSerialAllocation(
                                    openid=self.request.auth.openid,
                                    dn_code=dn.dn_code,
                                    goods_code=post_data.goods_code,
                                    serial_number=serial_number,
                                    created_by=staff_name,
                                )
                                for post_data in post_data_list
                                for serial_number in post_data.requested_serials
                            ])
                    except IntegrityError:
                        raise APIException({'detail': 'One or more serial numbers are already allocated'})
                check_data = DnDetailModel.objects.filter(openid=self.request.auth.openid, dn_code=data['dn_code'], is_delete=False)
                for k in range(len(check_data)):
                    res_check_data = check_data.filter(goods_code=check_data[k].goods_code)
                    if res_check_data.count() > 1:
                        combine_qty = []
                        conbine_weight = []
                        conbine_volume = []
                        conbine_cost = []
                        for z in range(len(res_check_data)):
                            combine_qty.append(res_check_data[z].goods_qty)
                            conbine_weight.append(res_check_data[z].goods_weight)
                            conbine_volume.append(res_check_data[z].goods_volume)
                            conbine_cost.append(res_check_data[z].goods_cost)
                            res_check_data[z].delete()
                        DnDetailModel.objects.create(openid=self.request.auth.openid,
                                                     dn_code=str(data['dn_code']),
                                                     customer=str(data['customer']),
                                                     goods_code=str(check_data[k].goods_code),
                                                     goods_desc=str(check_data[k].goods_desc),
                                                     goods_qty=sumOfList(combine_qty, len(combine_qty)),
                                                     goods_weight=sumOfList(conbine_weight, len(conbine_weight)),
                                                     goods_volume=sumOfList(conbine_volume, len(conbine_volume)),
                                                     goods_cost=sumOfList(conbine_cost, len(conbine_cost)),
                                                     creater=str(staff_name))
                DnListModel.objects.filter(openid=self.request.auth.openid, dn_code=str(data['dn_code'])).update(
                    customer=str(data['customer']), total_weight=total_weight, total_volume=total_volume,
                    total_cost=total_cost, transportation_fee=transportation_res)
                result = {"detail": "success"}
                complete_preview(command, result)
                return Response(result, status=200)
            else:
                raise APIException({"detail": "customer does not exists"})
        else:
            raise APIException({"detail": "DN Code does not exists"})

    def update(self, request, *args, **kwargs):
        data = self.request.data
        _validate_outbound_detail_payload(data)
        if DnListModel.objects.filter(openid=self.request.auth.openid, dn_code=str(data['dn_code']),
                                       dn_status=1, is_delete=False).exists():
            if customer.objects.filter(openid=self.request.auth.openid, customer_name=str(data['customer']),
                                       is_delete=False).exists():
                staff_name = staff.objects.filter(openid=self.request.auth.openid,
                                                  id=self.request.META.get('HTTP_OPERATOR')).first().staff_name
                for i in range(len(data['goods_code'])):
                    check_data = {
                        'openid': self.request.auth.openid,
                        'dn_code': str(data['dn_code']),
                        'customer': str(data['customer']),
                        'goods_code': str(data['goods_code'][i]),
                        'goods_qty': int(data['goods_qty'][i]),
                        'creater': str(staff_name)
                    }
                    serializer = self.get_serializer(data=check_data)
                    serializer.is_valid(raise_exception=True)
                dn_detail_list = DnDetailModel.objects.filter(openid=self.request.auth.openid,
                                              dn_code=str(data['dn_code']), is_delete=False)
                for v in range(len(dn_detail_list)):
                    goods_qty_change = stocklist.objects.filter(openid=self.request.auth.openid,
                                                                goods_code=str(dn_detail_list[v].goods_code)).first()
                    goods_qty_change.dn_stock = goods_qty_change.dn_stock - dn_detail_list[v].goods_qty
                    if goods_qty_change.dn_stock < 0:
                        goods_qty_change.dn_stock = 0
                    goods_qty_change.save()
                    dn_detail_list[v].is_delete = True
                    dn_detail_list[v].save()
                post_data_list = []
                weight_list = []
                volume_list = []
                cost_list = []
                for j in range(len(data['goods_code'])):
                    goods_detail = goods.objects.filter(openid=self.request.auth.openid,
                                                        goods_code=str(data['goods_code'][j]),
                                                        is_delete=False).first()
                    goods_weight = round(weight_to_kg(goods_detail) * int(data['goods_qty'][j]), 4)
                    goods_volume = round(goods_detail.unit_volume * int(data['goods_qty'][j]), 4)
                    goods_cost = round(numeric_value(goods_detail.goods_price) * int(data['goods_qty'][j]), 2)
                    if stocklist.objects.filter(openid=self.request.auth.openid, goods_code=str(data['goods_code'][j]),
                                                can_order_stock__gte=0).exists():
                        goods_qty_change = stocklist.objects.filter(openid=self.request.auth.openid,
                                                                    goods_code=str(data['goods_code'][j])).first()
                        goods_qty_change.dn_stock = goods_qty_change.dn_stock + int(data['goods_qty'][j])
                        goods_qty_change.save()
                    else:
                        stocklist.objects.create(openid=self.request.auth.openid,
                                                 goods_code=str(data['goods_code'][j]),
                                                 goods_desc=goods_detail.goods_desc,
                                                 dn_stock=int(data['goods_qty'][j]))
                    post_data = DnDetailModel(openid=self.request.auth.openid,
                                              dn_code=str(data['dn_code']),
                                              customer=str(data['customer']),
                                              goods_code=str(data['goods_code'][j]),
                                              goods_desc=str(goods_detail.goods_desc),
                                              goods_qty=int(data['goods_qty'][j]),
                                              goods_weight=goods_weight,
                                              goods_volume=goods_volume,
                                              goods_cost=goods_cost,
                                              creater=str(staff_name))
                    weight_list.append(goods_weight)
                    volume_list.append(goods_volume)
                    cost_list.append(goods_cost)
                    post_data_list.append(post_data)
                total_weight = sumOfList(weight_list, len(weight_list))
                total_volume = sumOfList(volume_list, len(volume_list))
                total_cost = sumOfList(cost_list, len(cost_list))
                customer_city = customer.objects.filter(openid=self.request.auth.openid,
                                                        customer_name=str(data['customer']),
                                                        is_delete=False).first().customer_city
                warehouse_city = warehouse.objects.filter(openid=self.request.auth.openid).first().warehouse_city
                transportation_fee = transportation.objects.filter(
                    Q(openid=self.request.auth.openid, send_city__icontains=warehouse_city,
                      receiver_city__icontains=customer_city,
                      is_delete=False) | Q(openid='init_data', send_city__icontains=warehouse_city,
                                           receiver_city__icontains=customer_city,
                                           is_delete=False))
                transportation_res = {
                    "detail": []
                }
                if len(transportation_fee) >= 1:
                    transportation_list = []
                    for k in range(len(transportation_fee)):
                        transportation_cost = transportation_calculate(total_weight,
                                                                       total_volume,
                                                                       transportation_fee[k].weight_fee,
                                                                       transportation_fee[k].volume_fee,
                                                                       transportation_fee[k].min_payment)
                        transportation_detail = {
                            "transportation_supplier": transportation_fee[k].transportation_supplier,
                            "transportation_cost": transportation_cost
                        }
                        transportation_list.append(transportation_detail)
                    transportation_res['detail'] = transportation_list
                DnDetailModel.objects.bulk_create(post_data_list, batch_size=100)
                check_data = DnDetailModel.objects.filter(openid=self.request.auth.openid, dn_code=data['dn_code'], is_delete=False)
                for k in range(len(check_data)):
                    res_check_data = check_data.filter(goods_code=check_data[k].goods_code)
                    if res_check_data.count() > 1:
                        combine_qty = []
                        conbine_weight = []
                        conbine_volume = []
                        conbine_cost = []
                        for z in range(len(res_check_data)):
                            combine_qty.append(res_check_data[z].goods_qty)
                            conbine_weight.append(res_check_data[z].goods_weight)
                            conbine_volume.append(res_check_data[z].goods_volume)
                            conbine_cost.append(res_check_data[z].goods_cost)
                            res_check_data[z].delete()
                        DnDetailModel.objects.create(openid=self.request.auth.openid,
                                                     dn_code=str(data['dn_code']),
                                                     customer=str(data['customer']),
                                                     goods_code=str(check_data[k].goods_code),
                                                     goods_desc=str(check_data[k].goods_desc),
                                                     goods_qty=sumOfList(combine_qty, len(combine_qty)),
                                                     goods_weight=sumOfList(conbine_weight, len(conbine_weight)),
                                                     goods_volume=sumOfList(conbine_volume, len(conbine_volume)),
                                                     goods_cost=sumOfList(conbine_cost, len(conbine_cost)),
                                                     creater=str(staff_name))
                DnListModel.objects.filter(openid=self.request.auth.openid, dn_code=str(data['dn_code'])).update(
                    customer=str(data['customer']), total_weight=total_weight, total_volume=total_volume,
                    total_cost=total_cost, transportation_fee=transportation_res)
                return Response({"detail": "success"}, status=200)
            else:
                raise APIException({"detail": "Customer does not exists"})
        else:
            raise APIException({"detail": "DN Code has been Confirmed or does not exists"})

    def destroy(self, request, pk):
        qs = self.get_object()
        if qs.openid != self.request.auth.openid:
            raise APIException({"detail": "Cannot delete data which not yours"})
        else:
            if qs.dn_status == 2 and qs.back_order_label:
                qs.is_delete = True
                goods_qty_change = stocklist.objects.filter(openid=self.request.auth.openid,
                                                            goods_code=str(qs.goods_code)).first()
                goods_qty_change.back_order_stock = goods_qty_change.back_order_stock - int(qs.goods_qty)
                goods_qty_change.ordered_stock = goods_qty_change.ordered_stock - int(qs.goods_qty)
                goods_qty_change.save()
                qs.save()
                dn_detail_check = DnDetailModel.objects.filter(openid=self.request.auth.openid, dn_code=qs.dn_code, is_delete=False).count()
                if dn_detail_check == 0:
                    dn_list = DnListModel.objects.filter(openid=self.request.auth.openid, dn_code=qs.dn_code, is_delete=False)
                    if dn_list.exists():
                        dn_list.update(is_delete=True)
                return Response({"detail": "success"}, status=200)
            else:
                raise APIException({"detail": "This order has Confirmed or Deliveried"})


class DnViewPrintViewSet(viewsets.ModelViewSet):
    """
        retrieve:
            Response a data list（get）
    """
    serializer_class = serializers.DNListGetSerializer
    pagination_class = MyPageNumberPagination
    filter_backends = [DjangoFilterBackend, OrderingFilter, ]
    ordering_fields = ['id', "create_time", "update_time", ]
    filter_class = DnListFilter

    def get_project(self):
        try:
            id = self.kwargs.get('pk')
            return id
        except:
            return None

    def get_queryset(self):
        id = self.get_project()
        if self.request.user:
            if id is None:
                return DnListModel.objects.filter(openid=self.request.auth.openid, is_delete=False)
            else:
                return DnListModel.objects.filter(openid=self.request.auth.openid, id=id, is_delete=False)
        else:
            return DnListModel.objects.none()

    def get_serializer_class(self):
        if self.action in ['retrieve']:
            return serializers.DNDetailGetSerializer
        else:
            return self.http_method_not_allowed(request=self.request)

    def retrieve(self, request, pk):
        qs = self.get_object()
        if qs.openid != self.request.auth.openid:
            raise APIException({"detail": "Cannot update data which not yours"})
        else:
            context = {}
            dn_detail_list = DnDetailModel.objects.filter(openid=self.request.auth.openid,
                                                          dn_code=qs.dn_code,
                                                          is_delete=False)
            dn_detail = serializers.DNDetailGetSerializer(dn_detail_list, many=True)
            customer_detail = customer.objects.filter(openid=self.request.auth.openid,
                                                            customer_name=qs.customer).first()
            warehouse_detail = warehouse.objects.filter(openid=self.request.auth.openid).first()
            context['dn_detail'] = dn_detail.data
            context['customer_detail'] = {
                "customer_name": customer_detail.customer_name,
                "customer_city": customer_detail.customer_city,
                "customer_address": customer_detail.customer_address,
                "customer_contact": customer_detail.customer_contact
            }
            context['warehouse_detail'] = {
                "warehouse_name": warehouse_detail.warehouse_name,
                "warehouse_city": warehouse_detail.warehouse_city,
                "warehouse_address": warehouse_detail.warehouse_address,
                "warehouse_contact": warehouse_detail.warehouse_contact
            }
        return Response(context, status=200)


class DnNewOrderViewSet(viewsets.ModelViewSet):
    """
        retrieve:
            Response a data list（get）
    """
    pagination_class = MyPageNumberPagination
    filter_backends = [DjangoFilterBackend, OrderingFilter, ]
    ordering_fields = ['id', "create_time", "update_time", ]
    filter_class = DnListFilter

    def get_project(self):
        try:
            id = self.kwargs.get('pk')
            return id
        except:
            return None

    def get_queryset(self):
        id = self.get_project()
        if self.request.user:
            if id is None:
                return DnListModel.objects.filter(openid=self.request.auth.openid, is_delete=False)
            else:
                return DnListModel.objects.filter(openid=self.request.auth.openid, id=id, is_delete=False)
        else:
            return DnListModel.objects.none()

    def get_serializer_class(self):
        if self.action in ['create']:
            return serializers.DNListPartialUpdateSerializer
        else:
            return self.http_method_not_allowed(request=self.request)

    @transaction.atomic
    def create(self, request, pk):
        qs = self.get_object()
        if qs.openid != self.request.auth.openid:
            raise APIException({"detail": "Cannot delete data which not yours"})
        else:
            if qs.dn_status == 1:
                dn_detail_list = DnDetailModel.objects.filter(openid=self.request.auth.openid, dn_code=qs.dn_code,
                                                              dn_status=1, is_delete=False)
                if dn_detail_list.exists():
                    command, replay = _agent_preview(request, 'outbound.release', resource_id=pk)
                    if replay is not None:
                        return Response(replay)
                    qs.dn_status = 2
                    for i in range(len(dn_detail_list)):
                        if stocklist.objects.filter(openid=self.request.auth.openid,
                                                    goods_code=str(dn_detail_list[i].goods_code)).exists():
                            pass
                        else:
                            goods_detail = goods.objects.filter(openid=self.request.auth.openid, goods_code=str(dn_detail_list[i].goods_code)).first()
                            stocklist.objects.create(openid=self.request.auth.openid,
                                                     goods_code=str(dn_detail_list[i].goods_code),
                                                     goods_desc=goods_detail.goods_desc,
                                                     supplier=goods_detail.goods_supplier)
                        goods_qty_change = stocklist.objects.filter(openid=self.request.auth.openid,
                                                                    goods_code=str(
                                                                        dn_detail_list[i].goods_code)).first()
                        goods_qty_change.can_order_stock = goods_qty_change.can_order_stock - dn_detail_list[i].goods_qty
                        goods_qty_change.ordered_stock = goods_qty_change.ordered_stock + dn_detail_list[i].goods_qty
                        goods_qty_change.dn_stock = goods_qty_change.dn_stock - dn_detail_list[i].goods_qty
                        if goods_qty_change.can_order_stock < 0:
                            goods_qty_change.can_order_stock = 0
                        goods_qty_change.save()
                    dn_detail_list.update(dn_status=2)
                    qs.save()
                    serializer = self.get_serializer(qs, many=False)
                    headers = self.get_success_headers(serializer.data)
                    result = serializer.data
                    complete_preview(command, result)
                    return Response(result, status=200, headers=headers)
                else:
                    raise APIException({"detail": "Please Enter The DN Detail"})
            else:
                raise APIException({"detail": "This DN Status Is Not Pre Order"})

class DnOrderReleaseViewSet(viewsets.ModelViewSet):
    """
        retrieve:
            Response a data list（get）
    """
    pagination_class = MyPageNumberPagination
    filter_backends = [DjangoFilterBackend, OrderingFilter, ]
    ordering_fields = ['id', "create_time", "update_time", ]
    filter_class = DnListFilter

    def get_project(self):
        try:
            id = self.kwargs.get('pk')
            return id
        except:
            return None

    def get_queryset(self):
        id = self.get_project()
        if self.request.user:
            if id is None:
                return DnListModel.objects.filter(openid=self.request.auth.openid, dn_status=2, is_delete=False).order_by('create_time')
            else:
                return DnListModel.objects.filter(openid=self.request.auth.openid, dn_status=2, id=id, is_delete=False)
        else:
            return DnListModel.objects.none()

    def get_serializer_class(self):
        if self.action in ['create', 'update']:
            return serializers.DNListUpdateSerializer
        else:
            return self.http_method_not_allowed(request=self.request)

    def create(self, request, *args, **kwargs):
        qs = self.get_queryset()
        staff_name = staff.objects.filter(openid=self.request.auth.openid,
                                          id=self.request.META.get('HTTP_OPERATOR')).first().staff_name
        for v in range(len(qs)):
            dn_detail_list = DnDetailModel.objects.filter(openid=self.request.auth.openid, dn_code=qs[v].dn_code,
                                                          dn_status=2, is_delete=False)
            picking_list = []
            picking_list_label = 0
            back_order_list = []
            back_order_list_label = 0
            back_order_goods_weight_list = []
            back_order_goods_volume_list = []
            back_order_goods_cost_list = []
            back_order_base_code = DnListModel.objects.filter(openid=self.request.auth.openid,
                                                              is_delete=False).order_by('-id').first().dn_code
            dn_last_code = re.findall(r'\d+', str(back_order_base_code), re.IGNORECASE)
            back_order_dn_code = 'DN' + str(int(dn_last_code[0]) + 1).zfill(8)
            bar_code = Md5.md5(back_order_dn_code)
            total_weight = qs[v].total_weight
            total_volume = qs[v].total_volume
            total_cost = qs[v].total_cost
            for i in range(len(dn_detail_list)):
                goods_detail = goods.objects.filter(openid=self.request.auth.openid,
                                                    goods_code=str(dn_detail_list[i].goods_code),
                                                    is_delete=False).first()
                if stocklist.objects.filter(openid=self.request.auth.openid,
                                            goods_code=str(dn_detail_list[i].goods_code)).exists() is False:
                    stocklist.objects.create(openid=self.request.auth.openid,
                                             goods_code=str(goods_detail.goods_code),
                                             goods_desc=goods_detail.goods_desc,
                                             dn_stock=int(dn_detail_list[i].goods_qty))
                goods_qty_change = stocklist.objects.filter(openid=self.request.auth.openid,
                                                            goods_code=str(
                                                                dn_detail_list[i].goods_code)).first()
                goods_bin_stock_list = stockbin.objects.filter(openid=self.request.auth.openid,
                                                               goods_code=str(dn_detail_list[i].goods_code),
                                                               bin_property="Normal", goods_qty__gt=0).order_by('id')
                can_pick_qty = goods_qty_change.onhand_stock - \
                               goods_qty_change.inspect_stock - \
                               goods_qty_change.hold_stock - \
                               goods_qty_change.damage_stock - \
                               goods_qty_change.pick_stock
                if can_pick_qty > 0:
                    if dn_detail_list[i].goods_qty > can_pick_qty:
                        if qs[v].back_order_label is False:
                            dn_pick_qty = dn_detail_list[i].pick_qty
                            for j in range(len(goods_bin_stock_list)):
                                bin_can_pick_qty = goods_bin_stock_list[j].goods_qty - \
                                                   goods_bin_stock_list[j].pick_qty
                                if bin_can_pick_qty > 0:
                                    goods_bin_stock_list[j].pick_qty = goods_bin_stock_list[
                                                                           j].pick_qty + bin_can_pick_qty
                                    goods_qty_change.ordered_stock = goods_qty_change.ordered_stock - bin_can_pick_qty
                                    goods_qty_change.pick_stock = goods_qty_change.pick_stock + bin_can_pick_qty
                                    picking_list.append(PickingListModel(openid=self.request.auth.openid,
                                                                         dn_code=dn_detail_list[i].dn_code,
                                                                         bin_name=goods_bin_stock_list[j].bin_name,
                                                                         goods_code=goods_bin_stock_list[
                                                                             j].goods_code,
                                                                         pick_qty=bin_can_pick_qty,
                                                                         creater=str(staff_name),
                                                                         t_code=goods_bin_stock_list[j].t_code))
                                    picking_list_label = 1
                                    dn_pick_qty = dn_pick_qty + bin_can_pick_qty
                                    goods_qty_change.save()
                                    goods_bin_stock_list[j].save()
                                elif bin_can_pick_qty == 0:
                                    continue
                                else:
                                    continue
                            dn_detail_list[i].pick_qty = dn_pick_qty
                            dn_back_order_qty = dn_detail_list[i].goods_qty - \
                                                dn_detail_list[i].pick_qty
                            goods_qty_change.back_order_stock = dn_detail_list[i].goods_qty - can_pick_qty
                            dn_detail_list[i].goods_qty = dn_pick_qty
                            dn_detail_list[i].dn_status = 3
                            back_order_goods_volume = round(goods_detail.unit_volume * dn_back_order_qty, 4)
                            back_order_goods_weight = round(
                                weight_to_kg(goods_detail) * dn_back_order_qty, 4)
                            back_order_goods_cost = round(numeric_value(goods_detail.goods_price) * dn_back_order_qty, 2)
                            back_order_list.append(DnDetailModel(dn_code=back_order_dn_code,
                                                                 dn_status=2,
                                                                 customer=qs[v].customer,
                                                                 goods_code=dn_detail_list[i].goods_code,
                                                                 goods_desc=dn_detail_list[i].goods_desc,
                                                                 goods_qty=dn_back_order_qty,
                                                                 goods_weight=back_order_goods_weight,
                                                                 goods_volume=back_order_goods_volume,
                                                                 goods_cost=back_order_goods_cost,
                                                                 creater=str(staff_name),
                                                                 back_order_label=True,
                                                                 openid=self.request.auth.openid,
                                                                 create_time=dn_detail_list[i].create_time))
                            back_order_list_label = 1
                            total_weight = total_weight - back_order_goods_weight
                            total_volume = total_volume - back_order_goods_volume
                            total_cost = total_cost - back_order_goods_cost
                            dn_detail_list[i].goods_weight = dn_detail_list[i].goods_weight - \
                                                             back_order_goods_weight
                            dn_detail_list[i].goods_volume = dn_detail_list[i].goods_volume - \
                                                             back_order_goods_volume
                            dn_detail_list[i].goods_cost = dn_detail_list[i].goods_cost - \
                                                           back_order_goods_cost
                            back_order_goods_weight_list.append(back_order_goods_weight)
                            back_order_goods_volume_list.append(back_order_goods_volume)
                            back_order_goods_cost_list.append(back_order_goods_cost)
                            goods_qty_change.save()
                            dn_detail_list[i].save()
                        else:
                            dn_pick_qty = dn_detail_list[i].pick_qty
                            for j in range(len(goods_bin_stock_list)):
                                bin_can_pick_qty = goods_bin_stock_list[j].goods_qty - \
                                                   goods_bin_stock_list[j].pick_qty
                                if bin_can_pick_qty > 0:
                                    goods_bin_stock_list[j].pick_qty = goods_bin_stock_list[
                                                                           j].pick_qty + bin_can_pick_qty
                                    goods_qty_change.ordered_stock = goods_qty_change.ordered_stock - bin_can_pick_qty
                                    goods_qty_change.can_order_stock = goods_qty_change.can_order_stock - bin_can_pick_qty
                                    goods_qty_change.back_order_stock = goods_qty_change.back_order_stock - bin_can_pick_qty
                                    goods_qty_change.pick_stock = goods_qty_change.pick_stock + bin_can_pick_qty
                                    picking_list.append(PickingListModel(openid=self.request.auth.openid,
                                                                         dn_code=dn_detail_list[i].dn_code,
                                                                         bin_name=goods_bin_stock_list[j].bin_name,
                                                                         goods_code=goods_bin_stock_list[
                                                                             j].goods_code,
                                                                         pick_qty=bin_can_pick_qty,
                                                                         creater=str(staff_name),
                                                                         t_code=goods_bin_stock_list[j].t_code))
                                    picking_list_label = 1
                                    dn_pick_qty = dn_pick_qty + bin_can_pick_qty
                                    goods_qty_change.save()
                                    goods_bin_stock_list[j].save()
                                elif bin_can_pick_qty == 0:
                                    continue
                                else:
                                    continue
                            dn_detail_list[i].pick_qty = dn_pick_qty
                            dn_back_order_qty = dn_detail_list[i].goods_qty - \
                                                dn_detail_list[i].pick_qty
                            dn_detail_list[i].goods_qty = dn_pick_qty
                            dn_detail_list[i].dn_status = 3
                            back_order_goods_volume = round(goods_detail.unit_volume * dn_back_order_qty, 4)
                            back_order_goods_weight = round(
                                weight_to_kg(goods_detail) * dn_back_order_qty, 4)
                            back_order_goods_cost = round(numeric_value(goods_detail.goods_price) * dn_back_order_qty, 2)
                            back_order_list.append(DnDetailModel(dn_code=back_order_dn_code,
                                                                 dn_status=2,
                                                                 customer=qs[v].customer,
                                                                 goods_code=dn_detail_list[i].goods_code,
                                                                 goods_desc=dn_detail_list[i].goods_desc,
                                                                 goods_qty=dn_back_order_qty,
                                                                 goods_weight=back_order_goods_weight,
                                                                 goods_volume=back_order_goods_volume,
                                                                 goods_cost=back_order_goods_cost,
                                                                 creater=str(staff_name),
                                                                 back_order_label=True,
                                                                 openid=self.request.auth.openid,
                                                                 create_time=dn_detail_list[i].create_time))
                            back_order_list_label = 1
                            total_weight = total_weight - back_order_goods_weight
                            total_volume = total_volume - back_order_goods_volume
                            total_cost = total_cost - back_order_goods_cost
                            dn_detail_list[i].goods_weight = dn_detail_list[i].goods_weight - \
                                                             back_order_goods_weight
                            dn_detail_list[i].goods_volume = dn_detail_list[i].goods_volume - \
                                                             back_order_goods_volume
                            dn_detail_list[i].goods_cost = dn_detail_list[i].goods_cost - \
                                                           back_order_goods_cost
                            back_order_goods_weight_list.append(back_order_goods_weight)
                            back_order_goods_volume_list.append(back_order_goods_volume)
                            back_order_goods_cost_list.append(back_order_goods_cost)
                            dn_detail_list[i].save()
                    elif dn_detail_list[i].goods_qty == can_pick_qty:
                        for j in range(len(goods_bin_stock_list)):
                            bin_can_pick_qty = goods_bin_stock_list[j].goods_qty - goods_bin_stock_list[j].pick_qty
                            if bin_can_pick_qty > 0:
                                dn_need_pick_qty = dn_detail_list[i].goods_qty - dn_detail_list[i].pick_qty
                                if dn_need_pick_qty > bin_can_pick_qty:
                                    goods_bin_stock_list[j].pick_qty = goods_bin_stock_list[
                                                                           j].pick_qty + bin_can_pick_qty
                                    if qs[v].back_order_label is True:
                                        goods_qty_change.can_order_stock = goods_qty_change.can_order_stock - bin_can_pick_qty
                                        goods_qty_change.back_order_stock = goods_qty_change.back_order_stock - bin_can_pick_qty
                                    goods_qty_change.ordered_stock = goods_qty_change.ordered_stock - bin_can_pick_qty
                                    goods_qty_change.pick_stock = goods_qty_change.pick_stock + bin_can_pick_qty
                                    picking_list.append(PickingListModel(openid=self.request.auth.openid,
                                                                         dn_code=dn_detail_list[i].dn_code,
                                                                         bin_name=goods_bin_stock_list[j].bin_name,
                                                                         goods_code=goods_bin_stock_list[j].goods_code,
                                                                         pick_qty=bin_can_pick_qty,
                                                                         creater=str(staff_name),
                                                                         t_code=goods_bin_stock_list[j].t_code))
                                    picking_list_label = 1
                                    dn_detail_list[i].pick_qty = dn_detail_list[i].pick_qty + bin_can_pick_qty
                                    goods_bin_stock_list[j].save()
                                    goods_qty_change.save()
                                elif dn_need_pick_qty == bin_can_pick_qty:
                                    goods_bin_stock_list[j].pick_qty = goods_bin_stock_list[
                                                                           j].pick_qty + bin_can_pick_qty
                                    if qs[v].back_order_label is True:
                                        goods_qty_change.can_order_stock = goods_qty_change.can_order_stock - bin_can_pick_qty
                                        goods_qty_change.back_order_stock = goods_qty_change.back_order_stock - bin_can_pick_qty
                                    goods_qty_change.ordered_stock = goods_qty_change.ordered_stock - bin_can_pick_qty
                                    goods_qty_change.pick_stock = goods_qty_change.pick_stock + bin_can_pick_qty
                                    picking_list.append(PickingListModel(openid=self.request.auth.openid,
                                                                         dn_code=dn_detail_list[i].dn_code,
                                                                         bin_name=goods_bin_stock_list[j].bin_name,
                                                                         goods_code=goods_bin_stock_list[j].goods_code,
                                                                         pick_qty=bin_can_pick_qty,
                                                                         creater=str(staff_name),
                                                                         t_code=goods_bin_stock_list[j].t_code))
                                    picking_list_label = 1
                                    dn_detail_list[i].pick_qty = dn_detail_list[i].pick_qty + bin_can_pick_qty
                                    dn_detail_list[i].dn_status = 3
                                    dn_detail_list[i].save()
                                    goods_bin_stock_list[j].save()
                                    goods_qty_change.save()
                                    break
                                else:
                                    break
                            elif bin_can_pick_qty == 0:
                                continue
                            else:
                                continue
                    elif dn_detail_list[i].goods_qty < can_pick_qty:
                        for j in range(len(goods_bin_stock_list)):
                            bin_can_pick_qty = goods_bin_stock_list[j].goods_qty - \
                                               goods_bin_stock_list[j].pick_qty
                            if bin_can_pick_qty > 0:
                                dn_need_pick_qty = dn_detail_list[i].goods_qty - \
                                                   dn_detail_list[i].pick_qty
                                if dn_need_pick_qty > bin_can_pick_qty:
                                    goods_bin_stock_list[j].pick_qty = goods_bin_stock_list[j].pick_qty + \
                                                                       bin_can_pick_qty
                                    if qs[v].back_order_label is True:
                                        goods_qty_change.can_order_stock = goods_qty_change.can_order_stock - bin_can_pick_qty
                                        goods_qty_change.back_order_stock = goods_qty_change.back_order_stock - bin_can_pick_qty
                                    goods_qty_change.ordered_stock = goods_qty_change.ordered_stock - \
                                                                     bin_can_pick_qty
                                    goods_qty_change.pick_stock = goods_qty_change.pick_stock + \
                                                                  bin_can_pick_qty
                                    picking_list.append(PickingListModel(openid=self.request.auth.openid,
                                                                         dn_code=dn_detail_list[i].dn_code,
                                                                         bin_name=goods_bin_stock_list[j].bin_name,
                                                                         goods_code=goods_bin_stock_list[j].goods_code,
                                                                         pick_qty=bin_can_pick_qty,
                                                                         creater=str(staff_name),
                                                                         t_code=goods_bin_stock_list[j].t_code))
                                    picking_list_label = 1
                                    dn_detail_list[i].pick_qty = dn_detail_list[i].pick_qty + \
                                                                 bin_can_pick_qty
                                    dn_detail_list[i].save()
                                    goods_bin_stock_list[j].save()
                                    goods_qty_change.save()
                                elif dn_need_pick_qty == bin_can_pick_qty:
                                    goods_bin_stock_list[j].pick_qty = goods_bin_stock_list[
                                                                           j].pick_qty + bin_can_pick_qty
                                    if qs[v].back_order_label is True:
                                        goods_qty_change.can_order_stock = goods_qty_change.can_order_stock - bin_can_pick_qty
                                        goods_qty_change.back_order_stock = goods_qty_change.back_order_stock - bin_can_pick_qty
                                    goods_qty_change.ordered_stock = goods_qty_change.ordered_stock - bin_can_pick_qty
                                    goods_qty_change.pick_stock = goods_qty_change.pick_stock + bin_can_pick_qty
                                    picking_list.append(PickingListModel(openid=self.request.auth.openid,
                                                                         dn_code=dn_detail_list[i].dn_code,
                                                                         bin_name=goods_bin_stock_list[j].bin_name,
                                                                         goods_code=goods_bin_stock_list[j].goods_code,
                                                                         pick_qty=bin_can_pick_qty,
                                                                         creater=str(staff_name),
                                                                         t_code=goods_bin_stock_list[j].t_code))
                                    picking_list_label = 1
                                    dn_detail_list[i].pick_qty = dn_detail_list[i].pick_qty + bin_can_pick_qty
                                    dn_detail_list[i].dn_status = 3
                                    dn_detail_list[i].save()
                                    goods_bin_stock_list[j].save()
                                    goods_qty_change.save()
                                    break
                                elif dn_need_pick_qty < bin_can_pick_qty:
                                    goods_bin_stock_list[j].pick_qty = goods_bin_stock_list[j].pick_qty + \
                                                                       dn_need_pick_qty
                                    if qs[v].back_order_label is True:
                                        goods_qty_change.can_order_stock = goods_qty_change.can_order_stock - dn_need_pick_qty
                                        goods_qty_change.back_order_stock = goods_qty_change.back_order_stock - dn_need_pick_qty
                                    goods_qty_change.ordered_stock = goods_qty_change.ordered_stock - \
                                                                     dn_need_pick_qty
                                    goods_qty_change.pick_stock = goods_qty_change.pick_stock + \
                                                                  dn_need_pick_qty
                                    picking_list.append(PickingListModel(openid=self.request.auth.openid,
                                                                         dn_code=dn_detail_list[i].dn_code,
                                                                         bin_name=goods_bin_stock_list[j].bin_name,
                                                                         goods_code=goods_bin_stock_list[j].goods_code,
                                                                         pick_qty=dn_need_pick_qty,
                                                                         creater=str(staff_name),
                                                                         t_code=goods_bin_stock_list[j].t_code))
                                    picking_list_label = 1
                                    dn_detail_list[i].pick_qty = dn_detail_list[i].pick_qty + dn_need_pick_qty
                                    dn_detail_list[i].dn_status = 3
                                    dn_detail_list[i].save()
                                    goods_bin_stock_list[j].save()
                                    goods_qty_change.save()
                                    break
                                else:
                                    break
                            elif bin_can_pick_qty == 0:
                                continue
                            else:
                                continue
                elif can_pick_qty == 0:
                    if qs[v].back_order_label is False:
                        goods_qty_change.back_order_stock = goods_qty_change.back_order_stock + dn_detail_list[
                            i].goods_qty
                        back_order_goods_volume = round(goods_detail.unit_volume * dn_detail_list[i].goods_qty, 4)
                        back_order_goods_weight = round(
                            weight_to_kg(goods_detail) * dn_detail_list[i].goods_qty, 4)
                        back_order_goods_cost = round(numeric_value(goods_detail.goods_price) * dn_detail_list[i].goods_qty, 2)
                        back_order_list.append(DnDetailModel(dn_code=back_order_dn_code,
                                                             dn_status=2,
                                                             customer=qs[v].customer,
                                                             goods_code=dn_detail_list[i].goods_code,
                                                             goods_desc=dn_detail_list[i].goods_desc,
                                                             goods_qty=dn_detail_list[i].goods_qty,
                                                             goods_weight=back_order_goods_weight,
                                                             goods_volume=back_order_goods_volume,
                                                             goods_cost=back_order_goods_cost,
                                                             creater=str(staff_name),
                                                             back_order_label=True,
                                                             openid=self.request.auth.openid,
                                                             create_time=dn_detail_list[i].create_time))
                        back_order_list_label = 1
                        total_weight = total_weight - back_order_goods_weight
                        total_volume = total_volume - back_order_goods_volume
                        total_cost = total_cost - back_order_goods_cost
                        back_order_goods_weight_list.append(back_order_goods_weight)
                        back_order_goods_volume_list.append(back_order_goods_volume)
                        back_order_goods_cost_list.append(back_order_goods_cost)
                        dn_detail_list[i].is_delete = True
                        dn_detail_list[i].save()
                        goods_qty_change.save()
                    else:
                        continue
                else:
                    continue
            if picking_list_label == 1:
                if back_order_list_label == 1:
                    back_order_total_volume = sumOfList(back_order_goods_volume_list,
                                                        len(back_order_goods_volume_list))
                    back_order_total_weight = sumOfList(back_order_goods_weight_list,
                                                        len(back_order_goods_weight_list))
                    back_order_total_cost = sumOfList(back_order_goods_cost_list,
                                                      len(back_order_goods_cost_list))
                    customer_city = customer.objects.filter(openid=self.request.auth.openid,
                                                            customer_name=str(qs[v].customer),
                                                            is_delete=False).first().customer_city
                    warehouse_city = warehouse.objects.filter(
                        openid=self.request.auth.openid).first().warehouse_city
                    transportation_fee = transportation.objects.filter(
                        Q(openid=self.request.auth.openid, send_city__icontains=warehouse_city,
                          receiver_city__icontains=customer_city,
                          is_delete=False) | Q(openid='init_data', send_city__icontains=warehouse_city,
                                               receiver_city__icontains=customer_city,
                                               is_delete=False))
                    transportation_res = {
                        "detail": []
                    }
                    transportation_back_order_res = {
                        "detail": []
                    }
                    if len(transportation_fee) >= 1:
                        transportation_list = []
                        transportation_back_order_list = []
                        for k in range(len(transportation_fee)):
                            transportation_cost = transportation_calculate(total_weight,
                                                                           total_volume,
                                                                           transportation_fee[k].weight_fee,
                                                                           transportation_fee[k].volume_fee,
                                                                           transportation_fee[k].min_payment)
                            transportation_back_order_cost = transportation_calculate(back_order_total_weight,
                                                                                      back_order_total_volume,
                                                                                      transportation_fee[k].weight_fee,
                                                                                      transportation_fee[k].volume_fee,
                                                                                      transportation_fee[k].min_payment)
                            transportation_detail = {
                                "transportation_supplier": transportation_fee[k].transportation_supplier,
                                "transportation_cost": transportation_cost
                            }
                            transportation_back_order_detail = {
                                "transportation_supplier": transportation_fee[k].transportation_supplier,
                                "transportation_cost": transportation_back_order_cost
                            }
                            transportation_list.append(transportation_detail)
                            transportation_back_order_list.append(transportation_back_order_detail)
                        transportation_res['detail'] = transportation_list
                        transportation_back_order_res['detail'] = transportation_back_order_list
                    DnListModel.objects.create(openid=self.request.auth.openid,
                                               dn_code=back_order_dn_code,
                                               dn_status=2,
                                               total_weight=back_order_total_weight,
                                               total_volume=back_order_total_volume,
                                               total_cost=back_order_total_cost,
                                               customer=qs[v].customer,
                                               creater=str(staff_name),
                                               bar_code=bar_code,
                                               back_order_label=True,
                                               transportation_fee=transportation_back_order_res,
                                               create_time=qs[v].create_time)
                    scanner.objects.create(openid=self.request.auth.openid, mode="DN", code=back_order_dn_code,
                                           bar_code=bar_code)
                    PickingListModel.objects.bulk_create(picking_list, batch_size=100)
                    DnDetailModel.objects.bulk_create(back_order_list, batch_size=100)
                    qs[v].total_weight = total_weight
                    qs[v].total_volume = total_volume
                    qs[v].total_cost = total_cost
                    qs[v].transportation_fee = transportation_res
                    qs[v].dn_status = 3
                    qs[v].save()
                elif back_order_list_label == 0:
                    PickingListModel.objects.bulk_create(picking_list, batch_size=100)
                    qs[v].dn_status = 3
                    qs[v].save()
            elif picking_list_label == 0:
                if back_order_list_label == 1:
                    DnDetailModel.objects.bulk_create(back_order_list, batch_size=100)
                    DnListModel.objects.create(openid=self.request.auth.openid,
                                               dn_code=back_order_dn_code,
                                               dn_status=2,
                                               total_weight=qs[v].total_weight,
                                               total_volume=qs[v].total_volume,
                                               total_cost=qs[v].total_cost,
                                               customer=qs[v].customer,
                                               creater=str(staff_name),
                                               bar_code=bar_code,
                                               back_order_label=True,
                                               transportation_fee=qs[v].transportation_fee,
                                               create_time=qs[v].create_time)
                    scanner.objects.create(openid=self.request.auth.openid, mode="DN", code=back_order_dn_code,
                                           bar_code=bar_code)
                    qs[v].is_delete = True
                    qs[v].dn_status = 3
                    qs[v].save()
            else:
                continue
        return Response({"detail": "success"}, status=200)

    @transaction.atomic
    def update(self, request, pk):
        qs = self.get_object()
        if qs.openid != self.request.auth.openid:
            raise APIException({"detail": "Cannot Release Order Data Which Not Yours"})
        else:
            if qs.dn_status == 2:
                command, replay = _agent_preview(request, 'outbound.order_release', resource_id=pk)
                if replay is not None:
                    return Response(replay)
                staff_name = staff.objects.filter(openid=self.request.auth.openid,
                                                  id=self.request.META.get('HTTP_OPERATOR')).first().staff_name
                dn_detail_list = DnDetailModel.objects.filter(openid=self.request.auth.openid,
                                                              dn_code=qs.dn_code,
                                                              dn_status=2, is_delete=False)
                picking_list = []
                picking_list_label = 0
                back_order_list = []
                back_order_list_label = 0
                back_order_goods_weight_list = []
                back_order_goods_volume_list = []
                back_order_goods_cost_list = []
                back_order_base_code = DnListModel.objects.filter(openid=self.request.auth.openid, is_delete=False).order_by('-id').first().dn_code
                dn_last_code = re.findall(r'\d+', str(back_order_base_code), re.IGNORECASE)
                back_order_dn_code = 'DN' + str(int(dn_last_code[0]) + 1).zfill(8)
                bar_code = Md5.md5(back_order_dn_code)
                total_weight = qs.total_weight
                total_volume = qs.total_volume
                total_cost = qs.total_cost
                for i in range(len(dn_detail_list)):
                    goods_detail = goods.objects.filter(openid=self.request.auth.openid,
                                                        goods_code=str(dn_detail_list[i].goods_code),
                                                        is_delete=False).first()
                    if stocklist.objects.filter(openid=self.request.auth.openid,
                                                goods_code=str(dn_detail_list[i].goods_code)).exists():
                        pass
                    else:
                        stocklist.objects.create(openid=self.request.auth.openid,
                                                 goods_code=str(goods_detail.goods_code),
                                                 goods_desc=goods_detail.goods_desc,
                                                 dn_stock=int(dn_detail_list[i].goods_qty))
                    goods_qty_change = stocklist.objects.filter(openid=self.request.auth.openid,
                                                                goods_code=str(
                                                                    dn_detail_list[i].goods_code)).first()
                    goods_bin_stock_list = stockbin.objects.filter(openid=self.request.auth.openid,
                                                                   goods_code=str(dn_detail_list[i].goods_code),
                                                                   bin_property="Normal", goods_qty__gt=0).order_by('id')
                    can_pick_qty = goods_qty_change.onhand_stock - \
                                   goods_qty_change.inspect_stock - \
                                   goods_qty_change.hold_stock - \
                                   goods_qty_change.damage_stock - \
                                   goods_qty_change.pick_stock
                    if can_pick_qty > 0:
                        if dn_detail_list[i].goods_qty > can_pick_qty:
                            if qs.back_order_label is False:
                                dn_pick_qty = dn_detail_list[i].pick_qty
                                for j in range(len(goods_bin_stock_list)):
                                    bin_can_pick_qty = goods_bin_stock_list[j].goods_qty - \
                                                       goods_bin_stock_list[j].pick_qty
                                    if bin_can_pick_qty > 0:
                                        goods_bin_stock_list[j].pick_qty = goods_bin_stock_list[
                                                                               j].pick_qty + bin_can_pick_qty
                                        goods_qty_change.ordered_stock = goods_qty_change.ordered_stock - bin_can_pick_qty
                                        goods_qty_change.pick_stock = goods_qty_change.pick_stock + bin_can_pick_qty
                                        picking_list.append(PickingListModel(openid=self.request.auth.openid,
                                                                             dn_code=dn_detail_list[i].dn_code,
                                                                             bin_name=goods_bin_stock_list[j].bin_name,
                                                                             goods_code=goods_bin_stock_list[
                                                                                 j].goods_code,
                                                                             pick_qty=bin_can_pick_qty,
                                                                             creater=str(staff_name),
                                                                             t_code=goods_bin_stock_list[j].t_code))
                                        picking_list_label = 1
                                        dn_pick_qty = dn_pick_qty + bin_can_pick_qty
                                        goods_qty_change.save()
                                        goods_bin_stock_list[j].save()
                                    elif bin_can_pick_qty == 0:
                                        continue
                                    else:
                                        continue
                                dn_detail_list[i].pick_qty = dn_pick_qty
                                dn_back_order_qty = dn_detail_list[i].goods_qty - \
                                                   dn_detail_list[i].pick_qty
                                goods_qty_change.back_order_stock = dn_detail_list[i].goods_qty - can_pick_qty
                                dn_detail_list[i].goods_qty = dn_pick_qty
                                dn_detail_list[i].dn_status = 3
                                back_order_goods_volume = round(goods_detail.unit_volume * dn_back_order_qty, 4)
                                back_order_goods_weight = round(
                                    weight_to_kg(goods_detail) * dn_back_order_qty, 4)
                                back_order_goods_cost = round(numeric_value(goods_detail.goods_price) * dn_back_order_qty, 2)
                                back_order_list.append(DnDetailModel(dn_code=back_order_dn_code,
                                                                     dn_status=2,
                                                                     customer=qs.customer,
                                                                     goods_code=dn_detail_list[i].goods_code,
                                                                     goods_desc=dn_detail_list[i].goods_desc,
                                                                     goods_qty=dn_back_order_qty,
                                                                     goods_weight=back_order_goods_weight,
                                                                     goods_volume=back_order_goods_volume,
                                                                     goods_cost=back_order_goods_cost,
                                                                     creater=str(staff_name),
                                                                     back_order_label=True,
                                                                     openid=self.request.auth.openid,
                                                                     create_time=dn_detail_list[i].create_time))
                                back_order_list_label = 1
                                total_weight = total_weight - back_order_goods_weight
                                total_volume = total_volume - back_order_goods_volume
                                total_cost = total_cost - back_order_goods_cost
                                dn_detail_list[i].goods_weight = dn_detail_list[i].goods_weight - \
                                                                 back_order_goods_weight
                                dn_detail_list[i].goods_volume = dn_detail_list[i].goods_volume - \
                                                                 back_order_goods_volume
                                dn_detail_list[i].goods_cost = dn_detail_list[i].goods_cost - \
                                                                 back_order_goods_cost
                                back_order_goods_weight_list.append(back_order_goods_weight)
                                back_order_goods_volume_list.append(back_order_goods_volume)
                                back_order_goods_cost_list.append(back_order_goods_cost)
                                goods_qty_change.save()
                                dn_detail_list[i].save()
                            else:
                                dn_pick_qty = dn_detail_list[i].pick_qty
                                for j in range(len(goods_bin_stock_list)):
                                    bin_can_pick_qty = goods_bin_stock_list[j].goods_qty - \
                                                       goods_bin_stock_list[j].pick_qty
                                    if bin_can_pick_qty > 0:
                                        goods_bin_stock_list[j].pick_qty = goods_bin_stock_list[
                                                                               j].pick_qty + bin_can_pick_qty
                                        goods_qty_change.ordered_stock = goods_qty_change.ordered_stock - bin_can_pick_qty
                                        goods_qty_change.can_order_stock = goods_qty_change.can_order_stock - bin_can_pick_qty
                                        goods_qty_change.back_order_stock = goods_qty_change.back_order_stock - bin_can_pick_qty
                                        goods_qty_change.pick_stock = goods_qty_change.pick_stock + bin_can_pick_qty
                                        picking_list.append(PickingListModel(openid=self.request.auth.openid,
                                                                             dn_code=dn_detail_list[i].dn_code,
                                                                             bin_name=goods_bin_stock_list[j].bin_name,
                                                                             goods_code=goods_bin_stock_list[
                                                                                 j].goods_code,
                                                                             pick_qty=bin_can_pick_qty,
                                                                             creater=str(staff_name),
                                                                             t_code=goods_bin_stock_list[j].t_code))
                                        picking_list_label = 1
                                        dn_pick_qty = dn_pick_qty + bin_can_pick_qty
                                        goods_qty_change.save()
                                        goods_bin_stock_list[j].save()
                                    elif bin_can_pick_qty == 0:
                                        continue
                                    else:
                                        continue
                                dn_detail_list[i].pick_qty = dn_pick_qty
                                dn_back_order_qty = dn_detail_list[i].goods_qty - \
                                                    dn_detail_list[i].pick_qty
                                dn_detail_list[i].goods_qty = dn_pick_qty
                                dn_detail_list[i].dn_status = 3
                                back_order_goods_volume = round(goods_detail.unit_volume * dn_back_order_qty, 4)
                                back_order_goods_weight = round(
                                    weight_to_kg(goods_detail) * dn_back_order_qty, 4)
                                back_order_goods_cost = round(numeric_value(goods_detail.goods_price) * dn_back_order_qty, 2)
                                back_order_list.append(DnDetailModel(dn_code=back_order_dn_code,
                                                                     dn_status=2,
                                                                     customer=qs.customer,
                                                                     goods_code=dn_detail_list[i].goods_code,
                                                                     goods_desc=dn_detail_list[i].goods_desc,
                                                                     goods_qty=dn_back_order_qty,
                                                                     goods_weight=back_order_goods_weight,
                                                                     goods_volume=back_order_goods_volume,
                                                                     goods_cost=back_order_goods_cost,
                                                                     creater=str(staff_name),
                                                                     back_order_label=True,
                                                                     openid=self.request.auth.openid,
                                                                     create_time=dn_detail_list[i].create_time))
                                back_order_list_label = 1
                                total_weight = total_weight - back_order_goods_weight
                                total_volume = total_volume - back_order_goods_volume
                                total_cost = total_cost - back_order_goods_cost
                                dn_detail_list[i].goods_weight = dn_detail_list[i].goods_weight - \
                                                                 back_order_goods_weight
                                dn_detail_list[i].goods_volume = dn_detail_list[i].goods_volume - \
                                                                 back_order_goods_volume
                                dn_detail_list[i].goods_cost = dn_detail_list[i].goods_cost - \
                                                                 back_order_goods_cost
                                back_order_goods_weight_list.append(back_order_goods_weight)
                                back_order_goods_volume_list.append(back_order_goods_volume)
                                back_order_goods_cost_list.append(back_order_goods_cost)
                                dn_detail_list[i].save()
                        elif dn_detail_list[i].goods_qty == can_pick_qty:
                            for j in range(len(goods_bin_stock_list)):
                                bin_can_pick_qty = goods_bin_stock_list[j].goods_qty - goods_bin_stock_list[j].pick_qty
                                if bin_can_pick_qty > 0:
                                    dn_need_pick_qty = dn_detail_list[i].goods_qty - dn_detail_list[i].pick_qty
                                    if dn_need_pick_qty > bin_can_pick_qty:
                                        goods_bin_stock_list[j].pick_qty = goods_bin_stock_list[
                                                                               j].pick_qty + bin_can_pick_qty
                                        if qs.back_order_label is True:
                                            goods_qty_change.can_order_stock = goods_qty_change.can_order_stock - bin_can_pick_qty
                                            goods_qty_change.back_order_stock = goods_qty_change.back_order_stock - bin_can_pick_qty
                                        goods_qty_change.ordered_stock = goods_qty_change.ordered_stock - bin_can_pick_qty
                                        goods_qty_change.pick_stock = goods_qty_change.pick_stock + bin_can_pick_qty
                                        picking_list.append(PickingListModel(openid=self.request.auth.openid,
                                                                             dn_code=dn_detail_list[i].dn_code,
                                                                             bin_name=goods_bin_stock_list[j].bin_name,
                                                                             goods_code=goods_bin_stock_list[j].goods_code,
                                                                             pick_qty=bin_can_pick_qty,
                                                                             creater=str(staff_name),
                                                                             t_code=goods_bin_stock_list[j].t_code))
                                        picking_list_label = 1
                                        dn_detail_list[i].pick_qty = dn_detail_list[i].pick_qty + bin_can_pick_qty
                                        goods_bin_stock_list[j].save()
                                        goods_qty_change.save()
                                    elif dn_need_pick_qty == bin_can_pick_qty:
                                        goods_bin_stock_list[j].pick_qty = goods_bin_stock_list[
                                                                               j].pick_qty + bin_can_pick_qty
                                        if qs.back_order_label is True:
                                            goods_qty_change.can_order_stock = goods_qty_change.can_order_stock - bin_can_pick_qty
                                            goods_qty_change.back_order_stock = goods_qty_change.back_order_stock - bin_can_pick_qty
                                        goods_qty_change.ordered_stock = goods_qty_change.ordered_stock - bin_can_pick_qty
                                        goods_qty_change.pick_stock = goods_qty_change.pick_stock + bin_can_pick_qty
                                        picking_list.append(PickingListModel(openid=self.request.auth.openid,
                                                                             dn_code=dn_detail_list[i].dn_code,
                                                                             bin_name=goods_bin_stock_list[j].bin_name,
                                                                             goods_code=goods_bin_stock_list[j].goods_code,
                                                                             pick_qty=bin_can_pick_qty,
                                                                             creater=str(staff_name),
                                                                             t_code=goods_bin_stock_list[j].t_code))
                                        picking_list_label = 1
                                        dn_detail_list[i].pick_qty = dn_detail_list[i].pick_qty + bin_can_pick_qty
                                        dn_detail_list[i].dn_status = 3
                                        dn_detail_list[i].save()
                                        goods_bin_stock_list[j].save()
                                        goods_qty_change.save()
                                        break
                                    else:
                                        break
                                elif bin_can_pick_qty == 0:
                                    continue
                                else:
                                    continue
                        elif dn_detail_list[i].goods_qty < can_pick_qty:
                            for j in range(len(goods_bin_stock_list)):
                                bin_can_pick_qty = goods_bin_stock_list[j].goods_qty - \
                                                   goods_bin_stock_list[j].pick_qty
                                if bin_can_pick_qty > 0:
                                    dn_need_pick_qty = dn_detail_list[i].goods_qty - \
                                                       dn_detail_list[i].pick_qty
                                    if dn_need_pick_qty > bin_can_pick_qty:
                                        goods_bin_stock_list[j].pick_qty = goods_bin_stock_list[j].pick_qty + \
                                                                           bin_can_pick_qty
                                        if qs.back_order_label is True:
                                            goods_qty_change.can_order_stock = goods_qty_change.can_order_stock - bin_can_pick_qty
                                            goods_qty_change.back_order_stock = goods_qty_change.back_order_stock - bin_can_pick_qty
                                        goods_qty_change.ordered_stock = goods_qty_change.ordered_stock - \
                                                                         bin_can_pick_qty
                                        goods_qty_change.pick_stock = goods_qty_change.pick_stock + \
                                                                      bin_can_pick_qty
                                        picking_list.append(PickingListModel(openid=self.request.auth.openid,
                                                                             dn_code=dn_detail_list[i].dn_code,
                                                                             bin_name=goods_bin_stock_list[j].bin_name,
                                                                             goods_code=goods_bin_stock_list[j].goods_code,
                                                                             pick_qty=bin_can_pick_qty,
                                                                             creater=str(staff_name),
                                                                             t_code=goods_bin_stock_list[j].t_code))
                                        picking_list_label = 1
                                        dn_detail_list[i].pick_qty = dn_detail_list[i].pick_qty + \
                                                                     bin_can_pick_qty
                                        dn_detail_list[i].save()
                                        goods_bin_stock_list[j].save()
                                        goods_qty_change.save()
                                    elif dn_need_pick_qty == bin_can_pick_qty:
                                        goods_bin_stock_list[j].pick_qty = goods_bin_stock_list[
                                                                               j].pick_qty + bin_can_pick_qty
                                        if qs.back_order_label is True:
                                            goods_qty_change.can_order_stock = goods_qty_change.can_order_stock - bin_can_pick_qty
                                            goods_qty_change.back_order_stock = goods_qty_change.back_order_stock - bin_can_pick_qty
                                        goods_qty_change.ordered_stock = goods_qty_change.ordered_stock - bin_can_pick_qty
                                        goods_qty_change.pick_stock = goods_qty_change.pick_stock + bin_can_pick_qty
                                        picking_list.append(PickingListModel(openid=self.request.auth.openid,
                                                                             dn_code=dn_detail_list[i].dn_code,
                                                                             bin_name=goods_bin_stock_list[j].bin_name,
                                                                             goods_code=goods_bin_stock_list[j].goods_code,
                                                                             pick_qty=bin_can_pick_qty,
                                                                             creater=str(staff_name),
                                                                             t_code=goods_bin_stock_list[j].t_code))
                                        picking_list_label = 1
                                        dn_detail_list[i].pick_qty = dn_detail_list[i].pick_qty + bin_can_pick_qty
                                        dn_detail_list[i].dn_status = 3
                                        dn_detail_list[i].save()
                                        goods_bin_stock_list[j].save()
                                        goods_qty_change.save()
                                        break
                                    elif dn_need_pick_qty < bin_can_pick_qty:
                                        goods_bin_stock_list[j].pick_qty = goods_bin_stock_list[j].pick_qty + \
                                                                           dn_need_pick_qty
                                        if qs.back_order_label is True:
                                            goods_qty_change.can_order_stock = goods_qty_change.can_order_stock - dn_need_pick_qty
                                            goods_qty_change.back_order_stock = goods_qty_change.back_order_stock - dn_need_pick_qty
                                        goods_qty_change.ordered_stock = goods_qty_change.ordered_stock - \
                                                                         dn_need_pick_qty
                                        goods_qty_change.pick_stock = goods_qty_change.pick_stock + \
                                                                      dn_need_pick_qty
                                        picking_list.append(PickingListModel(openid=self.request.auth.openid,
                                                                             dn_code=dn_detail_list[i].dn_code,
                                                                             bin_name=goods_bin_stock_list[j].bin_name,
                                                                             goods_code=goods_bin_stock_list[j].goods_code,
                                                                             pick_qty=dn_need_pick_qty,
                                                                             creater=str(staff_name),
                                                                             t_code=goods_bin_stock_list[j].t_code))
                                        picking_list_label = 1
                                        dn_detail_list[i].pick_qty = dn_detail_list[i].pick_qty + dn_need_pick_qty
                                        dn_detail_list[i].dn_status = 3
                                        dn_detail_list[i].save()
                                        goods_bin_stock_list[j].save()
                                        goods_qty_change.save()
                                        break
                                    else:
                                        break
                                elif bin_can_pick_qty == 0:
                                    continue
                                else:
                                    continue
                    elif can_pick_qty == 0:
                        if qs.back_order_label is False:
                            goods_qty_change.back_order_stock = goods_qty_change.back_order_stock + dn_detail_list[i].goods_qty
                            back_order_goods_volume = round(goods_detail.unit_volume * dn_detail_list[i].goods_qty, 4)
                            back_order_goods_weight = round(weight_to_kg(goods_detail) * dn_detail_list[i].goods_qty, 4)
                            back_order_goods_cost = round(numeric_value(goods_detail.goods_price) * dn_detail_list[i].goods_qty, 2)
                            back_order_list.append(DnDetailModel(dn_code=back_order_dn_code,
                                                                 dn_status=2,
                                                                 customer=qs.customer,
                                                                 goods_code=dn_detail_list[i].goods_code,
                                                                 goods_desc=dn_detail_list[i].goods_desc,
                                                                 goods_qty=dn_detail_list[i].goods_qty,
                                                                 goods_weight=back_order_goods_weight,
                                                                 goods_volume=back_order_goods_volume,
                                                                 goods_cost=back_order_goods_cost,
                                                                 creater=str(staff_name),
                                                                 back_order_label=True,
                                                                 openid=self.request.auth.openid,
                                                                 create_time=dn_detail_list[i].create_time))
                            back_order_list_label = 1
                            total_weight = total_weight - back_order_goods_weight
                            total_volume = total_volume - back_order_goods_volume
                            total_cost = total_cost - back_order_goods_cost
                            back_order_goods_weight_list.append(back_order_goods_weight)
                            back_order_goods_volume_list.append(back_order_goods_volume)
                            back_order_goods_cost_list.append(back_order_goods_cost)
                            dn_detail_list[i].is_delete = True
                            dn_detail_list[i].save()
                            goods_qty_change.save()
                        else:
                            continue
                    else:
                        continue
                if picking_list_label == 1:
                    if back_order_list_label == 1:
                        back_order_total_volume = sumOfList(back_order_goods_volume_list,
                                                            len(back_order_goods_volume_list))
                        back_order_total_weight = sumOfList(back_order_goods_weight_list,
                                                            len(back_order_goods_weight_list))
                        back_order_total_cost = sumOfList(back_order_goods_cost_list,
                                                            len(back_order_goods_cost_list))
                        customer_city = customer.objects.filter(openid=self.request.auth.openid,
                                                                customer_name=str(qs.customer),
                                                                is_delete=False).first().customer_city
                        warehouse_city = warehouse.objects.filter(
                            openid=self.request.auth.openid).first().warehouse_city
                        transportation_fee = transportation.objects.filter(
                            Q(openid=self.request.auth.openid, send_city__icontains=warehouse_city,
                              receiver_city__icontains=customer_city,
                              is_delete=False) | Q(openid='init_data', send_city__icontains=warehouse_city,
                                                   receiver_city__icontains=customer_city,
                                                   is_delete=False))
                        transportation_res = {
                            "detail": []
                        }
                        transportation_back_order_res = {
                            "detail": []
                        }
                        if len(transportation_fee) >= 1:
                            transportation_list = []
                            transportation_back_order_list = []
                            for k in range(len(transportation_fee)):
                                transportation_cost = transportation_calculate(total_weight,
                                                                               total_volume,
                                                                               transportation_fee[k].weight_fee,
                                                                               transportation_fee[k].volume_fee,
                                                                               transportation_fee[k].min_payment)
                                transportation_back_order_cost = transportation_calculate(back_order_total_weight,
                                                                               back_order_total_volume,
                                                                               transportation_fee[k].weight_fee,
                                                                               transportation_fee[k].volume_fee,
                                                                               transportation_fee[k].min_payment)
                                transportation_detail = {
                                    "transportation_supplier": transportation_fee[k].transportation_supplier,
                                    "transportation_cost": transportation_cost
                                }
                                transportation_back_order_detail = {
                                    "transportation_supplier": transportation_fee[k].transportation_supplier,
                                    "transportation_cost": transportation_back_order_cost
                                }
                                transportation_list.append(transportation_detail)
                                transportation_back_order_list.append(transportation_back_order_detail)
                            transportation_res['detail'] = transportation_list
                            transportation_back_order_res['detail'] = transportation_back_order_list
                        DnListModel.objects.create(openid=self.request.auth.openid,
                                                   dn_code=back_order_dn_code,
                                                   dn_status=2,
                                                   total_weight=back_order_total_weight,
                                                   total_volume=back_order_total_volume,
                                                   total_cost=back_order_total_cost,
                                                   customer=qs.customer,
                                                   creater=str(staff_name),
                                                   bar_code=bar_code,
                                                   back_order_label=True,
                                                   transportation_fee=transportation_back_order_res,
                                                   create_time=qs.create_time)
                        scanner.objects.create(openid=self.request.auth.openid, mode="DN", code=back_order_dn_code,
                                               bar_code=bar_code)
                        PickingListModel.objects.bulk_create(picking_list, batch_size=100)
                        DnDetailModel.objects.bulk_create(back_order_list, batch_size=100)
                        qs.total_weight = total_weight
                        qs.total_volume = total_volume
                        qs.total_cost = total_cost
                        qs.transportation_fee = transportation_res
                        qs.dn_status = 3
                        qs.save()
                    elif back_order_list_label == 0:
                        PickingListModel.objects.bulk_create(picking_list, batch_size=100)
                        qs.dn_status = 3
                        qs.save()
                elif picking_list_label == 0:
                    if back_order_list_label == 1:
                        DnDetailModel.objects.bulk_create(back_order_list, batch_size=100)
                        DnListModel.objects.create(openid=self.request.auth.openid,
                                                   dn_code=back_order_dn_code,
                                                   dn_status=2,
                                                   total_weight=qs.total_weight,
                                                   total_volume=qs.total_volume,
                                                   total_cost=qs.total_cost,
                                                   customer=qs.customer,
                                                   creater=str(staff_name),
                                                   bar_code=bar_code,
                                                   back_order_label=True,
                                                   transportation_fee=qs.transportation_fee,
                                                   create_time=qs.create_time)
                        scanner.objects.create(openid=self.request.auth.openid, mode="DN", code=back_order_dn_code,
                                               bar_code=bar_code)
                        qs.is_delete = True
                        qs.dn_status = 3
                        qs.save()
                result = {"detail": "success"}
                complete_preview(command, result)
                return Response(result, status=200)
            else:
                raise APIException({"detail": "This Order Does Not in Release Status"})

class DnPickingListViewSet(viewsets.ModelViewSet):
    """
        retrieve:
            Picklist for pk
    """
    pagination_class = MyPageNumberPagination
    filter_backends = [DjangoFilterBackend, OrderingFilter, ]
    ordering_fields = ['id', "create_time", "update_time", ]
    filter_class = DnListFilter

    def get_project(self):
        try:
            id = self.kwargs.get('pk')
            return id
        except:
            return None

    def get_queryset(self):
        id = self.get_project()
        if self.request.user:
            return DnListModel.objects.filter(openid=self.request.auth.openid, id=id)
        else:
            return DnListModel.objects.none()

    def get_serializer_class(self):
        if self.action in ['retrieve']:
            return serializers.DNListGetSerializer
        else:
            return self.http_method_not_allowed(request=self.request)

    def retrieve(self, request, pk):
        qs = self.get_object()
        if qs.dn_status < 3:
            raise APIException({"detail": "No Picking List Been Created"})
        else:
            picking_qs = PickingListModel.objects.filter(openid=self.request.auth.openid, dn_code=qs.dn_code)
            serializer = serializers.DNPickingListGetSerializer(picking_qs, many=True)
            return Response(serializer.data, status=200)

class DnPickingListFilterViewSet(viewsets.ModelViewSet):
    """
        list:
            Picklist for Filter
    """
    pagination_class = MyPageNumberPagination
    filter_backends = [DjangoFilterBackend, OrderingFilter, ]
    ordering_fields = ['id', "create_time", "update_time", ]
    filter_class = DnPickingListFilter

    def get_queryset(self):
        if self.request.user:
            return PickingListModel.objects.filter(openid=self.request.auth.openid)
        else:
            return PickingListModel.objects.none()

    def get_serializer_class(self):
        if self.action in ['list']:
            return serializers.DNPickingCheckGetSerializer
        else:
            return self.http_method_not_allowed(request=self.request)

class DnPickedViewSet(viewsets.ModelViewSet):
    """
        create:
            Finish Picked
    """
    pagination_class = MyPageNumberPagination
    filter_backends = [DjangoFilterBackend, OrderingFilter, ]
    ordering_fields = ['id', "create_time", "update_time", ]
    filter_class = DnListFilter

    def get_project(self):
        try:
            id = self.kwargs.get('pk')
            return id
        except:
            return None

    def get_queryset(self):
        id = self.get_project()
        if self.request.user:
            if id is None:
                return DnListModel.objects.filter(openid=self.request.auth.openid, is_delete=False)
            else:
                return DnListModel.objects.filter(openid=self.request.auth.openid, id=id, is_delete=False)
        else:
            return DnListModel.objects.none()

    def get_serializer_class(self):
        if self.action in ['create', 'update']:
            return serializers.DNListUpdateSerializer
        else:
            return self.http_method_not_allowed(request=self.request)

    @transaction.atomic
    def create(self, request, pk):
        delete_data = stockbin.objects.filter(openid=self.request.auth.openid,
                                                   goods_qty=0,
                                                   pick_qty=0,
                                                   picked_qty=0)
        if delete_data.exists():
            for i in delete_data:
                i.delete()
        qs = self.get_object()
        if qs.dn_status != 3:
            raise APIException({"detail": "This dn Status Not Pre Pick"})
        else:
            command, replay = _agent_preview(request, 'outbound.pick', resource_id=pk)
            if replay is not None:
                return Response(replay)
            data = self.request.data
            dn_code = str(data.get('dn_code') or qs.dn_code).strip()
            goods_data = data.get('goodsData') or []
            if not isinstance(goods_data, list) or not goods_data:
                raise ValidationError({'detail': 'goodsData must be a non-empty list'})
            pick_customer = str(data.get('customer') or qs.customer or '').strip()
            if not pick_customer:
                raise ValidationError({'detail': 'customer is required'})
            if qs.customer and pick_customer.casefold() != str(qs.customer).casefold():
                raise ValidationError({'detail': 'customer does not match the delivery note'})
            serials_by_goods = _validate_pick_serials(
                self.request.auth.openid,
                qs,
                goods_data,
            )
            for i in range(len(goods_data)):
                pick_qty_change = PickingListModel.objects.filter(openid=self.request.auth.openid,
                                                                  dn_code=dn_code,
                                                                  picking_status=0,
                                                                  t_code=str(goods_data[i].get('t_code'))).first()
                if pick_qty_change is None:
                    raise ValidationError({'detail': 'Picking list row does not exist'})
                if int(goods_data[i].get('pick_qty')) < 0:
                    raise APIException({"detail": str(goods_data[i].get('goods_code')) + " Picked Qty Must >= 0"})
                else:
                    if int(goods_data[i].get('pick_qty')) > pick_qty_change.pick_qty:
                        raise APIException({"detail": str(goods_data[i].get('goods_code')) + " Picked Qty Must Less Than Pick Qty"})
                    else:
                        continue
            qs.dn_status = 4
            staff_name = staff.objects.filter(openid=self.request.auth.openid,
                                              id=self.request.META.get('HTTP_OPERATOR')).first().staff_name
            for j in range(len(goods_data)):
                goods_qty_change = stocklist.objects.filter(openid=self.request.auth.openid,
                                                            goods_code=str(goods_data[j].get('goods_code'))).first()
                dn_detail = DnDetailModel.objects.filter(openid=self.request.auth.openid,
                                                         dn_code=dn_code,
                                                         customer=pick_customer,
                                                         goods_code=str(goods_data[j].get('goods_code'))).first()
                bin_qty_change = stockbin.objects.filter(openid=self.request.auth.openid,
                                                         t_code=str(goods_data[j].get('t_code'))).first()
                pick_qty_change = PickingListModel.objects.filter(openid=self.request.auth.openid,
                                                                  dn_code=dn_code,
                                                                  picking_status=0,
                                                                  t_code=str(goods_data[j].get('t_code'))).first()
                if not goods_qty_change or not dn_detail or not bin_qty_change or not pick_qty_change:
                    raise ValidationError({'detail': 'Picking data does not match the delivery note'})
                qtychangerecorder.objects.create(openid=self.request.auth.openid,
                                                 mode_code=dn_detail.dn_code,
                                                 bin_name=bin_qty_change.bin_name,
                                                 goods_code=bin_qty_change.goods_code,
                                                 goods_desc=bin_qty_change.goods_desc,
                                                 goods_qty=0 - int(goods_data[j].get('pick_qty')),
                                                 store_code=bin_qty_change.t_code,
                                                 creater=str(staff_name)
                                                 )
                cur_date = timezone.now().date()
                bin_stock = stockbin.objects.filter(openid=self.request.auth.openid,
                                                    bin_name=bin_qty_change.bin_name,
                                                    goods_code=bin_qty_change.goods_code,
                                                    ).aggregate(sum=Sum('goods_qty'))["sum"]
                cycle_qty = bin_stock - int(goods_data[j].get('pick_qty'))
                cyclecount.objects.filter(openid=self.request.auth.openid,
                                          bin_name=bin_qty_change.bin_name,
                                          goods_code=bin_qty_change.goods_code,
                                          create_time__gte=cur_date).update(goods_qty=cycle_qty)
                if int(goods_data[j].get('pick_qty')) == pick_qty_change.pick_qty:
                    goods_qty_change.onhand_stock = goods_qty_change.onhand_stock - int(goods_data[j].get('pick_qty'))
                    goods_qty_change.pick_stock = goods_qty_change.pick_stock - int(goods_data[j].get('pick_qty'))
                    goods_qty_change.picked_stock = goods_qty_change.picked_stock + int(goods_data[j].get('pick_qty'))
                    pick_qty_change.picked_qty = int(goods_data[j].get('pick_qty'))
                    pick_qty_change.picking_status = 1
                    bin_qty_change.goods_qty = bin_qty_change.goods_qty - int(goods_data[j].get('pick_qty'))
                    bin_qty_change.pick_qty = bin_qty_change.pick_qty - int(goods_data[j].get('pick_qty'))
                    bin_qty_change.picked_qty = bin_qty_change.picked_qty + int(goods_data[j].get('pick_qty'))
                    goods_qty_change.save()
                    pick_qty_change.save()
                    bin_qty_change.save()
                elif int(goods_data[j].get('pick_qty')) < pick_qty_change.pick_qty:
                    goods_qty_change.onhand_stock = goods_qty_change.onhand_stock - int(goods_data[j].get('pick_qty'))
                    goods_qty_change.pick_stock = goods_qty_change.pick_stock - dn_detail.pick_qty
                    goods_qty_change.picked_stock = goods_qty_change.picked_stock + int(goods_data[j].get('pick_qty'))
                    goods_qty_change.can_order_stock = goods_qty_change.can_order_stock + (int(pick_qty_change.pick_qty) - int(
                        goods_data[j].get('pick_qty')))
                    pick_qty_change.picked_qty = int(goods_data[j].get('pick_qty'))
                    pick_qty_change.picking_status = 1
                    bin_qty_change.goods_qty = bin_qty_change.goods_qty - int(goods_data[j].get('pick_qty'))
                    bin_qty_change.pick_qty = bin_qty_change.pick_qty - pick_qty_change.pick_qty
                    bin_qty_change.picked_qty = bin_qty_change.picked_qty + int(goods_data[j].get('pick_qty'))
                    goods_qty_change.save()
                    pick_qty_change.save()
                    bin_qty_change.save()
                dn_detail.picked_qty = dn_detail.picked_qty + int(goods_data[j].get('pick_qty'))
                if dn_detail.dn_status == 3:
                    dn_detail.dn_status = 4
                if dn_detail.pick_qty > 0:
                    dn_detail.pick_qty = 0
                dn_detail.save()
            if DnDetailModel.objects.filter(openid=self.request.auth.openid, dn_code=dn_code, dn_status=3).exists() is False:
                qs.save()
            _mark_picked_serials(self.request.auth.openid, qs, serials_by_goods)
            result = {"Detail": "success"}
            complete_preview(command, result)
            return Response(result, status=200)

    @transaction.atomic
    def update(self, request, *args, **kwargs):
        delete_data = stockbin.objects.filter(openid=self.request.auth.openid,
                                              goods_qty=0,
                                              pick_qty=0,
                                              picked_qty=0)
        if delete_data.exists():
            for i in delete_data:
                i.delete()
        data = self.request.data
        qs = self.get_queryset().filter(dn_code=data['dn_code']).first()
        if qs.dn_status != 3:
            raise APIException({"detail": "This dn Status Not Pre Pick"})
        else:
            serials_by_goods = _validate_pick_serials(
                self.request.auth.openid,
                qs,
                data.get('goodsData') or [],
            )
            for i in range(len(data['goodsData'])):
                pick_qty_change = PickingListModel.objects.filter(openid=self.request.auth.openid,
                                                                  dn_code=str(data['dn_code']),
                                                                  picking_status=0,
                                                                  t_code=str(
                                                                      data['goodsData'][i].get('t_code'))).first()
                if int(data['goodsData'][i].get('picked_qty')) < 0:
                    raise APIException(
                        {"detail": str(data['goodsData'][i].get('goods_code')) + " Picked Qty Must >= 0"})
                else:
                    if int(data['goodsData'][i].get('picked_qty')) > pick_qty_change.pick_qty:
                        raise APIException(
                            {"detail": str(
                                data['goodsData'][i].get('goods_code')) + " Picked Qty Must Less Than Pick Qty"})
                    else:
                        continue
            qs.dn_status = 4
            staff_name = staff.objects.filter(openid=self.request.auth.openid,
                                              id=self.request.META.get('HTTP_OPERATOR')).first().staff_name
            for j in range(len(data['goodsData'])):
                goods_qty_change = stocklist.objects.filter(openid=self.request.auth.openid,
                                                            goods_code=str(
                                                                data['goodsData'][j].get('goods_code'))).first()
                dn_detail = DnDetailModel.objects.filter(openid=self.request.auth.openid,
                                                         dn_code=str(data['dn_code']),
                                                         customer=str(data['customer']),
                                                         goods_code=str(data['goodsData'][j].get('goods_code'))).first()
                bin_qty_change = stockbin.objects.filter(openid=self.request.auth.openid,
                                                         t_code=str(data['goodsData'][j].get('t_code'))).first()
                pick_qty_change = PickingListModel.objects.filter(openid=self.request.auth.openid,
                                                                  dn_code=str(data['dn_code']),
                                                                  picking_status=0,
                                                                  t_code=str(
                                                                      data['goodsData'][j].get('t_code'))).first()
                qtychangerecorder.objects.create(openid=self.request.auth.openid,
                                                 mode_code=dn_detail.dn_code,
                                                 bin_name=bin_qty_change.bin_name,
                                                 goods_code=bin_qty_change.goods_code,
                                                 goods_desc=bin_qty_change.goods_desc,
                                                 goods_qty=0 - int(data['goodsData'][j].get('picked_qty')),
                                                 store_code=bin_qty_change.t_code,
                                                 creater=str(staff_name)
                                                 )
                cur_date = timezone.now().date()
                bin_stock = stockbin.objects.filter(openid=self.request.auth.openid,
                                                    bin_name=bin_qty_change.bin_name,
                                                    goods_code=bin_qty_change.goods_code,
                                                    ).aggregate(sum=Sum('goods_qty'))["sum"]
                cycle_qty = bin_stock - int(data['goodsData'][j].get('picked_qty'))
                cyclecount.objects.filter(openid=self.request.auth.openid,
                                          bin_name=bin_qty_change.bin_name,
                                          goods_code=bin_qty_change.goods_code,
                                          create_time__gte=cur_date).update(goods_qty=cycle_qty)
                if int(data['goodsData'][j].get('picked_qty')) == pick_qty_change.pick_qty:
                    goods_qty_change.onhand_stock = goods_qty_change.onhand_stock - int(
                        data['goodsData'][j].get('pick_qty'))
                    goods_qty_change.pick_stock = goods_qty_change.pick_stock - int(
                        data['goodsData'][j].get('picked_qty'))
                    goods_qty_change.picked_stock = goods_qty_change.picked_stock + int(
                        data['goodsData'][j].get('picked_qty'))
                    pick_qty_change.picked_qty = int(data['goodsData'][j].get('picked_qty'))
                    pick_qty_change.picking_status = 1
                    bin_qty_change.goods_qty = bin_qty_change.goods_qty - int(data['goodsData'][j].get('pick_qty'))
                    bin_qty_change.pick_qty = bin_qty_change.pick_qty - int(data['goodsData'][j].get('picked_qty'))
                    bin_qty_change.picked_qty = bin_qty_change.picked_qty + int(data['goodsData'][j].get('picked_qty'))
                    goods_qty_change.save()
                    pick_qty_change.save()
                    bin_qty_change.save()
                elif int(data['goodsData'][j].get('picked_qty')) < pick_qty_change.pick_qty:
                    goods_qty_change.onhand_stock = goods_qty_change.onhand_stock - int(
                        data['goodsData'][j].get('pick_qty'))
                    goods_qty_change.pick_stock = goods_qty_change.pick_stock - dn_detail.pick_qty
                    goods_qty_change.picked_stock = goods_qty_change.picked_stock + int(
                        data['goodsData'][j].get('picked_qty'))
                    goods_qty_change.can_order_stock = goods_qty_change.can_order_stock + (
                                int(pick_qty_change.pick_qty) - int(
                            data['goodsData'][j].get('pick_qty')))
                    pick_qty_change.picked_qty = int(data['goodsData'][j].get('picked_qty'))
                    pick_qty_change.picking_status = 1
                    bin_qty_change.goods_qty = bin_qty_change.goods_qty - pick_qty_change.pick_qty
                    bin_qty_change.pick_qty = bin_qty_change.pick_qty - pick_qty_change.pick_qty
                    bin_qty_change.picked_qty = bin_qty_change.picked_qty + int(data['goodsData'][j].get('picked_qty'))
                    goods_qty_change.save()
                    pick_qty_change.save()
                    bin_qty_change.save()
                dn_detail.picked_qty = dn_detail.picked_qty + int(data['goodsData'][j].get('picked_qty'))
                if dn_detail.pick_qty > 0:
                    dn_detail.pick_qty = 0
                if PickingListModel.objects.filter(openid=self.request.auth.openid, dn_code=str(data['dn_code']), picking_status=0).exists():
                    dn_detail.save()
                else:
                    qs.save()
                    dn_detail.dn_status = 4
                    dn_detail.save()
            _mark_picked_serials(self.request.auth.openid, qs, serials_by_goods)
            return Response({"Detail": "success"}, status=200)

class DnDispatchViewSet(viewsets.ModelViewSet):
    """
        create:
            Confirm Dispatch
    """
    pagination_class = MyPageNumberPagination
    filter_backends = [DjangoFilterBackend, OrderingFilter, ]
    ordering_fields = ['id', "create_time", "update_time", ]
    filter_class = DnListFilter

    def get_project(self):
        try:
            id = self.kwargs.get('pk')
            return id
        except:
            return None

    def get_queryset(self):
        id = self.get_project()
        if self.request.user:
            queryset = DnListModel.objects.filter(openid=self.request.auth.openid, id=id, is_delete=False)
            if self.action == 'create':
                queryset = queryset.select_for_update()
            return queryset
        else:
            return DnListModel.objects.none()

    def get_serializer_class(self):
        if self.action in ['create']:
            return serializers.DNListUpdateSerializer
        else:
            return self.http_method_not_allowed(request=self.request)

    @transaction.atomic
    def create(self, request, pk):
        qs = self.get_object()
        if qs.dn_status != 4:
            raise APIException({"detail": "This DN Status Not Picked"})
        else:
            command, replay = _agent_preview(request, 'outbound.dispatch', resource_id=pk)
            if replay is not None:
                return Response(replay)
            _require_all_picked_serials(self.request.auth.openid, qs)
            data = self.request.data
            staging_bin = data.get('staging_bin')
            if not staging_bin:
                raise APIException({"detail": "Please select an outbound staging location"})
            requested_dn_code = str(data.get('dn_code') or '').strip()
            if requested_dn_code and requested_dn_code != str(qs.dn_code):
                raise APIException({"detail": "DN code does not match the selected delivery note"})
            dn_code = str(qs.dn_code)
            driver_name = str(data.get('driver') or '').strip()
            if not driver_name:
                raise APIException({"detail": "Please select a driver"})
            operator = staff.objects.filter(
                openid=self.request.auth.openid,
                id=self.request.META.get('HTTP_OPERATOR'),
                is_delete=False,
            ).first()
            if operator is None:
                raise APIException({"detail": "Operator does not exist"})
            if driverdispatch.objects.filter(
                openid=self.request.auth.openid,
                dn_code=dn_code,
            ).exists():
                raise APIException({"detail": "This DN has already been dispatched"})
            driver = driverlist.objects.filter(
                openid=self.request.auth.openid,
                driver_name=driver_name,
                is_delete=False,
            ).first()
            if driver is not None:
                dn_detail = list(DnDetailModel.objects.select_for_update().filter(
                    openid=self.request.auth.openid,
                    dn_code=dn_code,
                    dn_status=4,
                    customer=qs.customer,
                ))
                pick_qty_change = list(PickingListModel.objects.select_for_update().filter(
                    openid=self.request.auth.openid,
                    dn_code=dn_code,
                ))
                if not dn_detail:
                    raise APIException({"detail": "No picked DN detail exists for this delivery note"})
                if not pick_qty_change:
                    raise APIException({"detail": "No picking record exists for this delivery note"})

                _ensure_outbound_transport(request, qs, driver_name)

                stock_by_goods = {}
                picked_by_goods = {}
                for detail in dn_detail:
                    picked_qty = int(detail.picked_qty or 0)
                    if picked_qty < 0:
                        raise APIException({"detail": "Picked quantity cannot be negative"})
                    picked_by_goods[detail.goods_code] = picked_by_goods.get(detail.goods_code, 0) + picked_qty
                for goods_code, picked_qty in picked_by_goods.items():
                    goods_qty_change = stocklist.objects.select_for_update().filter(
                        openid=self.request.auth.openid,
                        goods_code=goods_code,
                    ).first()
                    if goods_qty_change is None:
                        raise APIException({"detail": "Stock record does not exist for %s" % goods_code})
                    if int(goods_qty_change.goods_qty or 0) < picked_qty or int(goods_qty_change.picked_stock or 0) < picked_qty:
                        raise APIException({"detail": "Stock is insufficient for %s" % goods_code})
                    stock_by_goods[goods_code] = goods_qty_change
                for picking in pick_qty_change:
                    picked_qty = int(picking.picked_qty or 0)
                    if picked_qty < 0:
                        raise APIException({"detail": "Picked quantity cannot be negative"})
                    bin_qty_change = stockbin.objects.select_for_update().filter(
                        openid=self.request.auth.openid,
                        goods_code=picking.goods_code,
                        bin_name=picking.bin_name,
                        t_code=picking.t_code,
                    ).first()
                    if bin_qty_change is None:
                        raise APIException({"detail": "Picking bin record does not exist for %s" % picking.goods_code})
                    if int(bin_qty_change.picked_qty or 0) < picked_qty:
                        raise APIException({"detail": "Picked bin quantity is insufficient for %s" % picking.goods_code})
                try:
                    reserve_staging_slot(
                        self.request.auth.openid,
                        StagingAssignment.OUTBOUND,
                        qs.dn_code,
                        staging_bin,
                        sum(int(detail.picked_qty or 0) for detail in dn_detail),
                        '',
                        request.META.get('HTTP_OPERATOR', ''),
                    )
                except StagingError as exc:
                    raise APIException({"detail": str(exc)})
                qs.dn_status = 5
                for detail in dn_detail:
                    goods_qty_change = stock_by_goods[detail.goods_code]
                    goods_qty_change.goods_qty = goods_qty_change.goods_qty - detail.picked_qty
                    goods_qty_change.picked_stock = goods_qty_change.picked_stock - detail.picked_qty
                    detail.dn_status = 5
                    detail.intransit_qty = detail.picked_qty
                    detail.save()
                    goods_qty_change.save()
                    if goods_qty_change.goods_qty == 0 and goods_qty_change.back_order_stock == 0:
                        goods_qty_change.delete()
                for picking in pick_qty_change:
                    bin_qty_change = stockbin.objects.filter(
                        openid=self.request.auth.openid,
                        goods_code=picking.goods_code,
                        bin_name=picking.bin_name,
                        t_code=picking.t_code,
                    ).first()
                    bin_qty_change.picked_qty = bin_qty_change.picked_qty - picking.picked_qty
                    bin_qty_change.save()
                    bin_stock_check = stockbin.objects.filter(
                        openid=self.request.auth.openid,
                        goods_code=picking.goods_code,
                        bin_name=picking.bin_name,
                        t_code=picking.t_code,
                    ).first()
                    if bin_stock_check.goods_qty == 0 and bin_stock_check.pick_qty == 0 and bin_stock_check.picked_qty == 0:
                        bin_stock_check.delete()
                        if stockbin.objects.filter(openid=self.request.auth.openid,
                                                   bin_name=bin_stock_check.bin_name,
                                                   goods_qty__gt=0).exists() is False:
                            binset.objects.filter(openid=self.request.auth.openid,
                                                  bin_name=picking.bin_name).update(empty_label=True)
                driverdispatch.objects.create(openid=self.request.auth.openid,
                                              driver_name=driver.driver_name,
                                              dn_code=dn_code,
                                              staging_bin=str(staging_bin),
                                              contact=str(driver.contact or ''),
                                              creater=str(operator.staff_name))
                qs.save()
                occupy_staging_slot(self.request.auth.openid, StagingAssignment.OUTBOUND, qs.dn_code)
                _mark_outbound_transport_in_transit(qs)
                _mark_serials(
                    self.request.auth.openid,
                    qs.dn_code,
                    DnSerialAllocation.PICKED,
                    DnSerialAllocation.IN_TRANSIT,
                )
                result = {"detail": "success"}
                complete_preview(command, result)
                return Response(result, status=200)
            else:
                raise APIException({"detail": "Driver Does Not Exists"})

class DnPODViewSet(viewsets.ModelViewSet):
    """
        create:
            Confirm Dispatch
    """
    pagination_class = MyPageNumberPagination
    filter_backends = [DjangoFilterBackend, OrderingFilter, ]
    ordering_fields = ['id', "create_time", "update_time", ]
    filter_class = DnListFilter

    def get_project(self):
        try:
            id = self.kwargs.get('pk')
            return id
        except:
            return None

    def get_queryset(self):
        id = self.get_project()
        if self.request.user:
            return DnListModel.objects.filter(openid=self.request.auth.openid, id=id, is_delete=False)
        else:
            return DnListModel.objects.none()

    def get_serializer_class(self):
        if self.action in ['create']:
            return serializers.DNListUpdateSerializer
        else:
            return self.http_method_not_allowed(request=self.request)

    @transaction.atomic
    def create(self, request, pk):
        qs = self.get_object()
        if qs.dn_status != 5:
            raise APIException({"detail": "This DN Status Not Intran-Sit"})
        command, replay = _agent_preview(request, 'outbound.pod', resource_id=pk)
        if replay is not None:
            return Response(replay)
        data = self.request.data
        dn_code = str(data.get('dn_code') or qs.dn_code)
        if dn_code != str(qs.dn_code):
            raise APIException({"detail": "DN code does not match the selected delivery note"})
        raw_goods = data.get('goodsData') or []
        if not raw_goods:
            raise APIException({"detail": "Delivery details are required"})

        dn_detail = list(DnDetailModel.objects.select_for_update().filter(
            openid=self.request.auth.openid,
            dn_code=dn_code,
            dn_status=5,
            customer=qs.customer,
            is_delete=False,
        ))
        details_by_code = {str(item.goods_code): item for item in dn_detail}
        if len(details_by_code) != len(dn_detail):
            raise APIException({"detail": "Duplicate goods codes require a separate delivery line"})
        submitted_codes = set()
        updates = []
        for item in raw_goods:
            goods_code = str(item.get('goods_code') or '').strip()
            if not goods_code or goods_code in submitted_codes:
                raise APIException({"detail": "Each goods code must be submitted once"})
            if goods_code not in details_by_code:
                raise APIException({"detail": "Goods code does not belong to this delivery note: %s" % goods_code})
            submitted_codes.add(goods_code)
            try:
                delivery_actual_qty = int(item.get('intransit_qty'))
                delivery_damage_qty = int(item.get('delivery_damage_qty') or 0)
            except (TypeError, ValueError):
                raise APIException({"detail": "Delivery quantities must be integers"})
            if delivery_actual_qty < 0:
                raise APIException({"detail": "Delivery Actual QTY Must >= 0"})
            if delivery_damage_qty < 0 or delivery_damage_qty > delivery_actual_qty:
                raise APIException({"detail": "Delivery Damage QTY must be between 0 and actual quantity"})
            expected_qty = int(details_by_code[goods_code].intransit_qty or 0)
            delivery_note = str(item.get('delivery_note') or '').strip()
            if (delivery_actual_qty != expected_qty or delivery_damage_qty > 0) and not delivery_note:
                raise APIException({"detail": "An exception note is required for %s" % goods_code})
            updates.append((details_by_code[goods_code], delivery_actual_qty, delivery_damage_qty, expected_qty, delivery_note))

        missing_codes = set(details_by_code) - submitted_codes
        if missing_codes:
            raise APIException({"detail": "Missing delivery details for: %s" % ', '.join(sorted(missing_codes))})

        for goods_detail, actual_qty, damage_qty, expected_qty, note in updates:
            goods_detail.delivery_actual_qty = actual_qty
            goods_detail.delivery_shortage_qty = max(expected_qty - actual_qty, 0)
            goods_detail.delivery_more_qty = max(actual_qty - expected_qty, 0)
            goods_detail.delivery_damage_qty = damage_qty
            goods_detail.delivery_note = note
            goods_detail.intransit_qty = 0
            goods_detail.dn_status = 6
            goods_detail.save()
        qs.dn_status = 6
        qs.save()
        _complete_outbound_transport(request, qs)
        release_staging_slot(self.request.auth.openid, StagingAssignment.OUTBOUND, qs.dn_code)
        _mark_shipped_serials(self.request.auth.openid, qs.dn_code)
        result = {"detail": "success"}
        complete_preview(command, result)
        return Response(result, status=200)


class DnCancelInTransitViewSet(viewsets.ModelViewSet):
    """Cancel an in-transit delivery note and release its outbound staging slot."""

    def get_project(self):
        return self.kwargs.get('pk')

    def get_queryset(self):
        queryset = DnListModel.objects.filter(
            openid=self.request.auth.openid,
            id=self.get_project(),
            is_delete=False,
        )
        if self.action == 'create':
            queryset = queryset.select_for_update()
        return queryset

    def get_serializer_class(self):
        if self.action == 'create':
            return serializers.DNListUpdateSerializer
        return self.http_method_not_allowed(request=self.request)

    @transaction.atomic
    def create(self, request, pk):
        if not getattr(request.auth, 'is_admin', False):
            raise PermissionDenied('Only administrators can cancel an in-transit delivery note')

        qs = self.get_object()
        if qs.dn_status != 5:
            raise APIException({'detail': 'Only in-transit delivery notes can be canceled'})
        command, replay = _agent_preview(request, 'outbound.cancel_intransit', resource_id=pk)
        if replay is not None:
            return Response(replay)

        note = str(request.data.get('cancellation_note') or '').strip()
        if not note:
            raise APIException({'detail': 'A cancellation reason is required'})
        if len(note) > 2000:
            raise APIException({'detail': 'Cancellation reason cannot exceed 2000 characters'})

        now = timezone.now()
        qs.dn_status = 7
        qs.cancellation_note = note
        qs.canceled_by = str(getattr(request.auth, 'staff_name', '') or request.META.get('HTTP_OPERATOR', ''))
        qs.canceled_at = now
        qs.save(update_fields=['dn_status', 'cancellation_note', 'canceled_by', 'canceled_at', 'update_time'])
        canceled_details = list(DnDetailModel.objects.select_for_update().filter(
            openid=request.auth.openid,
            dn_code=qs.dn_code,
            dn_status=5,
            is_delete=False,
        ))
        canceled_quantities = {}
        for detail in canceled_details:
            canceled_qty = max(int(detail.intransit_qty or 0), 0)
            canceled_quantities[detail.goods_code] = canceled_qty
            detail.cancelled_qty = canceled_qty
            detail.intransit_qty = 0
            detail.dn_status = 7
            detail.save(update_fields=['cancelled_qty', 'intransit_qty', 'dn_status', 'update_time'])
        _mark_serials(
            request.auth.openid,
            qs.dn_code,
            DnSerialAllocation.IN_TRANSIT,
            DnSerialAllocation.RELEASED,
        )
        _cancel_outbound_transport(request, qs, note)
        released = release_staging_slot(request.auth.openid, StagingAssignment.OUTBOUND, qs.dn_code)
        result = {
            'detail': 'success',
            'released': released,
            'cancelled_qty': canceled_quantities,
            'inventory_action': 'Return goods must be processed through Receiving, QC and Putaway.',
        }
        complete_preview(command, result)
        return Response(result, status=200)

class FileListDownloadView(viewsets.ModelViewSet):
    renderer_classes = (FileListRenderCN, ) + tuple(api_settings.DEFAULT_RENDERER_CLASSES)
    filter_backends = [DjangoFilterBackend, OrderingFilter, ]
    ordering_fields = ['id', "create_time", "update_time", ]
    filter_class = DnListFilter

    def get_project(self):
        try:
            id = self.kwargs.get('pk')
            return id
        except:
            return None

    def get_queryset(self):
        id = self.get_project()
        if self.request.user:
            empty_qs = DnListModel.objects.filter(
                Q(openid=self.request.auth.openid, dn_status=1, is_delete=False) & Q(customer=''))
            cur_date = timezone.now()
            date_check = relativedelta(day=1)
            if len(empty_qs) > 0:
                for i in range(len(empty_qs)):
                    if empty_qs[i].create_time <= cur_date - date_check:
                        empty_qs[i].delete()
            if id is None:
                return DnListModel.objects.filter(
                    Q(openid=self.request.auth.openid, is_delete=False) & ~Q(customer=''))
            else:
                return DnListModel.objects.filter(
                    Q(openid=self.request.auth.openid, id=id, is_delete=False) & ~Q(customer=''))
        else:
            return DnListModel.objects.none()

    def get_serializer_class(self):
        if self.action in ['list']:
            return serializers.FileListRenderSerializer
        else:
            return self.http_method_not_allowed(request=self.request)

    def get_lang(self, data):
        lang = self.request.META.get('HTTP_LANGUAGE')
        if lang:
            if lang == 'zh-hans':
                return FileListRenderCN().render(data)
            else:
                return FileListRenderEN().render(data)
        else:
            return FileListRenderEN().render(data)

    def list(self, request, *args, **kwargs):
        from datetime import datetime
        dt = datetime.now()
        data = (
            FileListRenderSerializer(instance).data
            for instance in self.filter_queryset(self.get_queryset())
        )
        renderer = self.get_lang(data)
        response = StreamingHttpResponse(
            renderer,
            content_type="text/csv"
        )
        response['Content-Disposition'] = "attachment; filename='dnlist_{}.csv'".format(str(dt.strftime('%Y%m%d%H%M%S%f')))
        return response

class FileDetailDownloadView(viewsets.ModelViewSet):
    renderer_classes = (FileDetailRenderCN, ) + tuple(api_settings.DEFAULT_RENDERER_CLASSES)
    filter_backends = [DjangoFilterBackend, OrderingFilter, ]
    ordering_fields = ['id', "create_time", "update_time", ]
    filter_class = DnDetailFilter

    def get_project(self):
        try:
            id = self.kwargs.get('pk')
            return id
        except:
            return None

    def get_queryset(self):
        id = self.get_project()
        if self.request.user:
            if id is None:
                return DnDetailModel.objects.filter(openid=self.request.auth.openid, is_delete=False)
            else:
                return DnDetailModel.objects.filter(openid=self.request.auth.openid, id=id, is_delete=False)
        else:
            return DnDetailModel.objects.none()

    def get_serializer_class(self):
        if self.action in ['list']:
            return serializers.FileDetailRenderSerializer
        else:
            return self.http_method_not_allowed(request=self.request)

    def get_lang(self, data):
        lang = self.request.META.get('HTTP_LANGUAGE')
        if lang:
            if lang == 'zh-hans':
                return FileDetailRenderCN().render(data)
            else:
                return FileDetailRenderEN().render(data)
        else:
            return FileDetailRenderEN().render(data)

    def list(self, request, *args, **kwargs):
        from datetime import datetime
        dt = datetime.now()
        data = (
            FileDetailRenderSerializer(instance).data
            for instance in self.filter_queryset(self.get_queryset())
        )
        renderer = self.get_lang(data)
        response = StreamingHttpResponse(
            renderer,
            content_type="text/csv"
        )
        response['Content-Disposition'] = "attachment; filename='dndetail_{}.csv'".format(str(dt.strftime('%Y%m%d%H%M%S%f')))
        return response
