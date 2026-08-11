from rest_framework import viewsets
from asn.models import AsnDetailModel, AsnListModel
from dn.models import DnDetailModel
from asn import serializers as asnserializers
from dn import serializers as dnserializers
from utils.page import MyPageNumberPagination
from utils.datasolve import sumOfList
from utils.fbmsg import FBMsg
from utils.md5 import Md5
from rest_framework.filters import OrderingFilter
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.response import Response
from asn.filter import AsnDetailFilter
from dn.filter import DnDetailFilter
from rest_framework.exceptions import APIException
from django.shortcuts import render
from dateutil.relativedelta import relativedelta
from django.db.models.functions import TruncMonth,TruncYear,ExtractDay,ExtractMonth
from django.db.models import Count
from django.db import connection
from django.db.models import Q
from django.db.models import Sum
import re
from django.utils import timezone

class ReceiptsViewSet(viewsets.ModelViewSet):
    """
        list:
            Response a data list（all）
    """
    pagination_class = None
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
                return AsnDetailModel.objects.filter(openid=self.request.auth.openid, asn_status__gte=4,
                                                     create_time__gte=timezone.now().date() - relativedelta(days=14),
                                                     is_delete=False)
            else:
                return AsnDetailModel.objects.filter(openid=self.request.auth.openid, asn_status__gte=4,
                                                     create_time__gte=timezone.now().date() - relativedelta(days=14),
                                                     id=id, is_delete=False)
        else:
            return AsnDetailModel.objects.none()

    def get_serializer_class(self):
        if self.action in ['list']:
            return asnserializers.ASNDetailGetSerializer
        else:
            return self.http_method_not_allowed(request=self.request)

    def notice_lang(self):
        lang = self.request.META.get('HTTP_LANGUAGE')
        return lang

    def list(self, request, *args, **kwargs):
        qs = self.get_queryset()
        context = {}
        dataset = {}
        dimensions = ['product']
        source = []
        series = []
        bar_charts = {
            "type": 'bar',
            "barWidth": '4%',
            "barGap": '60%',
            "barCategoryGap": '10%',
            "itemStyle": {
              "normal": {
                "label": {
                  "show": "true",
                  "position": "top"
                }
              }
            }
          }
        receipt_res = qs.annotate(month=ExtractMonth('create_time'), day=ExtractDay('create_time')) \
            .values('month', 'day').order_by('month', 'day').annotate(number=Sum('goods_cost'))
        # qty_res = qs.values('goods_code').order_by('goods_code').annotate(number=Sum('goods_qty'))
        # rank_res = qs.values('goods_code').order_by('goods_code').annotate(number=Sum('goods_cost'))
        receipt_res_dict = {
        }
        # qty_res_dict = {
        # }
        # rank_res_dict = {
        # }
        for i in receipt_res:
            series.append(bar_charts)
            dimensions.append("%s-%s" % (i['month'], i['day']))
            receipt_res_dict.update({"%s-%s" % (i['month'], i['day']): round(i['number'], 2)})
        # for i in qty_res:
        #     qty_res_dict.update({i['goods_code']: i['number']})
        # for i in rank_res:
        #     rank_res_dict.update({i['goods_code']: i['number']})
        source.append(receipt_res_dict)
        # data_list.append(qty_res_dict)
        # data_list.append(rank_res_dict)
        dataset['source'] = source
        dataset['dimensions'] = dimensions
        context['dataset'] = dataset
        context['series'] = series
        return Response(context)

