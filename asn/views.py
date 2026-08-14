from rest_framework import serializers as drf_serializers
from rest_framework import viewsets
from .models import AsnEventModel, AsnListModel, AsnDetailModel
from . import serializers
from .page import MyPageNumberPaginationASNList
from utils.page import MyPageNumberPagination
from utils.datasolve import sumOfList, transportation_calculate
from utils.fbmsg import FBMsg
from utils.md5 import Md5
from rest_framework.filters import OrderingFilter
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.response import Response
from rest_framework.views import APIView
from .filter import AsnListFilter, AsnDetailFilter
from rest_framework.exceptions import APIException
from supplier.models import ListModel as supplier
from warehouse.models import ListModel as warehouse
from goods.models import ListModel as goods
from payment.models import TransportationFeeListModel as transportation
from stock.models import StockListModel as stocklist
from stock.models import StockBinModel as stockbin
from binset.models import ListModel as binset
from scanner.models import ListModel as scanner
from cyclecount.models import QTYRecorder as qtychangerecorder
from cyclecount.models import CyclecountModeDayModel as cyclecount
from django.db.models import Q
from django.db.models import Sum
from django.db import transaction
from .serializers import FileListRenderSerializer, FileDetailRenderSerializer
from django.http import StreamingHttpResponse
from django.utils import timezone
from .files import FileListRenderCN, FileListRenderEN, FileDetailRenderCN, FileDetailRenderEN
from rest_framework.settings import api_settings
from dateutil.relativedelta import relativedelta
from staff.models import ListModel as staff
from driver.models import ListModel as driverlist
from asnserial.models import (
    ACCEPT_FOR_PUTAWAY,
    HOLD_QUARANTINE,
    LEGACY_ACCEPT_EXCEPTION,
    AsnSerialRecord,
    PackListDocument,
    PUTAWAY_APPROVED_RESOLUTIONS,
    REJECT_RETURN,
)
from asnserial.agent import complete_preview, consume_preview, request_payload
from staging.models import StagingAssignment
from staging.services import (
    StagingError,
    occupy_staging_slot,
    release_staging_slot,
    reserve_staging_slots,
)
from receiving.services import assert_legacy_asn_putaway_allowed
from .services import inbound_package_quantity


def _operator_name(request, required=False):
    operator_id = request.META.get('HTTP_OPERATOR', '')
    operator = staff.objects.filter(
        openid=request.auth.openid,
        id=operator_id,
        is_delete=False,
    ).first() if operator_id else None
    if required and operator is None:
        raise APIException({'detail': 'Operator does not exist'})
    return operator.staff_name if operator else str(operator_id or '')


def _request_datetime(value, label):
    if value in (None, ''):
        return None
    try:
        parsed = drf_serializers.DateTimeField().to_internal_value(value)
    except Exception as exc:
        raise APIException({'detail': '%s is invalid: %s' % (label, exc)})
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


def _asn_response(request, asn):
    return serializers.ASNListGetSerializer(
        asn,
        context={'request': request},
    ).data

class AsnListViewSet(viewsets.ModelViewSet):
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
    pagination_class = MyPageNumberPaginationASNList
    filter_backends = [DjangoFilterBackend, OrderingFilter, ]
    ordering_fields = ['id', "create_time", "update_time", ]
    filter_class = AsnListFilter

    def get_project(self):
        try:
            id = self.kwargs.get('pk')
            return id
        except:
            return None

    def get_queryset(self):
        id = self.get_project()
        if self.request.user:
            empty_qs = AsnListModel.objects.filter(Q(openid=self.request.auth.openid, asn_status=1, is_delete=False) & Q(supplier=''))
            cur_date = timezone.now()
            date_check = relativedelta(day=1)
            if len(empty_qs) > 0:
                for i in range(len(empty_qs)):
                    if empty_qs[i].create_time <= cur_date - date_check:
                        empty_qs[i].delete()
            if id is None:
                return AsnListModel.objects.filter(Q(openid=self.request.auth.openid, is_delete=False) & ~Q(supplier=''))
            else:
                return AsnListModel.objects.filter(Q(openid=self.request.auth.openid, id=id, is_delete=False) & ~Q(supplier=''))
        else:
            return AsnListModel.objects.none()

    def get_serializer_class(self):
        if self.action in ['list', 'retrieve', 'destroy']:
            return serializers.ASNListGetSerializer
        elif self.action in ['create']:
            return serializers.ASNListPostSerializer
        elif self.action in ['update']:
            return serializers.ASNListUpdateSerializer
        elif self.action in ['partial_update']:
            return serializers.ASNListPartialUpdateSerializer
        else:
            return self.http_method_not_allowed(request=self.request)

    def notice_lang(self):
        return FBMsg(self.request.META.get('HTTP_LANGUAGE'))

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        data = self.request.data
        command, replay = consume_preview(
            request,
            'asn.create',
            request_payload(request),
        )
        if replay is not None:
            return Response(replay)
        data['openid'] = self.request.auth.openid
        container_tracking = str(data.get('container_tracking') or '').strip()
        if container_tracking:
            existing = AsnListModel.objects.filter(
                openid=self.request.auth.openid,
                container_tracking__iexact=container_tracking,
                is_delete=False,
            ).first()
            if existing:
                return Response({
                    'detail': 'An active ASN already exists for this container / tracking reference',
                    'asn_id': existing.id,
                    'asn_code': existing.asn_code,
                }, status=409)
        custom_asn = self.request.GET.get('custom_asn', '')
        if custom_asn:
            data['asn_code'] = custom_asn
        else:
            qs_set = AsnListModel.objects.filter(openid=self.request.auth.openid)
            order_day =str(timezone.now().strftime('%Y%m%d'))
            if len(qs_set) > 0:
                asn_last_code = qs_set.order_by('-id').first().asn_code
                if str(asn_last_code[3:11]) == order_day:
                    order_create_no = str(int(asn_last_code[11:]) + 1)
                    data['asn_code'] = 'ASN' + order_day + order_create_no
                else:
                    data['asn_code'] = 'ASN' + order_day + '1'
            else:
                data['asn_code'] = 'ASN' + order_day + '1'
        data['bar_code'] = Md5.md5(data['asn_code'])
        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        scanner.objects.create(openid=self.request.auth.openid, mode="ASN", code=data['asn_code'], bar_code=data['bar_code'])
        headers = self.get_success_headers(serializer.data)
        result = serializer.data
        complete_preview(command, result)
        return Response(result, status=200, headers=headers)

    def destroy(self, request, pk):
        qs = self.get_object()
        if qs.openid != self.request.auth.openid:
            raise APIException({"detail": "Cannot delete data which not yours"})
        else:
            if qs.asn_status == 1:
                release_staging_slot(self.request.auth.openid, StagingAssignment.INBOUND, qs.asn_code)
                qs.is_delete = True
                asn_detail_list = AsnDetailModel.objects.filter(openid=self.request.auth.openid, asn_code=qs.asn_code,
                                              asn_status=1, is_delete=False)
                for i in range(len(asn_detail_list)):
                    goods_qty_change = stocklist.objects.filter(openid=self.request.auth.openid,
                                                                goods_code=str(asn_detail_list[i].goods_code)).first()
                    goods_qty_change.goods_qty = goods_qty_change.goods_qty - int(asn_detail_list[i].goods_qty)
                    goods_qty_change.asn_stock = goods_qty_change.asn_stock - int(asn_detail_list[i].goods_qty)
                    goods_qty_change.save()
                asn_detail_list.update(is_delete=True)
                qs.save()
                serializer = self.get_serializer(qs, many=False)
                headers = self.get_success_headers(serializer.data)
                return Response(serializer.data, status=200, headers=headers)
            else:
                raise APIException({"detail": "This ASN Status Is Not '1'"})


class AsnEtaUpdateView(APIView):
    """Update a customer ETA without changing inventory or receiving status."""

    @transaction.atomic
    def post(self, request, pk):
        asn = AsnListModel.objects.select_for_update().filter(
            openid=request.auth.openid,
            id=pk,
            is_delete=False,
        ).first()
        if asn is None:
            raise APIException({'detail': 'ASN does not exist'})
        if int(asn.asn_status or 0) >= 5:
            raise APIException({'detail': 'Completed ASN ETA cannot be changed'})
        command, replay = consume_preview(
            request,
            'asn.eta',
            request_payload(request),
            resource_id=str(pk),
            asn_code=asn.asn_code,
        )
        if replay is not None:
            return Response(replay)
        new_eta = _request_datetime(request.data.get('expected_arrival_at'), 'ETA')
        old_eta = asn.expected_arrival_at
        asn.expected_arrival_at = new_eta
        asn.eta_received_at = timezone.now()
        asn.eta_received_by = _operator_name(request)
        asn.eta_source = str(request.data.get('source') or 'CUSTOMER').strip()[:64]
        asn.save(update_fields=[
            'expected_arrival_at',
            'eta_received_at',
            'eta_received_by',
            'eta_source',
            'update_time',
        ])
        AsnEventModel.objects.create(
            openid=request.auth.openid,
            asn_code=asn.asn_code,
            event_type=AsnEventModel.ETA_UPDATED,
            old_expected_arrival_at=old_eta,
            new_expected_arrival_at=new_eta,
            operator=_operator_name(request),
            source=asn.eta_source,
            note=str(request.data.get('note') or ''),
        )
        result = {'detail': 'ETA updated', 'asn': _asn_response(request, asn)}
        complete_preview(command, result)
        return Response(result)


class AsnArrivalConfirmView(APIView):
    """Record physical arrival separately from the customer ETA."""

    @transaction.atomic
    def post(self, request, pk):
        asn = AsnListModel.objects.select_for_update().filter(
            openid=request.auth.openid,
            id=pk,
            is_delete=False,
        ).first()
        if asn is None:
            raise APIException({'detail': 'ASN does not exist'})
        if int(asn.asn_status or 0) != 1:
            raise APIException({'detail': 'Only Pre Arrival ASN can be marked arrived'})
        command, replay = consume_preview(
            request,
            'asn.arrival',
            request_payload(request),
            resource_id=str(pk),
            asn_code=asn.asn_code,
        )
        if replay is not None:
            return Response(replay)
        actual_arrival = _request_datetime(request.data.get('actual_arrival_at'), 'Actual arrival time') or timezone.now()
        asn.actual_arrival_at = actual_arrival
        asn.arrival_confirmed_by = _operator_name(request)
        asn.save(update_fields=['actual_arrival_at', 'arrival_confirmed_by', 'update_time'])
        AsnEventModel.objects.create(
            openid=request.auth.openid,
            asn_code=asn.asn_code,
            event_type=AsnEventModel.ARRIVAL_CONFIRMED,
            actual_arrival_at=actual_arrival,
            operator=_operator_name(request),
            source=str(request.data.get('source') or 'WAREHOUSE').strip()[:64],
            note=str(request.data.get('note') or ''),
        )
        result = {'detail': 'Arrival confirmed', 'asn': _asn_response(request, asn)}
        complete_preview(command, result)
        return Response(result)