class SalesViewSet(viewsets.ModelViewSet):
    """
        list:
            Response a data list（all）
    """
    pagination_class = None
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
                return DnDetailModel.objects.filter(openid=self.request.auth.openid, dn_status__gte=4,
                                                    create_time__gte=timezone.now().date() - relativedelta(days=14),
                                                    is_delete=False)
            else:
                return DnDetailModel.objects.filter(openid=self.request.auth.openid, dn_status__gte=4,
                                                    create_time__gte=timezone.now().date() - relativedelta(days=14),
                                                    id=id, is_delete=False)
        else:
            return DnDetailModel.objects.none()

    def get_serializer_class(self):
        if self.action in ['list']:
            return dnserializers.DNDetailGetSerializer
        else:
            return self.http_method_not_allowed(request=self.request)

    def notice_lang(self):
        lang = self.request.META.get('HTTP_LANGUAGE')
        return lang

    def list(self, request, *args, **kwargs):
        qs = self.get_queryset()
        context = {}
        dataset = {}
        dimensions = ['product']
        source = []
        series = []
        bar_charts = {
            "type": 'bar',
            "barWidth": '4%',
            "barGap": '60%',
            "barCategoryGap": '10%',
            "itemStyle": {
              "normal": {
                "label": {
                  "show": "true",
                  "position": "top"
                }
              }
            }
          }
        receipt_res = qs.annotate(month=ExtractMonth('create_time'), day=ExtractDay('create_time')) \
            .values('month', 'day').order_by('month', 'day').annotate(number=Sum('goods_cost'))
        # qty_res = qs.values('goods_code').order_by('goods_code').annotate(number=Sum('goods_qty'))
        # rank_res = qs.values('goods_code').order_by('goods_code').annotate(number=Sum('goods_cost'))
        receipt_res_dict = {
        }
        # qty_res_dict = {
        # }
        # rank_res_dict = {
        # }
        for i in receipt_res:
            series.append(bar_charts)
            dimensions.append("%s-%s" % (i['month'], i['day']))
            receipt_res_dict.update({"%s-%s" % (i['month'], i['day']): i['number']})
        # for i in qty_res:
        #     qty_res_dict.update({i['goods_code']: i['number']})
        # for i in rank_res:
        #     rank_res_dict.update({i['goods_code']: i['number']})
        source.append(receipt_res_dict)
        # data_list.append(qty_res_dict)
        # data_list.append(rank_res_dict)
        dataset['source'] = source
        dataset['dimensions'] = dimensions
        context['dataset'] = dataset
        context['series'] = series
        return Response(context)