class AsnStagingReserveView(APIView):
    """Reserve staging capacity before arrival without occupying it."""

    @transaction.atomic
    def post(self, request, pk):
        asn = AsnListModel.objects.select_for_update().filter(
            openid=request.auth.openid,
            id=pk,
            is_delete=False,
        ).first()
        if asn is None:
            raise APIException({'detail': 'ASN does not exist'})
        if int(asn.asn_status or 0) != 1:
            raise APIException({'detail': 'Staging can only be reserved before unloading'})
        command, replay = consume_preview(
            request,
            'asn.reserve_staging',
            request_payload(request),
            resource_id=str(pk),
            asn_code=asn.asn_code,
        )
        if replay is not None:
            return Response(replay)
        quantity, quantity_source = inbound_package_quantity(asn)
        staging_bins = request.data.get('staging_bins') or []
        if not staging_bins and request.data.get('staging_bin'):
            staging_bins = [request.data.get('staging_bin')]
        try:
            reserve_staging_slots(
                request.auth.openid,
                StagingAssignment.INBOUND,
                asn.asn_code,
                staging_bins,
                quantity,
                '',
                _operator_name(request),
            )
        except StagingError as exc:
            raise APIException({'detail': str(exc)})
        AsnEventModel.objects.create(
            openid=request.auth.openid,
            asn_code=asn.asn_code,
            event_type=AsnEventModel.STAGING_RESERVED,
            operator=_operator_name(request),
            source='WAREHOUSE',
            note='Reserved %s load units from %s' % (quantity, quantity_source),
        )
        result = {
            'detail': 'Staging capacity reserved',
            'package_qty': quantity,
            'package_qty_source': quantity_source,
            'asn': _asn_response(request, asn),
        }
        complete_preview(command, result)
        return Response(result)


class AsnEventListView(APIView):
    def get(self, request):
        asn_code = str(request.query_params.get('asn_code') or '').strip()
        if not asn_code:
            raise APIException({'detail': 'ASN Code is required'})
        events = AsnEventModel.objects.filter(openid=request.auth.openid, asn_code=asn_code)
        return Response({
            'count': events.count(),
            'results': [
                {
                    'id': event.id,
                    'event_type': event.event_type,
                    'old_expected_arrival_at': event.old_expected_arrival_at,
                    'new_expected_arrival_at': event.new_expected_arrival_at,
                    'actual_arrival_at': event.actual_arrival_at,
                    'operator': event.operator,
                    'source': event.source,
                    'note': event.note,
                    'event_time': event.event_time,
                }
                for event in events
            ],
        })


class AsnCancelView(APIView):
    """Cancel a pre-delivery or pre-unload ASN without leaving stock residue."""

    @transaction.atomic
    def post(self, request, pk):
        asn = AsnListModel.objects.select_for_update().filter(
            openid=request.auth.openid,
            id=pk,
            is_delete=False,
        ).first()
        if asn is None:
            raise APIException({"detail": "ASN does not exist"})
        if asn.asn_status not in (1, 2):
            raise APIException({"detail": "Only ASN Status 1 or 2 can be cancelled"})

        details = list(AsnDetailModel.objects.select_for_update().filter(
            openid=request.auth.openid,
            asn_code=asn.asn_code,
            is_delete=False,
        ))
        for detail in details:
            stock = stocklist.objects.select_for_update().filter(
                openid=request.auth.openid,
                goods_code=str(detail.goods_code),
            ).first()
            if stock is None:
                raise APIException({"detail": "Stock record does not exist for %s" % detail.goods_code})
            quantity = int(detail.goods_qty)
            if asn.asn_status == 1:
                stock.asn_stock = max(0, stock.asn_stock - quantity)
            else:
                stock.pre_load_stock = max(0, stock.pre_load_stock - quantity)
            stock.goods_qty = max(0, stock.goods_qty - quantity)
            stock.save()

        if asn.asn_status in (1, 2):
            release_staging_slot(request.auth.openid, StagingAssignment.INBOUND, asn.asn_code)

        # Serial records have no soft-delete field in the current schema. They
        # are scoped to the cancelled ASN and must not remain searchable.
        from asnserial.models import AsnSerialRecord
        serial_deleted, _ = AsnSerialRecord.objects.filter(
            openid=request.auth.openid,
            asn_code=asn.asn_code,
        ).delete()
        detail_count = len(details)
        AsnDetailModel.objects.filter(
            openid=request.auth.openid,
            asn_code=asn.asn_code,
            is_delete=False,
        ).update(is_delete=True)
        asn.is_delete = True
        asn.save()
        return Response({
            "detail": "ASN cancelled",
            "asn_code": asn.asn_code,
            "detail_count": detail_count,
            "serial_deleted": serial_deleted,
        }, status=200)


class AsnCleanupCancelledSerialsView(APIView):
    """Remove serial records left by the legacy soft-delete path."""

    @transaction.atomic
    def post(self, request):
        asn_codes = request.data.get('asn_codes') or []
        if not isinstance(asn_codes, list) or not asn_codes:
            raise APIException({"detail": "asn_codes must be a non-empty list"})
        if len(asn_codes) > 100:
            raise APIException({"detail": "A maximum of 100 ASN codes can be cleaned per request"})

        codes = [str(code).strip() for code in asn_codes if str(code).strip()]
        deleted_orders = set(AsnListModel.objects.filter(
            openid=request.auth.openid,
            asn_code__in=codes,
            is_delete=True,
        ).values_list('asn_code', flat=True))
        live_orders = set(AsnListModel.objects.filter(
            openid=request.auth.openid,
            asn_code__in=codes,
            is_delete=False,
        ).values_list('asn_code', flat=True))
        blocked = sorted(deleted_orders & live_orders)
        if blocked:
            raise APIException({"detail": "Cannot clean codes that also have an active ASN", "asn_codes": blocked})

        eligible = sorted(deleted_orders - live_orders)
        serial_deleted, _ = AsnSerialRecord.objects.filter(
            openid=request.auth.openid,
            asn_code__in=eligible,
        ).delete()
        return Response({
            "detail": "Cancelled ASN serial records cleaned",
            "asn_codes": eligible,
            "serial_deleted": serial_deleted,
            "not_found": sorted(set(codes) - set(eligible)),
        }, status=200)

class AsnDetailViewSet(viewsets.ModelViewSet):
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
    filter_class = AsnDetailFilter

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
                return AsnDetailModel.objects.filter(openid=self.request.auth.openid, is_delete=False)
            else:
                return AsnDetailModel.objects.filter(openid=self.request.auth.openid, id=id, is_delete=False)
        else:
            return AsnDetailModel.objects.none()

    def get_serializer_class(self):
        if self.action in ['list', 'retrieve']:
            return serializers.ASNDetailGetSerializer
        elif self.action in ['create']:
            return serializers.ASNDetailPostSerializer
        elif self.action in ['update']:
            return serializers.ASNDetailUpdateSerializer
        else:
            return self.http_method_not_allowed(request=self.request)

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        data = self.request.data
        command, replay = consume_preview(
            request,
            'asn.detail.create',
            request_payload(request),
            asn_code=str(data.get('asn_code') or '').strip(),
        )
        if replay is not None:
            return Response(replay)
        if AsnListModel.objects.filter(openid=self.request.auth.openid, asn_code=str(data['asn_code']), is_delete=False).exists():
            if supplier.objects.filter(openid=self.request.auth.openid, supplier_name=str(data['supplier']), is_delete=False).exists():
                staff_name = _operator_name(self.request, required=True)
                for i in range(len(data['goods_code'])):
                    check_data = {
                        'openid': self.request.auth.openid,
                        'asn_code': str(data['asn_code']),
                        'supplier': str(data['supplier']),
                        'goods_code': str(data['goods_code'][i]),
                        'goods_qty': int(data['goods_qty'][i]),
                        'creater': str(staff_name)
                    }
                    serializer = self.get_serializer(data=check_data)
                    serializer.is_valid(raise_exception=True)
                post_data_list = []
                weight_list = []
                volume_list = []
                cost_list = []
                for j in range(len(data['goods_code'])):
                    goods_detail = goods.objects.filter(openid=self.request.auth.openid,
                                                        goods_code=str(data['goods_code'][j]),
                                                        is_delete=False).first()
                    goods_weight = round(goods_detail.goods_weight * int(data['goods_qty'][j]) / 1000, 4)
                    goods_volume = round(goods_detail.unit_volume * int(data['goods_qty'][j]), 4)
                    goods_cost = round(goods_detail.goods_cost * int(data['goods_qty'][j]), 2)
                    if stocklist.objects.filter(openid=self.request.auth.openid, goods_code=str(data['goods_code'][j])).exists():
                        goods_qty_change = stocklist.objects.filter(openid=self.request.auth.openid,
                                                 goods_code=str(data['goods_code'][j])).first()
                        goods_qty_change.goods_qty = goods_qty_change.goods_qty + int(data['goods_qty'][j])
                        goods_qty_change.asn_stock = goods_qty_change.asn_stock + int(data['goods_qty'][j])
                        goods_qty_change.save()
                    else:
                        stocklist.objects.create(openid=self.request.auth.openid,
                                                 goods_code=str(data['goods_code'][j]),
                                                 goods_desc=goods_detail.goods_desc,
                                                 goods_qty=int(data['goods_qty'][j]),
                                                 asn_stock=int(data['goods_qty'][j]))
                    post_data = AsnDetailModel(openid=self.request.auth.openid,
                                               asn_code=str(data['asn_code']),
                                               supplier=str(data['supplier']),
                                               goods_code=str(data['goods_code'][j]),
                                               goods_desc=str(goods_detail.goods_desc),
                                               goods_qty=int(data['goods_qty'][j]),
                                               goods_weight=goods_weight,
                                               goods_volume=goods_volume,
                                               goods_cost=goods_cost,
                                               creater=str(staff_name))
                    post_data_list.append(post_data)
                    weight_list.append(goods_weight)
                    volume_list.append(goods_volume)
                    cost_list.append(goods_cost)
                total_weight = sumOfList(weight_list, len(weight_list))
                total_volume = sumOfList(volume_list, len(volume_list))
                total_cost = sumOfList(cost_list, len(cost_list))
                supplier_city = supplier.objects.filter(openid=self.request.auth.openid,
                                                        supplier_name=str(data['supplier']),
                                                        is_delete=False).first().supplier_city
                warehouse_city = warehouse.objects.filter(openid=self.request.auth.openid).first().warehouse_city
                transportation_fee = transportation.objects.filter(
                    Q(openid=self.request.auth.openid, send_city__icontains=supplier_city, receiver_city__icontains=warehouse_city,
                      is_delete=False) | Q(openid='init_data', send_city__icontains=supplier_city, receiver_city__icontains=warehouse_city,
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
                AsnDetailModel.objects.bulk_create(post_data_list, batch_size=100)
                check_data = AsnDetailModel.objects.filter(openid=self.request.auth.openid, asn_code=data['asn_code'], is_delete=False)
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
                        AsnDetailModel.objects.create(openid=self.request.auth.openid,
                                                      asn_code=str(data['asn_code']),
                                                      supplier=str(data['supplier']),
                                                      goods_code=str(check_data[k].goods_code),
                                                      goods_desc=str(check_data[k].goods_desc),
                                                      goods_qty=sumOfList(combine_qty, len(combine_qty)),
                                                      goods_weight=sumOfList(conbine_weight, len(conbine_weight)),
                                                      goods_volume=sumOfList(conbine_volume, len(conbine_volume)),
                                                      goods_cost=sumOfList(conbine_cost, len(conbine_cost)),
                                                      creater=str(staff_name))
                AsnListModel.objects.filter(openid=self.request.auth.openid, asn_code=str(data['asn_code'])).update(
                    supplier=str(data['supplier']), total_weight=total_weight, total_volume=total_volume,
                    total_cost=total_cost, transportation_fee=transportation_res)
                result = {"detail": "success"}
                complete_preview(command, result)
                return Response(result, status=200)
            else:
                raise APIException({"detail": "Supplier does not exists"})
        else:
            raise APIException({"detail": "ASN Code does not exists"})

    def update(self, request, *args, **kwargs):
        data = self.request.data
        if AsnListModel.objects.filter(openid=self.request.auth.openid, asn_code=str(data['asn_code']),
                                       asn_status=1, is_delete=False).exists():
            if supplier.objects.filter(openid=self.request.auth.openid, supplier_name=str(data['supplier']),
                                       is_delete=False).exists():
                staff_name = _operator_name(self.request, required=True)
                for i in range(len(data['goods_code'])):
                    check_data = {
                        'openid': self.request.auth.openid,
                        'asn_code': str(data['asn_code']),
                        'supplier': str(data['supplier']),
                        'goods_code': str(data['goods_code'][i]),
                        'goods_qty': int(data['goods_qty'][i]),
                        'creater': str(staff_name)
                    }
                    serializer = self.get_serializer(data=check_data)
                    serializer.is_valid(raise_exception=True)
                asn_detail_list = AsnDetailModel.objects.filter(openid=self.request.auth.openid,
                                                                asn_code=str(data['asn_code']), is_delete=False)
                for v in range(len(asn_detail_list)):
                    goods_qty_change = stocklist.objects.filter(openid=self.request.auth.openid,
                                                                goods_code=str(asn_detail_list[v].goods_code)).first()
                    goods_qty_change.goods_qty = goods_qty_change.goods_qty - asn_detail_list[v].goods_qty
                    if goods_qty_change.goods_qty < 0:
                        goods_qty_change.goods_qty = 0
                    goods_qty_change.asn_stock = goods_qty_change.asn_stock - asn_detail_list[v].goods_qty
                    if goods_qty_change.asn_stock < 0:
                        goods_qty_change.asn_stock = 0
                    goods_qty_change.save()
                    asn_detail_list[v].is_delete = True
                    asn_detail_list[v].save()
                post_data_list = []
                weight_list = []
                volume_list = []
                for j in range(len(data['goods_code'])):
                    goods_detail = goods.objects.filter(openid=self.request.auth.openid,
                                                        goods_code=str(data['goods_code'][j]),
                                                        is_delete=False).first()
                    goods_weight = round(goods_detail.goods_weight * int(data['goods_qty'][j]) / 1000, 4)
                    goods_volume = round(goods_detail.unit_volume * int(data['goods_qty'][j]), 4)
                    goods_cost = round(goods_detail.goods_cost * int(data['goods_qty'][j]), 2)
                    if stocklist.objects.filter(openid=self.request.auth.openid, goods_code=str(data['goods_code'][j])).exists():
                        goods_qty_change = stocklist.objects.filter(openid=self.request.auth.openid,
                                                 goods_code=str(data['goods_code'][j])).first()
                        goods_qty_change.goods_qty = goods_qty_change.goods_qty + int(data['goods_qty'][j])
                        goods_qty_change.asn_stock = goods_qty_change.asn_stock + int(data['goods_qty'][j])
                        goods_qty_change.save()
                    else:
                        stocklist.objects.create(openid=self.request.auth.openid,
                                                 goods_code=str(data['goods_code'][j]),
                                                 goods_desc=goods_detail.goods_desc,
                                                 goods_qty=int(data['goods_qty'][j]),
                                                 asn_stock=int(data['goods_qty'][j]))
                    post_data = AsnDetailModel(openid=self.request.auth.openid,
                                               asn_code=str(data['asn_code']),
                                               supplier=str(data['supplier']),
                                               goods_code=str(data['goods_code'][j]),
                                               goods_desc=str(goods_detail.goods_desc),
                                               goods_qty=int(data['goods_qty'][j]),
                                               goods_weight=goods_weight,
                                               goods_volume=goods_volume,
                                               creater=str(staff_name))
                    post_data_list.append(post_data)
                    weight_list.append(goods_weight)
                    volume_list.append(goods_volume)
                total_weight = sumOfList(weight_list, len(weight_list))
                total_volume = sumOfList(volume_list, len(volume_list))
                supplier_city = supplier.objects.filter(openid=self.request.auth.openid,
                                                        supplier_name=str(data['supplier']),
                                                        is_delete=False).first().supplier_city
                warehouse_city = warehouse.objects.filter(openid=self.request.auth.openid).first().warehouse_city
                transportation_fee = transportation.objects.filter(
                    Q(openid=self.request.auth.openid, send_city__icontains=supplier_city,
                      receiver_city__icontains=warehouse_city,
                      is_delete=False) | Q(openid='init_data', send_city__icontains=supplier_city,
                                           receiver_city__icontains=warehouse_city,
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
                AsnDetailModel.objects.bulk_create(post_data_list, batch_size=100)
                check_data = AsnDetailModel.objects.filter(openid=self.request.auth.openid, asn_code=data['asn_code'], is_delete=False)
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
                        AsnDetailModel.objects.create(openid=self.request.auth.openid,
                                                      asn_code=str(data['asn_code']),
                                                      supplier=str(data['supplier']),
                                                      goods_code=str(check_data[k].goods_code),
                                                      goods_desc=str(check_data[k].goods_desc),
                                                      goods_qty=sumOfList(combine_qty, len(combine_qty)),
                                                      goods_weight=sumOfList(conbine_weight, len(conbine_weight)),
                                                      goods_volume=sumOfList(conbine_volume, len(conbine_volume)),
                                                      goods_cost=sumOfList(conbine_cost, len(conbine_cost)),
                                                      creater=str(staff_name))
                AsnListModel.objects.filter(openid=self.request.auth.openid, asn_code=str(data['asn_code'])).update(
                    supplier=str(data['supplier']), total_weight=total_weight, total_volume=total_volume,
                    transportation_fee=transportation_res)
                return Response({"detail": "success"}, status=200)
            else:
                raise APIException({"detail": "Supplier does not exists"})
        else:
            raise APIException({"detail": "This ASN Status Is Not 1"})

class AsnViewPrintViewSet(viewsets.ModelViewSet):
    """
        retrieve:
            Response a data list（get）
    """
    pagination_class = MyPageNumberPagination
    filter_backends = [DjangoFilterBackend, OrderingFilter, ]
    ordering_fields = ['id', "create_time", "update_time", ]
    filter_class = AsnListFilter

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
                return AsnListModel.objects.filter(openid=self.request.auth.openid, is_delete=False)
            else:
                return AsnListModel.objects.filter(openid=self.request.auth.openid, id=id, is_delete=False)
        else:
            return AsnListModel.objects.none()

    def get_serializer_class(self):
        if self.action in ['retrieve']:
            return serializers.ASNDetailGetSerializer
        else:
            return self.http_method_not_allowed(request=self.request)

    def retrieve(self, request, pk):
        qs = self.get_object()
        if qs.openid != self.request.auth.openid:
            raise APIException({"detail": "Cannot update data which not yours"})
        else:
            context = {}
            asn_detail_list = AsnDetailModel.objects.filter(openid=self.request.auth.openid,
                                                            asn_code=qs.asn_code,
                                                            is_delete=False)
            asn_detail = serializers.ASNDetailGetSerializer(asn_detail_list, many=True)
            supplier_detail = supplier.objects.filter(openid=self.request.auth.openid,
                                                            supplier_name=qs.supplier).first()
            warehouse_detail = warehouse.objects.filter(openid=self.request.auth.openid,).first()
            context['asn_detail'] = asn_detail.data
            context['supplier_detail'] = {
                "supplier_name": supplier_detail.supplier_name,
                "supplier_city": supplier_detail.supplier_city,
                "supplier_address": supplier_detail.supplier_address,
                "supplier_contact": supplier_detail.supplier_contact
            }
            context['warehouse_detail'] = {
                "warehouse_name": warehouse_detail.warehouse_name,
                "warehouse_city": warehouse_detail.warehouse_city,
                "warehouse_address": warehouse_detail.warehouse_address,
                "warehouse_contact": warehouse_detail.warehouse_contact
            }
        return Response(context, status=200)

class AsnPreLoadViewSet(viewsets.ModelViewSet):
    """
        retrieve:
            Response a data list（get）
    """
    pagination_class = MyPageNumberPagination
    filter_backends = [DjangoFilterBackend, OrderingFilter, ]
    ordering_fields = ['id', "create_time", "update_time", ]
    filter_class = AsnListFilter

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
                return AsnListModel.objects.filter(openid=self.request.auth.openid, is_delete=False)
            else:
                return AsnListModel.objects.filter(openid=self.request.auth.openid, id=id, is_delete=False)
        else:
            return AsnListModel.objects.none()

    def get_serializer_class(self):
        if self.action in ['create']:
            return serializers.ASNListPartialUpdateSerializer
        else:
            return self.http_method_not_allowed(request=self.request)

    @transaction.atomic
    def create(self, request, pk):
        qs = self.get_queryset().select_for_update().filter(pk=pk).first()
        if qs is None:
            raise APIException({"detail": "ASN does not exist"})
        if qs.openid != self.request.auth.openid:
            raise APIException({"detail": "Cannot delete data which not yours"})
        else:
            if qs.asn_status == 1:
                if AsnDetailModel.objects.filter(openid=self.request.auth.openid, asn_code=qs.asn_code,
                                                                asn_status=1, is_delete=False).exists():
                    if not qs.actual_arrival_at:
                        raise APIException({"detail": "Mark the ASN as arrived before starting unloading"})
                    unload_driver = str(
                        request.data.get('unload_driver') or request.data.get('driver') or ''
                    ).strip()
                    if not unload_driver:
                        raise APIException({"detail": "Select an unloading driver before starting unloading"})
                    if not driverlist.objects.filter(
                        openid=self.request.auth.openid,
                        driver_name=unload_driver,
                        is_delete=False,
                    ).exists():
                        raise APIException({"detail": "Selected unloading driver does not exist"})
                    asn_detail_list = AsnDetailModel.objects.select_for_update().filter(openid=self.request.auth.openid, asn_code=qs.asn_code,
                                                                    asn_status=1, is_delete=False)
                    quantity, _ = inbound_package_quantity(qs)
                    staging_bins = request.data.get('staging_bins')
                    if not staging_bins:
                        staging_bin = request.data.get('staging_bin')
                        staging_bins = [staging_bin] if staging_bin else []
                    if not staging_bins:
                        raise APIException({"detail": "Please select inbound staging locations"})
                    command, replay = consume_preview(
                        request,
                        'asn.unload_start',
                        request_payload(request),
                        resource_id=str(pk),
                        asn_code=qs.asn_code,
                    )
                    if replay is not None:
                        return Response(replay)
                    try:
                        reserve_staging_slots(
                            self.request.auth.openid,
                            StagingAssignment.INBOUND,
                            qs.asn_code,
                            staging_bins,
                            quantity,
                            '',
                            request.META.get('HTTP_OPERATOR', ''),
                        )
                    except StagingError as exc:
                        raise APIException({"detail": str(exc)})
                    qs.asn_status = 2
                    for i in range(len(asn_detail_list)):
                        goods_qty_change = stocklist.objects.select_for_update().filter(openid=self.request.auth.openid,
                                                                    goods_code=str(asn_detail_list[i].goods_code)).first()
                        if goods_qty_change is None:
                            raise APIException({"detail": "Stock record does not exist for %s" % asn_detail_list[i].goods_code})
                        goods_qty_change.asn_stock = goods_qty_change.asn_stock - asn_detail_list[i].goods_qty
                        if goods_qty_change.asn_stock < 0:
                            goods_qty_change.asn_stock = 0
                        goods_qty_change.pre_load_stock = goods_qty_change.pre_load_stock + asn_detail_list[i].goods_qty
                        goods_qty_change.save()
                    asn_detail_list.update(asn_status=2)
                    qs.unload_driver = unload_driver
                    qs.save(update_fields=['asn_status', 'unload_driver', 'update_time'])
                    AsnEventModel.objects.create(
                        openid=self.request.auth.openid,
                        asn_code=qs.asn_code,
                        event_type=AsnEventModel.UNLOADING_STARTED,
                        operator=_operator_name(request),
                        source='WAREHOUSE',
                        note='Driver: %s; Staging: %s' % (
                            unload_driver,
                            ', '.join(sorted(str(item) for item in staging_bins)),
                        ),
                    )
                    serializer = self.get_serializer(qs, many=False)
                    headers = self.get_success_headers(serializer.data)
                    result = serializer.data
                    complete_preview(command, result)
                    return Response(result, status=200, headers=headers)
                else:
                    raise APIException({"detail": "Please Enter The ASN Detail"})
            else:
                raise APIException({"detail": "This ASN Status Is Not 1"})

class AsnPreSortViewSet(viewsets.ModelViewSet):
    """
        retrieve:
            Response a data list（get）
    """
    pagination_class = MyPageNumberPagination
    filter_backends = [DjangoFilterBackend, OrderingFilter, ]
    ordering_fields = ['id', "create_time", "update_time", ]
    filter_class = AsnListFilter

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
                return AsnListModel.objects.filter(openid=self.request.auth.openid, is_delete=False)
            else:
                return AsnListModel.objects.filter(openid=self.request.auth.openid, id=id, is_delete=False)
        else:
            return AsnListModel.objects.none()

    def get_serializer_class(self):
        if self.action in ['create']:
            return serializers.ASNListUpdateSerializer
        else:
            return self.http_method_not_allowed(request=self.request)

    @transaction.atomic
    def create(self, request, pk):
        qs = self.get_object()
        if qs.openid != self.request.auth.openid:
            raise APIException({"detail": "Cannot delete data which not yours"})
        else:
            if qs.asn_status == 2:
                command, replay = consume_preview(
                    request,
                    'asn.unload_finish',
                    request_payload(request),
                    resource_id=str(pk),
                    asn_code=qs.asn_code,
                )
                if replay is not None:
                    return Response(replay)
                qs.asn_status = 3
                occupy_staging_slot(
                    self.request.auth.openid,
                    StagingAssignment.INBOUND,
                    qs.asn_code,
                )
                asn_detail_list = AsnDetailModel.objects.filter(openid=self.request.auth.openid, asn_code=qs.asn_code,
                                                                asn_status=2, is_delete=False)
                for i in range(len(asn_detail_list)):
                    goods_qty_change = stocklist.objects.select_for_update().filter(openid=self.request.auth.openid,
                                                                goods_code=str(asn_detail_list[i].goods_code)).first()
                    goods_qty_change.pre_load_stock = goods_qty_change.pre_load_stock - asn_detail_list[i].goods_qty
                    if goods_qty_change.pre_load_stock < 0:
                        goods_qty_change.pre_load_stock = 0
                    goods_qty_change.pre_sort_stock = goods_qty_change.pre_sort_stock + asn_detail_list[i].goods_qty
                    goods_qty_change.save()
                asn_detail_list.update(asn_status=3)
                qs.save()
                serializer = self.get_serializer(qs, many=False)
                headers = self.get_success_headers(serializer.data)
                result = serializer.data
                complete_preview(command, result)
                return Response(result, status=200, headers=headers)
            else:
                raise APIException({"detail": "This ASN Status Is Not 2"})

def _validate_receiving_payload(openid, asn_code, supplier_name, goods_data):
    """Validate the complete receiving snapshot before changing inventory."""
    if not isinstance(goods_data, list) or not goods_data:
        raise APIException({"detail": "goodsData must contain every ASN detail line"})
    if not str(supplier_name or '').strip():
        raise APIException({"detail": "Receiving supplier is required"})

    details = list(AsnDetailModel.objects.select_for_update().filter(
        openid=openid,
        asn_code=asn_code,
        asn_status=3,
        is_delete=False,
    ))
    if not details:
        raise APIException({"detail": "No receiving detail lines are available for this ASN"})

    details_by_goods = {}
    for detail in details:
        if detail.goods_code in details_by_goods:
            raise APIException({
                "detail": "Receiving requires unique SKU lines; duplicate ASN detail found for %s" % detail.goods_code,
            })
        details_by_goods[detail.goods_code] = detail
        if supplier_name and detail.supplier != str(supplier_name):
            raise APIException({"detail": "Receiving supplier does not match the ASN"})

    quantities = {}
    seen = set()
    for row in goods_data:
        if not isinstance(row, dict):
            raise APIException({"detail": "Each goodsData item must be an object"})
        goods_code = str(row.get('goods_code') or '').strip()
        if not goods_code:
            raise APIException({"detail": "Receiving SKU is required"})
        if goods_code in seen:
            raise APIException({"detail": "Duplicate receiving SKU: %s" % goods_code})
        if goods_code not in details_by_goods:
            raise APIException({"detail": "SKU %s is not part of this ASN" % goods_code})
        try:
            actual_qty = int(row.get('goods_actual_qty'))
        except (TypeError, ValueError):
            raise APIException({"detail": "Received quantity must be an integer for %s" % goods_code})
        if actual_qty < 0:
            raise APIException({"detail": "Received quantity cannot be negative for %s" % goods_code})
        quantities[goods_code] = actual_qty
        seen.add(goods_code)

    expected = set(details_by_goods)
    missing = sorted(expected - seen)
    if missing:
        raise APIException({
            "detail": "Receiving payload is incomplete; missing SKU(s): %s" % ', '.join(missing),
        })

    # Fail before the first stock mutation if a required supporting record is missing.
    for detail in details:
        if stocklist.objects.select_for_update().filter(openid=openid, goods_code=str(detail.goods_code)).first() is None:
            raise APIException({"detail": "Stock record does not exist for %s" % detail.goods_code})
        if goods.objects.filter(openid=openid, goods_code=str(detail.goods_code), is_delete=False).first() is None:
            raise APIException({"detail": "SKU master data does not exist for %s" % detail.goods_code})
    return details, quantities


class AsnSortedViewSet(viewsets.ModelViewSet):
    """
        create:
            Finish Sorted

        update:
            All Sorted
    """
    pagination_class = MyPageNumberPagination
    filter_backends = [DjangoFilterBackend, OrderingFilter, ]
    ordering_fields = ['id', "create_time", "update_time", ]
    filter_class = AsnListFilter

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
                return AsnListModel.objects.filter(openid=self.request.auth.openid, is_delete=False)
            else:
                return AsnListModel.objects.filter(openid=self.request.auth.openid, id=id, is_delete=False)
        else:
            return AsnListModel.objects.none()

    def get_serializer_class(self):
        if self.action in ['create', 'update']:
            return serializers.ASNSortedPostSerializer
        else:
            return self.http_method_not_allowed(request=self.request)

    @transaction.atomic
    def create(self, request, pk):
        qs = self.get_object()
        if qs.asn_status != 3:
            raise APIException({"detail": "This ASN Status Is Not 3"})
        else:
            data = self.request.data
            requested_asn_code = str(data.get('asn_code') or '').strip()
            if requested_asn_code != str(qs.asn_code):
                raise APIException({"detail": "Receiving ASN code does not match the selected ASN"})
            _validate_receiving_payload(
                self.request.auth.openid,
                requested_asn_code,
                data.get('supplier'),
                data.get('goodsData'),
            )
            command, replay = consume_preview(
                request,
                'asn.receive',
                request_payload(request),
                resource_id=str(pk),
                asn_code=requested_asn_code,
            )
            if replay is not None:
                return Response(replay)
            for j in range(len(data['goodsData'])):
                goods_qty_change = stocklist.objects.select_for_update().filter(openid=self.request.auth.openid,
                                                            goods_code=str(
                                                                data['goodsData'][j].get('goods_code'))).first()
                asn_detail = AsnDetailModel.objects.filter(openid=self.request.auth.openid,
                                                           asn_code=str(data['asn_code']),
                                                           asn_status=3, is_delete=False,
                                                           supplier=str(data['supplier']),
                                                           goods_code=str(
                                                               data['goodsData'][j].get('goods_code'))).first()
                asn_detail.exception_resolved = False
                asn_detail.exception_resolution_action = ''
                asn_detail.exception_resolution_note = ''
                asn_detail.exception_resolution_location = ''
                asn_detail.exception_resolved_by = ''
                asn_detail.exception_resolved_at = None
                goods_detail = goods.objects.filter(openid=self.request.auth.openid,
                                                    goods_code=str(data['goodsData'][j].get('goods_code')),
                                                    is_delete=False).first()
                if int(data['goodsData'][j].get('goods_actual_qty')) == 0:
                    asn_detail.goods_actual_qty = int(data['goodsData'][j].get('goods_actual_qty'))
                    asn_detail.goods_shortage_qty = asn_detail.goods_qty
                    asn_detail.goods_cost = 0
                    qs.total_cost = qs.total_cost - (asn_detail.goods_shortage_qty * goods_detail.goods_cost)
                    goods_qty_change.goods_qty = goods_qty_change.goods_qty - asn_detail.goods_qty
                    goods_qty_change.pre_sort_stock = goods_qty_change.pre_sort_stock - asn_detail.goods_qty
                    asn_detail.asn_status = 5
                    asn_detail.save()
                    goods_qty_change.save()
                    if goods_qty_change.goods_qty == 0 and goods_qty_change.back_order_stock == 0:
                        goods_qty_change.delete()
                else:
                    asn_detail.goods_actual_qty = int(data['goodsData'][j].get('goods_actual_qty'))
                    goods_qty_check = asn_detail.goods_qty - int(data['goodsData'][j].get('goods_actual_qty'))
                    if goods_qty_check > 0:
                        asn_detail.goods_shortage_qty = goods_qty_check
                        asn_detail.goods_more_qty = 0
                        asn_detail.goods_cost = asn_detail.goods_cost - (asn_detail.goods_shortage_qty * goods_detail.goods_cost)
                        qs.total_cost = qs.total_cost - (asn_detail.goods_shortage_qty * goods_detail.goods_cost)
                        goods_qty_change.goods_qty = goods_qty_change.goods_qty - goods_qty_check
                        goods_qty_change.pre_sort_stock = goods_qty_change.pre_sort_stock - asn_detail.goods_qty
                        goods_qty_change.sorted_stock = goods_qty_change.sorted_stock + int(data['goodsData'][j].get('goods_actual_qty'))
                    elif goods_qty_check == 0:
                        asn_detail.goods_shortage_qty = 0
                        asn_detail.goods_more_qty = 0
                        goods_qty_change.pre_sort_stock = goods_qty_change.pre_sort_stock - int(data['goodsData'][j].get('goods_actual_qty'))
                        goods_qty_change.sorted_stock = goods_qty_change.sorted_stock + int(data['goodsData'][j].get('goods_actual_qty'))
                    elif goods_qty_check < 0:
                        asn_detail.goods_shortage_qty = 0
                        asn_detail.goods_more_qty = abs(goods_qty_check)
                        asn_detail.goods_cost = asn_detail.goods_cost + (asn_detail.goods_more_qty * goods_detail.goods_cost)
                        qs.total_cost = qs.total_cost + (asn_detail.goods_more_qty * goods_detail.goods_cost)
                        goods_qty_change.goods_qty = goods_qty_change.goods_qty + abs(goods_qty_check)
                        goods_qty_change.pre_sort_stock = goods_qty_change.pre_sort_stock - asn_detail.goods_qty
                        goods_qty_change.sorted_stock = goods_qty_change.sorted_stock + int(data['goodsData'][j].get('goods_actual_qty'))
                    asn_detail.asn_status = 4
                    asn_detail.save()
                    goods_qty_change.save()
                    if goods_qty_change.goods_qty == 0 and goods_qty_change.back_order_stock == 0:
                        goods_qty_change.delete()
            if AsnDetailModel.objects.filter(openid=self.request.auth.openid, asn_code=str(data['asn_code']),
                                                      asn_status=4, is_delete=False, supplier=str(data['supplier'])).exists():
                qs.asn_status = 4
            else:
                qs.asn_status = 5
            qs.save()
            if qs.asn_status == 5:
                # No physical goods remain to be put away (for example, a fully short shipment).
                release_staging_slot(self.request.auth.openid, StagingAssignment.INBOUND, qs.asn_code)
            result = {"detail": "success"}
            complete_preview(command, result)
            return Response(result, status=200)

    @transaction.atomic
    def update(self, request, *args, **kwargs):
        data = self.request.data
        asn_code = str(data.get('asn_code') or '').strip()
        if not asn_code:
            raise APIException({"detail": "ASN code is required"})
        qs = self.get_queryset().filter(asn_code=asn_code).select_for_update().first()
        if qs is None:
            raise APIException({"detail": "ASN does not exist"})
        if qs.asn_status != 3:
            raise APIException({"detail": "This ASN Status Is Not 3"})
        else:
            _validate_receiving_payload(
                self.request.auth.openid,
                asn_code,
                data.get('supplier'),
                data.get('goodsData'),
            )
            command, replay = consume_preview(
                request,
                'asn.receive',
                request_payload(request),
                resource_id=str(qs.id),
                asn_code=asn_code,
            )
            if replay is not None:
                return Response(replay)
            for j in range(len(data['goodsData'])):
                goods_qty_change = stocklist.objects.select_for_update().filter(openid=self.request.auth.openid,
                                                            goods_code=str(
                                                                data['goodsData'][j].get('goods_code'))).first()
                asn_detail = AsnDetailModel.objects.filter(openid=self.request.auth.openid,
                                                           asn_code=asn_code,
                                                           asn_status=3,
                                                           is_delete=False,
                                                           goods_code=str(
                                                               data['goodsData'][j].get('goods_code'))).first()
                if asn_detail is None:
                    raise APIException({"detail": "Receiving detail does not exist for %s" % data['goodsData'][j].get('goods_code')})
                asn_detail.exception_resolved = False
                asn_detail.exception_resolution_action = ''
                asn_detail.exception_resolution_note = ''
                asn_detail.exception_resolution_location = ''
                asn_detail.exception_resolved_by = ''
                asn_detail.exception_resolved_at = None
                goods_detail = goods.objects.filter(openid=self.request.auth.openid,
                                                    goods_code=str(data['goodsData'][j].get('goods_code')),
                                                    is_delete=False).first()
                if int(data['goodsData'][j].get('goods_actual_qty')) == 0:
                    asn_detail.goods_actual_qty = int(data['goodsData'][j].get('goods_actual_qty'))
                    asn_detail.goods_shortage_qty = asn_detail.goods_qty
                    asn_detail.goods_cost = 0
                    qs.total_cost = qs.total_cost - (asn_detail.goods_shortage_qty * goods_detail.goods_cost)
                    goods_qty_change.goods_qty = goods_qty_change.goods_qty - asn_detail.goods_qty
                    goods_qty_change.pre_sort_stock = goods_qty_change.pre_sort_stock - asn_detail.goods_qty
                    asn_detail.asn_status = 5
                    asn_detail.save()
                    goods_qty_change.save()
                    if goods_qty_change.goods_qty == 0 and goods_qty_change.back_order_stock == 0:
                        goods_qty_change.delete()
                else:
                    asn_detail.goods_actual_qty = int(data['goodsData'][j].get('goods_actual_qty'))
                    goods_qty_check = asn_detail.goods_qty - int(data['goodsData'][j].get('goods_actual_qty'))
                    if goods_qty_check > 0:
                        asn_detail.goods_shortage_qty = goods_qty_check
                        asn_detail.goods_more_qty = 0
                        asn_detail.goods_cost = asn_detail.goods_cost - (asn_detail.goods_shortage_qty * goods_detail.goods_cost)
                        qs.total_cost = qs.total_cost - (asn_detail.goods_shortage_qty * goods_detail.goods_cost)
                        goods_qty_change.goods_qty = goods_qty_change.goods_qty - goods_qty_check
                        goods_qty_change.pre_sort_stock = goods_qty_change.pre_sort_stock - asn_detail.goods_qty
                        goods_qty_change.sorted_stock = goods_qty_change.sorted_stock + int(data['goodsData'][j].get('goods_actual_qty'))
                    elif goods_qty_check == 0:
                        asn_detail.goods_shortage_qty = 0
                        asn_detail.goods_more_qty = 0
                        goods_qty_change.pre_sort_stock = goods_qty_change.pre_sort_stock - int(data['goodsData'][j].get('goods_actual_qty'))
                        goods_qty_change.sorted_stock = goods_qty_change.sorted_stock + int(data['goodsData'][j].get('goods_actual_qty'))
                    elif goods_qty_check < 0:
                        asn_detail.goods_shortage_qty = 0
                        asn_detail.goods_more_qty = abs(goods_qty_check)
                        asn_detail.goods_cost = asn_detail.goods_cost + (asn_detail.goods_more_qty * goods_detail.goods_cost)
                        qs.total_cost = qs.total_cost + (asn_detail.goods_more_qty * goods_detail.goods_cost)
                        goods_qty_change.goods_qty = goods_qty_change.goods_qty + abs(goods_qty_check)
                        goods_qty_change.pre_sort_stock = goods_qty_change.pre_sort_stock - asn_detail.goods_qty
                        goods_qty_change.sorted_stock = goods_qty_change.sorted_stock + int(data['goodsData'][j].get('goods_actual_qty'))
                    asn_detail.asn_status = 4
                    asn_detail.save()
                    goods_qty_change.save()
                    if goods_qty_change.goods_qty == 0 and goods_qty_change.back_order_stock == 0:
                        goods_qty_change.delete()
            if AsnDetailModel.objects.filter(openid=self.request.auth.openid, asn_code=str(data['asn_code']),
                                                      asn_status=4, is_delete=False).exists():
                qs.asn_status = 4
            else:
                qs.asn_status = 5
            qs.save()
            if qs.asn_status == 5:
                release_staging_slot(self.request.auth.openid, StagingAssignment.INBOUND, qs.asn_code)
            result = {"detail": "success"}
            complete_preview(command, result)
            return Response(result, status=200)

class MoveToBinViewSet(viewsets.ModelViewSet):
    """
        create:
            Create a data line（post）
    """
    pagination_class = MyPageNumberPagination
    filter_backends = [DjangoFilterBackend, OrderingFilter, ]
    ordering_fields = ['id', "create_time", "update_time", ]
    filter_class = AsnDetailFilter

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
                return AsnDetailModel.objects.filter(openid=self.request.auth.openid, is_delete=False)
            else:
                return AsnDetailModel.objects.filter(openid=self.request.auth.openid, id=id, is_delete=False)
        else:
            return AsnDetailModel.objects.none()

    def get_serializer_class(self):
        if self.action in ['retrieve']:
            return serializers.ASNDetailGetSerializer
        elif self.action in ['create', 'update']:
            return serializers.MoveToBinSerializer
        else:
            return self.http_method_not_allowed(request=self.request)

    def _validate_putaway_request(self, asn_code, detail, requested_qty, bin_name, putaway_driver):
        """Apply the same business gates to single and bulk putaway requests."""
        if detail is None or detail.is_delete or detail.asn_status != 4:
            raise APIException({"detail": "Only receiving-approved ASN details can be put away"})

        asn = AsnListModel.objects.select_for_update().filter(
            openid=self.request.auth.openid,
            asn_code=asn_code,
            is_delete=False,
        ).first()
        if asn is None:
            raise APIException({"detail": "ASN does not exist"})
        if asn.asn_status != 4:
            raise APIException({"detail": "ASN is not ready for putaway"})
        assert_legacy_asn_putaway_allowed(
            self.request.auth.openid,
            asn_code,
            detail.goods_code,
        )

        putaway_driver = str(putaway_driver or '').strip()
        if not putaway_driver:
            raise APIException({"detail": "Please assign a putaway driver"})
        if not driverlist.objects.filter(
            openid=self.request.auth.openid,
            driver_name=putaway_driver,
            is_delete=False,
        ).exists():
            raise APIException({"detail": "Putaway driver does not exist"})
        if asn.putaway_driver and asn.putaway_driver != putaway_driver:
            raise APIException({
                "detail": "This ASN is already assigned to putaway driver %s" % asn.putaway_driver,
            })

        bin_detail = binset.objects.select_for_update().filter(
            openid=self.request.auth.openid,
            bin_name=str(bin_name or '').strip(),
            is_delete=False,
        ).first()
        if bin_detail is None:
            raise APIException({"detail": "Bin does not exist"})
        if bin_detail.location_role == 'STAGING':
            raise APIException({"detail": "Staging locations cannot be used for final putaway"})

        goods_qty_change = stocklist.objects.select_for_update().filter(
            openid=self.request.auth.openid,
            goods_code=str(detail.goods_code),
        ).first()
        if goods_qty_change is None:
            raise APIException({"detail": "Stock record does not exist for %s" % detail.goods_code})
        try:
            requested_qty = int(requested_qty)
        except (TypeError, ValueError):
            raise APIException({"detail": "Putaway quantity must be an integer"})
        if requested_qty <= 0:
            raise APIException({"detail": "Move QTY Must > 0"})
        remaining_qty = int(detail.goods_actual_qty or 0) - int(detail.sorted_qty or 0)
        if requested_qty > remaining_qty:
            raise APIException({"detail": "Move QTY exceeds the remaining received quantity"})

        current_pack_list = PackListDocument.objects.filter(
            openid=self.request.auth.openid,
            asn_code=detail.asn_code,
            is_current=True,
            status=PackListDocument.CONFIRMED,
        ).first()
        if current_pack_list:
            pack_qty = sum(
                int(line.goods_qty or 0)
                for line in current_pack_list.lines.filter(
                    is_current=True,
                    goods_code=detail.goods_code,
                )
            )
            if pack_qty and pack_qty != int(detail.goods_actual_qty or 0) and not detail.exception_resolved:
                raise APIException({
                    "detail": "Customer Pack List quantity mismatch; resolve the receiving exception before putaway",
                })

        serial_records = AsnSerialRecord.objects.filter(
            openid=self.request.auth.openid,
            asn_code=detail.asn_code,
            goods_code=detail.goods_code,
        )
        eligible_remaining = remaining_qty
        if serial_records.exists():
            strict_serial_check = serial_records.filter(is_expected=True).exists()
            missing_serials = serial_records.filter(
                is_expected=True,
                is_received=False,
                exception_resolved=False,
            ).count()
            exception_statuses = [
                AsnSerialRecord.DUPLICATE,
                AsnSerialRecord.WRONG_SKU,
                AsnSerialRecord.DAMAGED,
                AsnSerialRecord.REJECTED,
            ]
            if strict_serial_check:
                exception_statuses.append(AsnSerialRecord.UNEXPECTED)
            exception_serials = serial_records.filter(
                status__in=exception_statuses,
                exception_resolved=False,
            ).count()
            accepted_serials = serial_records.filter(status=AsnSerialRecord.ACCEPTED).count()
            resolved_serials = serial_records.filter(
                exception_resolved=True,
                exception_resolution_action__in=PUTAWAY_APPROVED_RESOLUTIONS,
            ).count()
            expected_sn_count = serial_records.filter(is_expected=True).count()
            scanned_sn_count = serial_records.filter(is_received=True).count()
            eligible_serials = accepted_serials + resolved_serials
            eligible_remaining = max(eligible_serials - int(detail.sorted_qty or 0), 0)
            if strict_serial_check and requested_qty > eligible_remaining:
                blocked_parts = []
                if missing_serials:
                    blocked_parts.append("%s expected SN missing" % missing_serials)
                if exception_serials:
                    blocked_parts.append("%s unresolved SN exception(s)" % exception_serials)
                if not blocked_parts:
                    blocked_parts.append("only %s eligible unit(s) remain" % eligible_remaining)
                raise APIException({
                    "detail": (
                        "SN verification incomplete. Expected: %s; Scanned: %s; Accepted: %s; "
                        "Hold/exception: %s; Requested: %s; Maximum allowed now: %s. %s. "
                        "Reduce Putaway Qty or open Review QC."
                    ) % (
                        expected_sn_count,
                        scanned_sn_count,
                        eligible_serials,
                        max(expected_sn_count - eligible_serials, 0),
                        requested_qty,
                        eligible_remaining,
                        "; ".join(blocked_parts),
                    ),
                })

        if detail.exception_resolved and detail.exception_resolution_action in {HOLD_QUARANTINE, REJECT_RETURN}:
            raise APIException({"detail": "This quantity exception is held or rejected and is not eligible for putaway"})
        if current_pack_list and current_pack_list.has_serials:
            expected_serials = set(current_pack_list.serial_records.filter(
                is_expected=True,
            ).values_list('serial_number', flat=True))
            received_serials = set(serial_records.filter(
                is_received=True,
            ).values_list('serial_number', flat=True))
            if (
                (expected_serials - received_serials or received_serials - expected_serials)
                and requested_qty > eligible_remaining
            ):
                raise APIException({
                    "detail": (
                        "Customer Pack List serial mismatch. Expected: %s; Scanned: %s; "
                        "Maximum allowed now: %s. Review QC before moving the remaining quantity."
                    ) % (len(expected_serials), len(received_serials), eligible_remaining),
                })
        if (
            not detail.exception_resolved
            and (
                int(detail.goods_shortage_qty or 0)
                or int(detail.goods_more_qty or 0)
                or int(detail.goods_damage_qty or 0)
            )
        ):
            raise APIException({"detail": "Receiving quantity exception is unresolved; resolve it before putaway"})
        return asn, bin_detail, goods_qty_change, putaway_driver

    @transaction.atomic
    def create(self, request, pk):
        qs = self.get_object()
        if qs.openid != self.request.auth.openid:
            raise APIException({"detail": "Cannot delete data which not yours"})
        else:
            if qs.asn_status != 4:
                raise APIException({"detail": "This ASN Status Is Not 4"})
            else:
                data = self.request.data
                putaway_driver = str(data.get('putaway_driver') or data.get('driver') or '').strip()
                requested_asn_code = str(data.get('asn_code') or '').strip()
                if requested_asn_code != str(qs.asn_code):
                    raise APIException({"detail": "Putaway ASN code does not match the selected ASN detail"})
                self._validate_putaway_request(
                    requested_asn_code,
                    qs,
                    data.get('qty'),
                    data.get('bin_name'),
                    putaway_driver,
                )
                command, replay = consume_preview(
                    request,
                    'asn.putaway',
                    request_payload(request),
                    resource_id=str(pk),
                    asn_code=requested_asn_code,
                )
                if replay is not None:
                    return Response(replay)
                if not putaway_driver:
                    raise APIException({"detail": "Please assign a putaway driver"})
                driver_record = driverlist.objects.filter(
                    openid=self.request.auth.openid,
                    driver_name=putaway_driver,
                    is_delete=False,
                ).first()
                if driver_record is None:
                    raise APIException({"detail": "Putaway driver does not exist"})
                if 'bin_name' not in data:
                    raise APIException({"detail": "Please Enter the Bin Name"})
                else:
                    bin_detail = binset.objects.filter(openid=self.request.auth.openid,
                                                       bin_name=str(data['bin_name']),
                                                       is_delete=False).first()
                    if bin_detail is None:
                        raise APIException({"detail": "Bin does not exist"})
                    if bin_detail.location_role == 'STAGING':
                        raise APIException({"detail": "Staging locations cannot be used for final putaway"})
                    asn_detail = AsnListModel.objects.select_for_update().filter(
                        openid=self.request.auth.openid,
                        asn_code=requested_asn_code,
                        is_delete=False,
                    ).first()
                    if asn_detail is None:
                        raise APIException({"detail": "ASN does not exist"})
                    if asn_detail.putaway_driver and asn_detail.putaway_driver != putaway_driver:
                        raise APIException({
                            "detail": "This ASN is already assigned to putaway driver %s" % asn_detail.putaway_driver
                        })
                    goods_qty_change = stocklist.objects.select_for_update().filter(openid=self.request.auth.openid,
                                                                goods_code=str(data['goods_code'])).first()
                    requested_qty = int(data['qty'])
                    if requested_qty <= 0:
                        raise APIException({"detail": "Move QTY Must > 0"})
                    remaining_qty = int(qs.goods_actual_qty or 0) - int(qs.sorted_qty or 0)
                    if requested_qty > remaining_qty:
                        raise APIException({"detail": "Move QTY exceeds the remaining received quantity"})
                    else:
                        current_pack_list = PackListDocument.objects.filter(
                            openid=self.request.auth.openid,
                            asn_code=qs.asn_code,
                            is_current=True,
                            status=PackListDocument.CONFIRMED,
                        ).first()
                        if current_pack_list:
                            pack_qty = sum(
                                int(line.goods_qty or 0)
                                for line in current_pack_list.lines.filter(
                                    is_current=True,
                                    goods_code=qs.goods_code,
                                )
                            )
                            if pack_qty and pack_qty != int(qs.goods_actual_qty or 0) and not qs.exception_resolved:
                                raise APIException({
                                    "detail": "Customer Pack List quantity mismatch; resolve the receiving exception before putaway"
                                })
                        serial_records = AsnSerialRecord.objects.filter(
                            openid=self.request.auth.openid,
                            asn_code=qs.asn_code,
                            goods_code=qs.goods_code,
                        )
                        eligible_remaining = remaining_qty
                        if serial_records.exists():
                            strict_serial_check = serial_records.filter(is_expected=True).exists()
                            missing_serials = serial_records.filter(
                                is_expected=True,
                                is_received=False,
                                exception_resolved=False,
                            ).count()
                            exception_statuses = [
                                AsnSerialRecord.DUPLICATE,
                                AsnSerialRecord.WRONG_SKU,
                                AsnSerialRecord.DAMAGED,
                                AsnSerialRecord.REJECTED,
                            ]
                            if strict_serial_check:
                                exception_statuses.append(AsnSerialRecord.UNEXPECTED)
                            exception_serials = serial_records.filter(
                                status__in=exception_statuses,
                                exception_resolved=False,
                            ).count()
                            accepted_serials = serial_records.filter(status=AsnSerialRecord.ACCEPTED).count()
                            resolved_serials = serial_records.filter(
                                exception_resolved=True,
                                exception_resolution_action__in=PUTAWAY_APPROVED_RESOLUTIONS,
                            ).count()
                            expected_sn_count = serial_records.filter(is_expected=True).count()
                            scanned_sn_count = serial_records.filter(is_received=True).count()
                            eligible_serials = accepted_serials + resolved_serials
                            eligible_remaining = max(eligible_serials - int(qs.sorted_qty or 0), 0)
                            if strict_serial_check and requested_qty > eligible_remaining:
                                blocked_parts = []
                                if missing_serials:
                                    blocked_parts.append("%s expected SN missing" % missing_serials)
                                if exception_serials:
                                    blocked_parts.append("%s unresolved SN exception(s)" % exception_serials)
                                if not blocked_parts:
                                    blocked_parts.append("only %s eligible unit(s) remain" % eligible_remaining)
                                raise APIException({
                                    "detail": (
                                        "SN verification incomplete. Expected: %s; Scanned: %s; "
                                        "Accepted: %s; Hold/exception: %s; Requested: %s; "
                                        "Maximum allowed now: %s. %s. Reduce Putaway Qty or open Review QC."
                                    ) % (
                                        expected_sn_count,
                                        scanned_sn_count,
                                        eligible_serials,
                                        max(expected_sn_count - eligible_serials, 0),
                                        requested_qty,
                                        eligible_remaining,
                                        "; ".join(blocked_parts),
                                    )
                                })
                        if qs.exception_resolved and qs.exception_resolution_action in {HOLD_QUARANTINE, REJECT_RETURN}:
                            raise APIException({
                                "detail": "This quantity exception is held or rejected and is not eligible for putaway"
                            })
                        if current_pack_list and current_pack_list.has_serials:
                            expected_serials = set(current_pack_list.serial_records.filter(
                                is_expected=True,
                            ).values_list('serial_number', flat=True))
                            received_serials = set(serial_records.filter(
                                is_received=True,
                            ).values_list('serial_number', flat=True))
                            if (
                                (expected_serials - received_serials or received_serials - expected_serials)
                                and requested_qty > eligible_remaining
                            ):
                                raise APIException({
                                    "detail": (
                                        "Customer Pack List serial mismatch. Expected: %s; Scanned: %s; "
                                        "Maximum allowed now: %s. Review QC before moving the remaining quantity."
                                    ) % (
                                        len(expected_serials),
                                        len(received_serials),
                                        eligible_remaining,
                                    )
                                })
                        if (
                            not qs.exception_resolved
                            and (
                                int(qs.goods_shortage_qty or 0)
                                or int(qs.goods_more_qty or 0)
                                or int(qs.goods_damage_qty or 0)
                            )
                        ):
                            raise APIException({
                                "detail": "Receiving quantity exception is unresolved; resolve it before putaway"
                            })
                        operator = staff.objects.filter(openid=self.request.auth.openid,
                                                        id=self.request.META.get('HTTP_OPERATOR')).first()
                        if operator is None:
                            raise APIException({"detail": "Operator does not exist"})
                        staff_name = operator.staff_name
                        move_qty = qs.goods_actual_qty - qs.sorted_qty - requested_qty
                        if move_qty > 0:
                            qs.sorted_qty = qs.sorted_qty + requested_qty
                            goods_qty_change.sorted_stock = goods_qty_change.sorted_stock - requested_qty
                            goods_qty_change.onhand_stock = goods_qty_change.onhand_stock + requested_qty
                            if bin_detail.bin_property == 'Damage':
                                goods_qty_change.damage_stock = goods_qty_change.damage_stock + requested_qty
                                qs.goods_damage_qty = qs.goods_damage_qty + requested_qty
                            elif bin_detail.bin_property == 'Inspection':
                                goods_qty_change.inspect_stock = goods_qty_change.inspect_stock + requested_qty
                            elif bin_detail.bin_property == 'Holding':
                                goods_qty_change.hold_stock = goods_qty_change.hold_stock + requested_qty
                            else:
                                goods_qty_change.can_order_stock = goods_qty_change.can_order_stock + requested_qty
                            qs.save()
                            goods_qty_change.save()
                            store_code = Md5.md5(str(data['goods_code']))
                            stockbin.objects.create(openid=self.request.auth.openid,
                                                    bin_name=str(data['bin_name']),
                                                    goods_code=str(data['goods_code']),
                                                    goods_desc=goods_qty_change.goods_desc,
                                                    goods_qty=requested_qty,
                                                    bin_size=bin_detail.bin_size,
                                                    bin_property=bin_detail.bin_property,
                                                    t_code=store_code,
                                                    create_time=qs.create_time
                                                    )
                            qtychangerecorder.objects.create(openid=self.request.auth.openid,
                                                             mode_code=qs.asn_code,
                                                             bin_name=str(data['bin_name']),
                                                             goods_code=str(data['goods_code']),
                                                             goods_desc=goods_qty_change.goods_desc,
                                                             goods_qty=requested_qty,
                                                             store_code=store_code,
                                                             creater=str(staff_name)
                                                             )
                            cur_date = timezone.now().date()
                            line_data = cyclecount.objects.filter(openid=self.request.auth.openid,
                                                                  bin_name=str(data['bin_name']),
                                                                  goods_code=str(data['goods_code']),
                                                                  create_time__gte=cur_date)
                            bin_check = stockbin.objects.filter(openid=self.request.auth.openid,
                                                                bin_name=str(data['bin_name']),
                                                                goods_code=str(data['goods_code']),
                                                                )
                            if bin_check.exists():
                                bin_stock = bin_check.aggregate(sum=Sum('goods_qty'))["sum"]
                            else:
                                bin_stock = 0
                            if line_data.exists():
                                line_data.goods_qty = bin_stock + requested_qty
                                line_data.update(goods_qty=line_data.goods_qty)
                            else:
                                cyclecount.objects.create(openid=self.request.auth.openid,
                                                          bin_name=str(data['bin_name']),
                                                          goods_code=str(data['goods_code']),
                                                          goods_qty=requested_qty,
                                                          creater=str(staff_name)
                                                          )
                            if bin_detail.empty_label is True:
                                bin_detail.empty_label = False
                                bin_detail.save()
                        elif move_qty == 0:
                            qs.sorted_qty = qs.sorted_qty + requested_qty
                            qs.asn_status = 5
                            goods_qty_change.sorted_stock = goods_qty_change.sorted_stock - requested_qty
                            goods_qty_change.onhand_stock = goods_qty_change.onhand_stock + requested_qty
                            if bin_detail.bin_property == 'Damage':
                                goods_qty_change.damage_stock = goods_qty_change.damage_stock + requested_qty
                                qs.goods_damage_qty = qs.goods_damage_qty + requested_qty
                            elif bin_detail.bin_property == 'Inspection':
                                goods_qty_change.inspect_stock = goods_qty_change.inspect_stock + requested_qty
                            elif bin_detail.bin_property == 'Holding':
                                goods_qty_change.hold_stock = goods_qty_change.hold_stock + requested_qty
                            else:
                                goods_qty_change.can_order_stock = goods_qty_change.can_order_stock + requested_qty
                            cur_date = timezone.now().date()
                            line_data = cyclecount.objects.filter(openid=self.request.auth.openid,
                                                                  bin_name=str(data['bin_name']),
                                                                  goods_code=str(data['goods_code']),
                                                                  create_time__gte=cur_date)
                            bin_check = stockbin.objects.filter(openid=self.request.auth.openid,
                                                                bin_name=str(data['bin_name']),
                                                                goods_code=str(data['goods_code']),
                                                                )
                            if bin_check.exists():
                                bin_stock = bin_check.aggregate(sum=Sum('goods_qty'))["sum"]
                            else:
                                bin_stock = 0
                            if line_data.exists():
                                line_data.goods_qty = bin_stock + requested_qty
                                line_data.update(goods_qty=line_data.goods_qty)
                            else:
                                cyclecount.objects.create(openid=self.request.auth.openid,
                                                          bin_name=str(data['bin_name']),
                                                          goods_code=str(data['goods_code']),
                                                          goods_qty=requested_qty,
                                                          creater=str(staff_name),
                                                          t_code=Md5.md5(str(data['bin_name']))
                                                          )
                            qs.save()
                            goods_qty_change.save()
                            if AsnDetailModel.objects.filter(openid=self.request.auth.openid,
                                                             asn_code=requested_asn_code,
                                                             asn_status=4,
                                                             is_delete=False,
                                                             ).exists():
                                pass
                            else:
                                asn_detail.asn_status = 5
                                asn_detail.save()
                            store_code = Md5.md5(str(data['goods_code']))
                            stockbin.objects.create(openid=self.request.auth.openid,
                                                    bin_name=str(data['bin_name']),
                                                    goods_code=str(data['goods_code']),
                                                    goods_desc=goods_qty_change.goods_desc,
                                                    goods_qty=requested_qty,
                                                    bin_size=bin_detail.bin_size,
                                                    bin_property=bin_detail.bin_property,
                                                    t_code=store_code,
                                                    create_time=qs.create_time)
                            qtychangerecorder.objects.create(openid=self.request.auth.openid,
                                                             mode_code=qs.asn_code,
                                                             bin_name=str(data['bin_name']),
                                                             goods_code=str(data['goods_code']),
                                                             goods_desc=goods_qty_change.goods_desc,
                                                             goods_qty=requested_qty,
                                                             store_code=store_code,
                                                             creater=str(staff_name)
                                                             )
                            if bin_detail.empty_label is True:
                                bin_detail.empty_label = False
                                bin_detail.save()
                            if asn_detail.asn_status == 5:
                                release_staging_slot(self.request.auth.openid, StagingAssignment.INBOUND, asn_detail.asn_code)
                        elif move_qty < 0:
                            raise APIException({"detail": "Move Qty must < Actual Arrive Qty"})
                        if not asn_detail.putaway_driver:
                            asn_detail.putaway_driver = putaway_driver
                            asn_detail.save(update_fields=['putaway_driver', 'update_time'])
                            AsnEventModel.objects.create(
                                openid=self.request.auth.openid,
                                asn_code=asn_detail.asn_code,
                                event_type=AsnEventModel.PUTAWAY_STARTED,
                                operator=_operator_name(self.request),
                                source='WAREHOUSE',
                                note='Putaway driver assigned: %s' % putaway_driver,
                            )
                        result = {"detail": "success", "putaway_driver": asn_detail.putaway_driver}
                        complete_preview(command, result)
                        return Response(result, status=200)

    @transaction.atomic
    def update(self, request, *args, **kwargs):
        """Bulk putaway with the same gates as the single-item endpoint."""
        data = request.data
        asn_code = str(data.get('asn_code') or '').strip()
        bin_name = str(data.get('bin_name') or '').strip()
        putaway_driver = str(data.get('putaway_driver') or data.get('driver') or '').strip()
        items = data.get('res_data')
        if not asn_code or not bin_name or not putaway_driver:
            raise APIException({"detail": "ASN code, final bin, and putaway driver are required"})
        if not isinstance(items, list) or not items:
            raise APIException({"detail": "res_data must contain at least one putaway line"})

        asn = AsnListModel.objects.select_for_update().filter(
            openid=self.request.auth.openid,
            asn_code=asn_code,
            is_delete=False,
        ).first()
        if asn is None:
            raise APIException({"detail": "ASN does not exist"})
        if asn.asn_status != 4:
            raise APIException({"detail": "ASN is not ready for putaway"})

        details = {
            detail.goods_code: detail
            for detail in AsnDetailModel.objects.select_for_update().filter(
                openid=self.request.auth.openid,
                asn_code=asn_code,
                asn_status=4,
                is_delete=False,
            )
        }
        if not details:
            raise APIException({"detail": "No ASN detail is ready for putaway"})

        normalized = []
        seen = set()
        for item in items:
            if not isinstance(item, dict):
                raise APIException({"detail": "Each res_data item must be an object"})
            goods_code = str(item.get('goods_code') or '').strip()
            if not goods_code or goods_code not in details:
                raise APIException({"detail": "SKU %s is not ready for putaway" % (goods_code or '<empty>')})
            if goods_code in seen:
                raise APIException({"detail": "Duplicate putaway SKU: %s" % goods_code})
            try:
                quantity = int(item.get('qty'))
            except (TypeError, ValueError):
                raise APIException({"detail": "Putaway quantity must be an integer for %s" % goods_code})
            normalized.append((goods_code, quantity))
            seen.add(goods_code)

        operator = staff.objects.filter(
            openid=self.request.auth.openid,
            id=self.request.META.get('HTTP_OPERATOR'),
            is_delete=False,
        ).first()
        if operator is None:
            raise APIException({"detail": "Operator does not exist"})

        bin_detail = None
        for goods_code, quantity in normalized:
            _, bin_detail, _, putaway_driver = self._validate_putaway_request(
                asn_code,
                details[goods_code],
                quantity,
                bin_name,
                putaway_driver,
            )

        command, replay = consume_preview(
            request,
            'asn.putaway_bulk',
            request_payload(request),
            resource_id=asn_code,
            asn_code=asn_code,
        )
        if replay is not None:
            return Response(replay)

        for goods_code, quantity in normalized:
            detail = details[goods_code]
            goods_qty_change = stocklist.objects.select_for_update().filter(
                openid=self.request.auth.openid,
                goods_code=goods_code,
            ).first()
            remaining_qty = int(detail.goods_actual_qty or 0) - int(detail.sorted_qty or 0)
            move_qty = remaining_qty - quantity
            detail.sorted_qty = int(detail.sorted_qty or 0) + quantity
            if move_qty == 0:
                detail.asn_status = 5

            if bin_detail.bin_property == 'Damage':
                goods_qty_change.damage_stock = goods_qty_change.damage_stock + quantity
                detail.goods_damage_qty = detail.goods_damage_qty + quantity
            elif bin_detail.bin_property == 'Inspection':
                goods_qty_change.inspect_stock = goods_qty_change.inspect_stock + quantity
            elif bin_detail.bin_property == 'Holding':
                goods_qty_change.hold_stock = goods_qty_change.hold_stock + quantity
            else:
                goods_qty_change.can_order_stock = goods_qty_change.can_order_stock + quantity
            goods_qty_change.sorted_stock = goods_qty_change.sorted_stock - quantity
            goods_qty_change.onhand_stock = goods_qty_change.onhand_stock + quantity
            detail.save()
            goods_qty_change.save()

            store_code = Md5.md5(goods_code)
            stockbin.objects.create(
                openid=self.request.auth.openid,
                bin_name=bin_name,
                goods_code=goods_code,
                goods_desc=goods_qty_change.goods_desc,
                goods_qty=quantity,
                bin_size=bin_detail.bin_size,
                bin_property=bin_detail.bin_property,
                t_code=store_code,
                create_time=detail.create_time,
            )
            qtychangerecorder.objects.create(
                openid=self.request.auth.openid,
                mode_code=asn_code,
                bin_name=bin_name,
                goods_code=goods_code,
                goods_desc=goods_qty_change.goods_desc,
                goods_qty=quantity,
                store_code=store_code,
                creater=operator.staff_name,
            )
            current_date = timezone.now().date()
            bin_stock = stockbin.objects.filter(
                openid=self.request.auth.openid,
                bin_name=bin_name,
                goods_code=goods_code,
            ).aggregate(sum=Sum('goods_qty'))['sum'] or 0
            line_data = cyclecount.objects.filter(
                openid=self.request.auth.openid,
                bin_name=bin_name,
                goods_code=goods_code,
                create_time__gte=current_date,
            )
            if line_data.exists():
                line_data.update(goods_qty=bin_stock)
            else:
                cyclecount.objects.create(
                    openid=self.request.auth.openid,
                    bin_name=bin_name,
                    goods_code=goods_code,
                    goods_qty=bin_stock,
                    creater=operator.staff_name,
                    t_code=Md5.md5(bin_name),
                )
            if bin_detail.empty_label:
                bin_detail.empty_label = False
                bin_detail.save(update_fields=['empty_label', 'update_time'])

        if not AsnDetailModel.objects.filter(
            openid=self.request.auth.openid,
            asn_code=asn_code,
            asn_status=4,
            is_delete=False,
        ).exists():
            asn.asn_status = 5
            asn.save(update_fields=['asn_status', 'update_time'])
            release_staging_slot(self.request.auth.openid, StagingAssignment.INBOUND, asn_code)
        if not asn.putaway_driver:
            asn.putaway_driver = putaway_driver
            asn.save(update_fields=['putaway_driver', 'update_time'])
            AsnEventModel.objects.create(
                openid=self.request.auth.openid,
                asn_code=asn_code,
                event_type=AsnEventModel.PUTAWAY_STARTED,
                operator=_operator_name(request),
                source='WAREHOUSE',
                note='Putaway driver assigned: %s' % putaway_driver,
            )
        result = {"detail": "success", "putaway_driver": asn.putaway_driver}
        complete_preview(command, result)
        return Response(result, status=200)

class FileListDownloadView(viewsets.ModelViewSet):
    renderer_classes = (FileListRenderCN, ) + tuple(api_settings.DEFAULT_RENDERER_CLASSES)
    filter_backends = [DjangoFilterBackend, OrderingFilter, ]
    ordering_fields = ['id', "create_time", "update_time", ]
    filter_class = AsnListFilter

    def get_project(self):
        try:
            id = self.kwargs.get('pk')
            return id
        except:
            return None

    def get_queryset(self):
        id = self.get_project()
        if self.request.user:
            empty_qs = AsnListModel.objects.filter(
                Q(openid=self.request.auth.openid, asn_status=1, is_delete=False) & Q(supplier=''))
            cur_date = timezone.now()
            date_check = relativedelta(day=1)
            if len(empty_qs) > 0:
                for i in range(len(empty_qs)):
                    if empty_qs[i].create_time <= cur_date - date_check:
                        empty_qs[i].delete()
            if id is None:
                return AsnListModel.objects.filter(
                    Q(openid=self.request.auth.openid, is_delete=False) & ~Q(supplier=''))
            else:
                return AsnListModel.objects.filter(
                    Q(openid=self.request.auth.openid, id=id, is_delete=False) & ~Q(supplier=''))
        else:
            return AsnListModel.objects.none()

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
        response['Content-Disposition'] = "attachment; filename='asnlist_{}.csv'".format(str(dt.strftime('%Y%m%d%H%M%S%f')))
        return response

class FileDetailDownloadView(viewsets.ModelViewSet):
    serializer_class = serializers.FileDetailRenderSerializer
    renderer_classes = (FileDetailRenderCN, ) + tuple(api_settings.DEFAULT_RENDERER_CLASSES)
    filter_backends = [DjangoFilterBackend, OrderingFilter, ]
    ordering_fields = ['id', "create_time", "update_time", ]
    filter_class = AsnDetailFilter

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
                return AsnDetailModel.objects.filter(openid=self.request.auth.openid, is_delete=False)
            else:
                return AsnDetailModel.objects.filter(openid=self.request.auth.openid, id=id, is_delete=False)
        else:
            return AsnDetailModel.objects.none()

    def get_serializer_class(self):
        if self.action == 'list':
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
        response['Content-Disposition'] = "attachment; filename='asndetail_{}.csv'".format(str(dt.strftime('%Y%m%d%H%M%S%f')))
        return response