class OperationsBoardViewSet(viewsets.ViewSet):
    """Return the active warehouse work queue for the GreaterWMS dashboard."""

    def list(self, request, *args, **kwargs):
        auth = getattr(request, 'auth', None)
        openid = getattr(auth, 'openid', None)
        if not openid:
            return Response({'detail': 'auth required'}, status=401)

        now = timezone.now()
        items = []
        items.extend(self._inbound_items(openid, now))
        items.extend(self._outbound_items(openid, now))
        lane_order = {'blocked': 0, 'delayed': 1, 'now': 2, 'next': 3}
        items.sort(key=lambda item: (lane_order[item['lane']], item['sort_time']))

        counts = {
            'total': len(items),
            'now': sum(item['lane'] == 'now' for item in items),
            'next': sum(item['lane'] == 'next' for item in items),
            'delayed': sum(item['lane'] == 'delayed' for item in items),
            'blocked': sum(item['lane'] == 'blocked' for item in items),
        }
        for item in items:
            item.pop('sort_time', None)
        return Response({
            'generated_at': now.isoformat(),
            'items': items[:100],
            'counts': counts,
        })

    @staticmethod
    def _lane(eta, *, blocked, planned):
        if blocked:
            return 'blocked'
        if eta and timezone.now() > eta:
            return 'delayed'
        return 'next' if planned else 'now'

    @staticmethod
    def _timestamp(row):
        return row.update_time or row.create_time

    def _inbound_items(self, openid, now):
        status_map = {
            1: ('Unload', 'Stage', 'asn', True),
            2: ('Receive', 'Stage', 'predeliverystock', False),
            3: ('Inspect', 'Stage', 'presortstock', False),
            4: ('Putaway', 'Storage', 'sortstock', False),
        }
        grouped = {}
        eta_by_asn = dict(AsnListModel.objects.filter(
            openid=openid,
            is_delete=False,
        ).values_list('asn_code', 'expected_arrival_at'))
        rows = AsnDetailModel.objects.filter(
            openid=openid,
            asn_status__in=status_map.keys(),
            is_delete=False,
        ).order_by('-update_time', '-id')
        for row in rows:
            current = grouped.setdefault(row.asn_code, {
                'category': 'inbound',
                'reference': row.asn_code,
                'operation': 'Unload',
                'location': 'Stage',
                'action_route': 'asn',
                'status': 99,
                'quantity': 0,
                'progress_quantity': 0,
                'blocked': False,
                'timestamp': self._timestamp(row),
                'eta': eta_by_asn.get(row.asn_code),
            })
            if row.asn_status < current['status']:
                current['status'] = row.asn_status
            operation, location, route, planned = status_map[current['status']]
            current.update({
                'operation': operation,
                'location': location,
                'action_route': route,
                'planned': planned,
            })
            current['quantity'] += int(row.goods_qty or 0)
            current['progress_quantity'] += int(row.goods_actual_qty or row.sorted_qty or 0)
            current['blocked'] = current['blocked'] or any([
                row.goods_shortage_qty,
                row.goods_more_qty,
                row.goods_damage_qty,
            ])
            current['timestamp'] = max(current['timestamp'], self._timestamp(row))

        return [self._format_item(item, now) for item in grouped.values()]

    def _outbound_items(self, openid, now):
        status_map = {
            1: ('Release', 'Shipping', 'freshorder', True),
            2: ('Release', 'Shipping', 'neworder', True),
            3: ('Pick', 'Storage', 'pickstock', False),
            4: ('Pack', 'Shipping', 'pickedstock', False),
            5: ('Ship', 'Dock', 'shippedstock', False),
        }
        grouped = {}
        rows = DnDetailModel.objects.filter(
            openid=openid,
            dn_status__in=status_map.keys(),
            is_delete=False,
        ).order_by('-update_time', '-id')
        for row in rows:
            current = grouped.setdefault(row.dn_code, {
                'category': 'outbound',
                'reference': row.dn_code,
                'operation': 'Release',
                'location': 'Shipping',
                'action_route': 'neworder',
                'status': 99,
                'quantity': 0,
                'progress_quantity': 0,
                'blocked': False,
                'timestamp': self._timestamp(row),
                'eta': None,
            })
            if row.dn_status < current['status']:
                current['status'] = row.dn_status
            operation, location, route, planned = status_map[current['status']]
            current.update({
                'operation': operation,
                'location': location,
                'action_route': route,
                'planned': planned,
            })
            current['quantity'] += int(row.goods_qty or 0)
            current['progress_quantity'] += int(row.picked_qty or row.delivery_actual_qty or 0)
            current['blocked'] = current['blocked'] or bool(
                row.back_order_label or row.delivery_shortage_qty or row.delivery_more_qty or row.delivery_damage_qty
            )
            current['timestamp'] = max(current['timestamp'], self._timestamp(row))

        return [self._format_item(item, now) for item in grouped.values()]

    def _format_item(self, item, now):
        timestamp = item['timestamp']
        eta = item.get('eta')
        lane = self._lane(eta, blocked=item['blocked'], planned=item['planned'])
        quantity = item['quantity']
        progress = min(item['progress_quantity'], quantity)
        return {
            'id': '%s-%s' % (item['category'], item['reference']),
            'category': item['category'],
            'operation': item['operation'],
            'lane': lane,
            'reference': item['reference'],
            'location': item['location'],
            'quantity': max(quantity - progress, 0),
            'progress_quantity': progress,
            'total_quantity': quantity,
            'eta': timezone.localtime(eta).strftime('%m-%d %H:%M') if eta else '',
            'action_route': item['action_route'],
            'sort_time': timestamp or now,
        }
