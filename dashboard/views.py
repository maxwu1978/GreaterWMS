from rest_framework import viewsets
from asn.models import AsnDetailModel, AsnListModel
from dn.models import DnDetailModel, DnListModel, PickingListModel
from asn import serializers as asnserializers
from dn import serializers as dnserializers
from supplier.models import ListModel as SupplierModel
from supplier.shortname import generated_supplier_short_name
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
import math
from django.utils import timezone
from staging.models import StagingAssignment
from asnserial.views import _summary as receiving_summary
from driver.models import DispatchListModel
from receiving.models import ReceivingRecord
from transport.models import TransportOrder

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

    MANAGEMENT_ROLES = {'admin', 'manager', 'supervisor'}
    ETA_DUE_SOON_MINUTES = 120

    def list(self, request, *args, **kwargs):
        auth = getattr(request, 'auth', None)
        openid = getattr(auth, 'openid', None)
        if not openid:
            return Response({'detail': 'auth required'}, status=401)

        viewer_role = str(getattr(auth, 'staff_type', '') or '').strip().casefold()
        viewer_name = str(getattr(auth, 'staff_name', '') or '').strip()
        view = str(request.query_params.get('view') or 'active').strip().casefold()
        if view not in ('active', 'history'):
            return Response({'detail': 'view must be active or history'}, status=400)
        history = view == 'history'
        now = timezone.now()
        items = []
        items.extend(self._inbound_items(openid, now, history=history))
        items.extend(self._receiving_items(openid, now, history=history))
        items.extend(self._outbound_items(openid, now, history=history))
        items.extend(self._transport_items(openid, now, history=history))
        items = self._filter_for_identity(items, viewer_role, viewer_name, history=history)
        for item in items:
            self._decorate_action(item, viewer_role)
        lane_order = {
            'blocked': 0,
            'delayed': 1,
            'now': 2,
            'next': 3,
            'completed': 4,
            'cancelled': 5,
        }
        eta_order = {
            'OVERDUE': 0,
            'DUE_SOON': 1,
            'ON_TIME': 2,
            'NOT_PROVIDED': 3,
            'ARRIVED': 4,
            'COMPLETED': 5,
            'CANCELLED': 6,
        }
        items.sort(key=lambda item: (
            lane_order[item['lane']],
            eta_order.get(item.get('eta_status'), 3),
            item['sort_time'],
        ))

        counts = {
            'total': len(items),
            'now': sum(item['lane'] == 'now' for item in items),
            'next': sum(item['lane'] == 'next' for item in items),
            'delayed': sum(item['lane'] == 'delayed' for item in items),
            'blocked': sum(item['lane'] == 'blocked' for item in items),
            'urgent': sum(item['eta_status'] in ('DUE_SOON', 'OVERDUE') for item in items),
            'due_soon': sum(item['eta_status'] == 'DUE_SOON' for item in items),
            'overdue': sum(item['eta_status'] == 'OVERDUE' for item in items),
            'completed': sum(item['lane'] == 'completed' for item in items),
            'cancelled': sum(item['lane'] == 'cancelled' for item in items),
        }
        for item in items:
            item.pop('sort_time', None)
        try:
            limit = min(max(int(request.query_params.get('limit', 100)), 1), 500)
        except (TypeError, ValueError):
            return Response({'detail': 'limit must be an integer'}, status=400)
        try:
            offset = max(int(request.query_params.get('offset', 0)), 0)
        except (TypeError, ValueError):
            return Response({'detail': 'offset must be an integer'}, status=400)
        total = len(items)
        return Response({
            'generated_at': now.isoformat(),
            'view': view,
            'viewer': {
                'staff_name': viewer_name,
                'staff_type': getattr(auth, 'staff_type', '') or '',
                'scope': 'all' if viewer_role in self.MANAGEMENT_ROLES else 'role',
            },
            'items': items[offset:offset + limit],
            'offset': offset,
            'limit': limit,
            'has_more': offset + limit < total,
            'total': total,
            'counts': counts,
        })

    @staticmethod
    def _action_code(operation):
        return {
            'Reserve Stage': 'reserve_stage',
            'Await Arrival': 'await_arrival',
            'Assign Unloading Driver': 'assign_unloading_driver',
            'Unload': 'unload',
            'Receive': 'receive',
            'Inspect': 'inspect',
            'Review QC': 'review_qc',
            'Assign Putaway Driver': 'assign_putaway_driver',
            'Putaway': 'putaway',
            'Reconcile ASN': 'reconcile_asn',
            'Resolve Reconciliation': 'resolve_reconciliation',
            'Resolve QC Exception': 'resolve_qc_exception',
            'Close Receipt': 'close_receipt',
            'Release': 'release',
            'Pick': 'pick',
            'Pack': 'pack',
            'Ship': 'ship',
            'Assign Driver': 'assign_driver',
            'Transport': 'transport',
            'Confirm Delivery': 'confirm_delivery',
            'Completed': 'completed',
            'Cancelled': 'cancelled',
        }.get(operation, str(operation or '').strip().lower().replace(' ', '_'))

    @classmethod
    def _decorate_action(cls, item, viewer_role):
        action_code = cls._action_code(item.get('operation'))
        assigned_role = str(item.get('assigned_role') or '').casefold()
        category = item.get('category')
        can_act = viewer_role in cls.MANAGEMENT_ROLES or viewer_role == assigned_role
        if viewer_role == 'inbound' and category in ('inbound', 'receiving'):
            can_act = True
        elif viewer_role == 'outbound' and category == 'outbound':
            can_act = True
        elif viewer_role == 'logistics' and category == 'transport':
            can_act = True
        item['action_code'] = action_code
        item['available_actions'] = [action_code] if can_act and action_code not in ('completed', 'cancelled') else []
        item['can_act'] = bool(item['available_actions'])

    def _filter_for_identity(self, items, viewer_role, viewer_name, history=False):
        """Keep the dashboard server-side scoped to the logged-in role."""
        if viewer_role in self.MANAGEMENT_ROLES:
            return items
        if history:
            def has_role(item, role):
                return role in set(item.get('history_roles') or [])

            if viewer_role == 'driver':
                return [
                    item for item in items
                    if has_role(item, 'DRIVER')
                    and viewer_name.casefold() in {
                        str(name).casefold() for name in item.get('history_assignees') or []
                    }
                ]
            if viewer_role == 'qc':
                return [item for item in items if has_role(item, 'QC')]
            if viewer_role == 'warehouse':
                return [item for item in items if has_role(item, 'WAREHOUSE')]
            if viewer_role == 'logistics':
                return [item for item in items if has_role(item, 'LOGISTICS')]
            if viewer_role == 'inbound':
                return [item for item in items if item.get('category') in ('inbound', 'receiving')]
            if viewer_role == 'outbound':
                return [item for item in items if item.get('category') == 'outbound']
            if viewer_role == 'stockcontrol':
                return [item for item in items if has_role(item, 'WAREHOUSE')]
            return []
        if viewer_role == 'driver':
            return [
                item for item in items
                if item.get('assigned_role') == 'DRIVER'
                and str(item.get('assignee_name') or '').casefold() == viewer_name.casefold()
            ]
        if viewer_role == 'qc':
            return [item for item in items if item.get('assigned_role') == 'QC']
        if viewer_role == 'warehouse':
            return [item for item in items if item.get('assigned_role') == 'WAREHOUSE']
        if viewer_role == 'inbound':
            return [item for item in items if item.get('category') in ('inbound', 'receiving')]
        if viewer_role == 'outbound':
            return [item for item in items if item.get('category') == 'outbound']
        if viewer_role == 'logistics':
            return [
                item for item in items
                if item.get('assigned_role') == 'LOGISTICS'
                or item.get('category') == 'transport'
            ]
        if viewer_role == 'stockcontrol':
            return [item for item in items if item.get('assigned_role') in ('WAREHOUSE', 'QC')]
        return []

    @staticmethod
    def _align_datetimes(left, right):
        """Make naive and aware datetimes comparable without changing the instant."""
        if timezone.is_naive(left) == timezone.is_naive(right):
            return left, right
        current_timezone = timezone.get_current_timezone()
        if timezone.is_naive(left):
            left = timezone.make_aware(left, current_timezone)
        if timezone.is_naive(right):
            right = timezone.make_aware(right, current_timezone)
        return left, right

    @classmethod
    def _eta_status(cls, eta, now, *, actual_arrival_at=None, business_status='', history=False):
        if history:
            return ('CANCELLED' if business_status == 'CANCELLED' else 'COMPLETED', None)
        if actual_arrival_at or business_status == 'ARRIVED':
            return 'ARRIVED', None
        if not eta:
            return 'NOT_PROVIDED', None
        eta, now = cls._align_datetimes(eta, now)
        seconds = (eta - now).total_seconds()
        if seconds < 0:
            minutes = -int(math.ceil(abs(seconds) / 60))
            return 'OVERDUE', minutes
        minutes = int(math.ceil(seconds / 60))
        if minutes <= cls.ETA_DUE_SOON_MINUTES:
            return 'DUE_SOON', minutes
        return 'ON_TIME', minutes

    @classmethod
    def _lane(cls, eta, *, blocked, planned, now=None):
        if blocked:
            return 'blocked'
        if eta:
            now = now or timezone.now()
            eta, now = cls._align_datetimes(eta, now)
        if eta and now > eta:
            return 'delayed'
        return 'next' if planned else 'now'

    @staticmethod
    def _timestamp(row):
        return row.update_time or row.create_time

    def _inbound_items(self, openid, now, history=False):
        status_map = {
            1: ('Unload', 'Stage', 'asn', True),
            2: ('Receive', 'Stage', 'predeliverystock', False),
            3: ('Inspect', 'Stage', 'presortstock', False),
            4: ('Putaway', 'Storage', 'sortstock', False),
        }
        business_status_map = {
            1: 'PRE_ARRIVAL',
            2: 'UNLOADING',
            3: 'RECEIVING_REVIEW',
            4: 'PUTAWAY',
            5: 'COMPLETED',
        }
        if history:
            status_map[5] = ('Completed', 'Storage', 'asnfinish', False)
        grouped = {}
        asn_context = {
            row['asn_code']: row for row in AsnListModel.objects.filter(
            openid=openid,
            is_delete=False,
        ).values(
            'asn_code', 'expected_arrival_at', 'actual_arrival_at', 'package_qty',
            'unload_driver', 'putaway_driver',
        )
        }
        staging_context = {}
        for assignment in StagingAssignment.objects.filter(
            openid=openid,
            flow=StagingAssignment.INBOUND,
            status__in=(StagingAssignment.RESERVED, StagingAssignment.ACTIVE),
        ).only('reference_code', 'status', 'bin_name'):
            summary = staging_context.setdefault(assignment.reference_code, {
                'reserved': 0,
                'occupied': 0,
                'reserved_bins': [],
                'occupied_bins': [],
            })
            if assignment.status == StagingAssignment.RESERVED:
                summary['reserved'] += 1
                if assignment.bin_name not in summary['reserved_bins']:
                    summary['reserved_bins'].append(assignment.bin_name)
            else:
                summary['occupied'] += 1
                if assignment.bin_name not in summary['occupied_bins']:
                    summary['occupied_bins'].append(assignment.bin_name)
        linked_receipt_asns = set(ReceivingRecord.objects.filter(
            openid=openid,
        ).exclude(
            status=ReceivingRecord.CANCELLED,
        ).exclude(
            linked_asn_code='',
        ).values_list('linked_asn_code', flat=True))
        history_statuses = (5,) if history else tuple(status_map.keys())
        rows = list(AsnDetailModel.objects.filter(
            openid=openid,
            asn_status__in=history_statuses,
            is_delete=False,
        ).exclude(asn_code__in=linked_receipt_asns).order_by('-update_time', '-id'))
        asn_codes = {row.asn_code for row in rows}
        asn_models = {
            asn.asn_code: asn
            for asn in AsnListModel.objects.filter(
                openid=openid,
                asn_code__in=asn_codes,
                is_delete=False,
            )
        }
        asn_display_cache = {}
        supplier_names = {row.supplier for row in rows if row.supplier}
        supplier_short_names = dict(SupplierModel.objects.filter(
            openid=openid,
            supplier_name__in=supplier_names,
            is_delete=False,
        ).values_list('supplier_name', 'supplier_short_name'))
        for row in rows:
            customer_name = row.supplier or ''
            intake = asn_context.get(row.asn_code, {})
            staging = staging_context.get(row.asn_code, {
                'reserved': 0,
                'occupied': 0,
                'reserved_bins': [],
                'occupied_bins': [],
            })
            current = grouped.setdefault(row.asn_code, {
                'category': 'inbound',
                'reference': row.asn_code,
                'customer': supplier_short_names.get(customer_name) or generated_supplier_short_name(customer_name),
                'customer_short_name': supplier_short_names.get(customer_name) or generated_supplier_short_name(customer_name),
                'customer_full_name': customer_name,
                'operation': 'Reserve Stage',
                'location': 'Stage',
                'action_route': 'asn',
                'status': 99,
                'quantity': 0,
                'progress_quantity': 0,
                'blocked': False,
                'timestamp': self._timestamp(row),
                'eta': intake.get('expected_arrival_at'),
                'actual_arrival_at': intake.get('actual_arrival_at'),
                'unload_driver': intake.get('unload_driver') or '',
                'putaway_driver': intake.get('putaway_driver') or '',
                'staging_reserved_qty': staging['reserved'],
                'staging_occupied_qty': staging['occupied'],
                'staging_reserved_bins': staging['reserved_bins'],
                'staging_occupied_bins': staging['occupied_bins'],
                'package_qty': intake.get('package_qty') or 0,
                'container_tracking': intake.get('container_tracking') or '',
                'source_location': 'Dock',
                'target_location': 'Stage',
                'task_qty': 0,
                'task_total_qty': 0,
                'acceptance_summary': {},
                'exception_summary': '',
                'blocking_reason': '',
                'history': history,
                'history_roles': [],
                'history_assignees': [],
            })
            if row.asn_status < current['status']:
                current['status'] = row.asn_status
            operation, location, route, planned = status_map[current['status']]
            current.update({
                'operation': operation,
                'location': location,
                'action_route': route,
                'planned': planned,
                'business_status': business_status_map[current['status']],
            })
            if current['status'] == 1:
                if current['actual_arrival_at'] and current['unload_driver']:
                    current.update({'operation': 'Unload', 'planned': False, 'business_status': 'UNLOADING'})
                elif current['actual_arrival_at']:
                    current.update({
                        'operation': 'Assign Unloading Driver',
                        'planned': False,
                        'business_status': 'AWAITING_UNLOADING_DRIVER',
                    })
                elif current['staging_reserved_qty']:
                    current.update({'operation': 'Await Arrival', 'planned': True})
                else:
                    current.update({'operation': 'Reserve Stage', 'planned': True})
            elif current['status'] == 4 and current['putaway_driver']:
                current.update({
                    'operation': 'Putaway',
                    'planned': False,
                    'business_status': 'PUTAWAY_PENDING',
                })
            elif current['status'] == 4:
                current.update({
                    'operation': 'Assign Putaway Driver',
                    'planned': False,
                    'business_status': 'PUTAWAY_PENDING',
                })
            if current['status'] == 1 and current['actual_arrival_at'] and current['unload_driver']:
                current.update({'assigned_role': 'DRIVER', 'assignee_name': current['unload_driver']})
            elif current['status'] == 3:
                current.update({'assigned_role': 'QC', 'assignee_name': ''})
            elif current['status'] == 4 and current['putaway_driver']:
                current.update({'assigned_role': 'DRIVER', 'assignee_name': current['putaway_driver']})
            else:
                current.update({'assigned_role': 'WAREHOUSE', 'assignee_name': ''})
            current['quantity'] += int(row.goods_qty or 0)
            current['progress_quantity'] += int(row.goods_actual_qty or row.sorted_qty or 0)
            current['blocked'] = current['blocked'] or any([
                row.goods_shortage_qty,
                row.goods_more_qty,
                row.goods_damage_qty,
            ])
            current['timestamp'] = max(current['timestamp'], self._timestamp(row))

        summary_cache = {}
        for item in grouped.values():
            received_qty = int(item.get('progress_quantity') or 0)
            expected_qty = int(item.get('quantity') or 0)
            sorted_qty = 0
            if item['status'] == 3:
                item['task_qty'] = received_qty
                item['task_total_qty'] = expected_qty
                item['source_location'] = 'Stage'
                item['target_location'] = 'Stage / QC'
            elif item['status'] == 4:
                sorted_qty = sum(
                    int(row.sorted_qty or 0)
                    for row in AsnDetailModel.objects.filter(
                        openid=openid,
                        asn_code=item['reference'],
                        is_delete=False,
                    )
                )
                item['task_qty'] = max(received_qty - sorted_qty, 0)
                item['task_total_qty'] = received_qty
                item['source_location'] = 'Stage'
                item['target_location'] = 'Storage'
            else:
                item['task_qty'] = max(expected_qty - received_qty, 0)
                item['task_total_qty'] = expected_qty
                if item['status'] == 1 and item.get('actual_arrival_at'):
                    item['source_location'] = 'Dock'
                item['target_location'] = (
                    ', '.join(item.get('staging_occupied_bins') or item.get('staging_reserved_bins') or [])
                    or 'Stage'
                )
            if item.get('staging_occupied_bins'):
                item['target_location'] = ', '.join(item['staging_occupied_bins'])
            elif item.get('staging_reserved_bins') and item['status'] <= 2:
                item['target_location'] = ', '.join(item['staging_reserved_bins'])
            item['location_summary'] = '%s -> %s' % (
                item['source_location'],
                item['target_location'],
            )
            if history:
                roles = {'WAREHOUSE'}
                assignees = []
                if item.get('status', 0) >= 3:
                    roles.add('QC')
                if item.get('unload_driver'):
                    roles.add('DRIVER')
                    assignees.append(item['unload_driver'])
                if item.get('putaway_driver'):
                    roles.add('DRIVER')
                    assignees.append(item['putaway_driver'])
                item.update({
                    'operation': 'Completed',
                    'business_status': 'EXCEPTION' if item.get('blocked') else 'COMPLETED',
                    'history_roles': sorted(roles),
                    'history_assignees': assignees,
                })
            if item['status'] in (3, 4):
                summary = summary_cache.setdefault(
                    item['reference'],
                    receiving_summary(openid, item['reference']),
                )
                receiving_data = summary.get('receiving_summary') or {}
                item['acceptance_summary'] = {
                    'pack_list_status': summary.get('pack_list_status', 'NOT_RECEIVED'),
                    'pack_list_timing': summary.get('pack_list_timing', 'NOT_RECEIVED'),
                    'verification_mode': summary.get('verification_mode', 'ASN_ONLY'),
                    'qc_status': summary.get('qc_status', 'NOT_STARTED'),
                    'expected_qty': item['quantity'],
                    'received_qty': summary.get('total_received_qty', item['progress_quantity']),
                    'scanned_qty': receiving_data.get('scanned', summary.get('total_received_serials', 0)),
                    'accepted_qty': receiving_data.get('accepted_for_putaway', summary.get('total_accepted_for_putaway', 0)),
                    'repair_qty': receiving_data.get('repair_qty', summary.get('total_repair_serials', 0)),
                    'rejected_qty': receiving_data.get('rejected_qty', summary.get('total_rejected_serials', 0)),
                    'open_exception_qty': receiving_data.get('open_exceptions', summary.get('total_exception_serials', 0)),
                }
                item['exception_summary'] = (
                    'QC review required' if not summary.get('qc_complete', False) else ''
                )
                if item['status'] == 4:
                    item['blocking_reason'] = item['exception_summary']
                if not summary.get('ready_for_putaway', False):
                    item.update({
                        'operation': 'Review QC',
                        'location': 'Stage',
                        'action_route': 'asn',
                        'planned': False,
                        'blocked': True,
                        'business_status': 'RECEIVING_REVIEW',
                        'assigned_role': 'QC',
                        'assignee_name': '',
                    })
                    item['blocking_reason'] = 'QC review required'

            # Match the ASN page's authoritative display fields. Keep the
            # legacy operation for role/action routing, but do not expose a
            # second status or next-step vocabulary on the dashboard.
            if not history:
                asn_obj = asn_models.get(item['reference'])
                if asn_obj:
                    display = asn_display_cache.setdefault(
                        item['reference'],
                        asnserializers.ASNListGetSerializer(asn_obj, context={}).data,
                    )
                    item['customer_short_name'] = display.get('supplier_short_name') or item.get('customer_short_name', '')
                    item['operational_status'] = display.get('operational_status') or item.get('business_status', '')
                    item['operational_status_reason'] = display.get('operational_status_reason', '')
                    item['next_action_code'] = display.get('next_action_code', '')
                    item['next_action_label'] = display.get('next_action_label', '')
                    item['pack_list_status'] = display.get('pack_list_status', 'NOT_RECEIVED')
                    item['serial_acceptance'] = display.get('serial_acceptance') or {}
                    item['business_status'] = item['operational_status']

            if item.get('blocked') and not item.get('blocking_reason'):
                item['blocking_reason'] = 'Quantity or damage exception'

        return [self._format_item(item, now) for item in grouped.values()]

    def _receiving_items(self, openid, now, history=False):
        records = ReceivingRecord.objects.filter(
            openid=openid,
        )
        if history:
            records = records.filter(status__in=(ReceivingRecord.CLOSED, ReceivingRecord.CANCELLED))
        else:
            records = records.exclude(status__in=(ReceivingRecord.CLOSED, ReceivingRecord.CANCELLED))
        records = list(records)
        customer_names = {record.customer for record in records if record.customer}
        customer_short_names = dict(SupplierModel.objects.filter(
            openid=openid,
            supplier_name__in=customer_names,
            is_delete=False,
        ).values_list('supplier_name', 'supplier_short_name'))
        items = []
        reconciliation_status_map = {
            ReceivingRecord.NO_ASN: 'AWAITING_ASN',
            ReceivingRecord.PENDING: 'RECONCILIATION_PENDING',
            ReceivingRecord.MATCHED: 'MATCHED',
            ReceivingRecord.EXCEPTION: 'EXCEPTION',
            ReceivingRecord.RESOLVED: 'RESOLVED',
            ReceivingRecord.DISPUTED: 'DISPUTED',
        }
        for record in records:
            business_reconciliation_status = reconciliation_status_map.get(
                record.reconciliation_status,
                record.reconciliation_status,
            )
            details = list(record.details.all())
            physical_total = sum(int(detail.actual_qty or 0) for detail in details)
            accepted_total = sum(int(detail.accepted_qty or 0) for detail in details)
            total = accepted_total if record.status == ReceivingRecord.PUTAWAY_PENDING else physical_total
            progress = sum(int(detail.putaway_qty or 0) for detail in details)
            if record.status in (ReceivingRecord.QC_PENDING, ReceivingRecord.QC_EXCEPTION):
                task_qty = physical_total
                task_total_qty = physical_total
            elif record.status == ReceivingRecord.PUTAWAY_PENDING:
                task_qty = max(accepted_total - progress, 0)
                task_total_qty = accepted_total
            else:
                task_qty = max(physical_total - progress, 0)
                task_total_qty = physical_total
            assignee = ''
            if history:
                operation = 'Cancelled' if record.status == ReceivingRecord.CANCELLED else 'Completed'
                role = 'DRIVER' if record.putaway_driver else 'QC' if record.qc_by else 'WAREHOUSE'
                assignee = record.putaway_driver or record.qc_by or record.closed_by or ''
                blocked = record.status == ReceivingRecord.CANCELLED
                planned = False
            elif record.status == ReceivingRecord.QC_PENDING:
                operation, role, blocked, planned = 'Inspect', 'QC', False, False
            elif record.status == ReceivingRecord.QC_EXCEPTION:
                operation, role, blocked, planned = 'Resolve QC Exception', 'QC', True, False
            elif record.status == ReceivingRecord.PUTAWAY_PENDING:
                if record.putaway_driver:
                    operation, role, blocked, planned = 'Putaway', 'DRIVER', False, False
                    assignee = record.putaway_driver
                else:
                    operation, role, blocked, planned = 'Assign Putaway Driver', 'WAREHOUSE', False, False
                    assignee = ''
            elif record.reconciliation_status in (ReceivingRecord.EXCEPTION, ReceivingRecord.DISPUTED):
                operation, role, blocked, planned = 'Resolve Reconciliation', 'WAREHOUSE', True, False
                assignee = ''
            elif record.reconciliation_status == ReceivingRecord.NO_ASN:
                operation, role, blocked, planned = 'Await ASN', 'WAREHOUSE', False, True
                assignee = ''
            elif record.reconciliation_status == ReceivingRecord.PENDING:
                operation, role, blocked, planned = 'Reconcile ASN', 'WAREHOUSE', False, False
                assignee = ''
            else:
                operation, role, blocked, planned = 'Close Receipt', 'WAREHOUSE', False, False
                assignee = ''
            history_roles = {'WAREHOUSE'}
            history_assignees = []
            if record.qc_by:
                history_roles.add('QC')
            if record.putaway_driver:
                history_roles.add('DRIVER')
                history_assignees.append(record.putaway_driver)
            detail_exceptions = [
                str(detail.exception_note or '').strip()
                for detail in details
                if str(detail.exception_note or '').strip()
            ]
            exception_summary = str(record.exception_note or '').strip() or (
                '; '.join(detail_exceptions[:2])
            )
            if record.status == ReceivingRecord.QC_EXCEPTION and not exception_summary:
                exception_summary = 'QC exception requires resolution'
            if record.reconciliation_status in (ReceivingRecord.EXCEPTION, ReceivingRecord.DISPUTED) and not exception_summary:
                exception_summary = 'ASN reconciliation requires resolution'
            if record.status in (ReceivingRecord.QC_PENDING, ReceivingRecord.QC_EXCEPTION):
                source_location, target_location = 'Stage', 'Stage / QC'
            elif record.status == ReceivingRecord.PUTAWAY_PENDING:
                target_bins = sorted({detail.bin_name for detail in details if detail.bin_name})
                source_location, target_location = 'Stage', ', '.join(target_bins) or 'Storage'
            else:
                source_location, target_location = 'Dock', 'Stage'
            items.append(self._format_item({
                'category': 'receiving',
                'reference': record.receipt_no,
                'customer': customer_short_names.get(record.customer) or generated_supplier_short_name(record.customer),
                'customer_short_name': customer_short_names.get(record.customer) or generated_supplier_short_name(record.customer),
                'customer_full_name': record.customer,
                'operation': operation,
                'location': 'Stage' if progress < total else 'Storage',
                'action_route': 'receiving',
                'status': record.status,
                'reconciliation_status': record.reconciliation_status,
                'quantity': total,
                'progress_quantity': progress,
                'task_qty': task_qty,
                'task_total_qty': task_total_qty,
                'blocked': blocked,
                'planned': planned,
                'timestamp': record.update_time or record.create_time,
                'eta': None,
                'assigned_role': role,
                'assignee_name': assignee,
                'exception_note': record.exception_note,
                'exception_summary': exception_summary,
                'blocking_reason': exception_summary if blocked else '',
                'source_location': source_location,
                'target_location': target_location,
                'location_summary': '%s -> %s' % (source_location, target_location),
                'linked_reference': record.linked_asn_code,
                'acceptance_summary': {
                    'expected_qty': sum(int(detail.expected_qty or 0) for detail in details),
                    'received_qty': physical_total,
                    'accepted_qty': accepted_total,
                    'putaway_qty': progress,
                    'repair_qty': sum(int(detail.hold_qty or 0) for detail in details),
                    'rejected_qty': sum(int(detail.rejected_qty or 0) for detail in details),
                    'open_exception_qty': sum(
                        int(detail.damage_qty or 0) + int(detail.hold_qty or 0) + int(detail.rejected_qty or 0)
                        for detail in details
                    ),
                },
                'business_status': (
                    'CANCELLED' if record.status == ReceivingRecord.CANCELLED else
                    'RESOLVED' if history and record.reconciliation_status == ReceivingRecord.RESOLVED else
                    'MATCHED' if history and record.reconciliation_status == ReceivingRecord.MATCHED else
                    record.reconciliation_status if history and record.reconciliation_status in (
                        ReceivingRecord.EXCEPTION,
                        ReceivingRecord.DISPUTED,
                    ) else
                    'COMPLETED' if history else
                    business_reconciliation_status if record.status == ReceivingRecord.PUTAWAY_COMPLETE else
                    record.status
                ),
                'history': history,
                'history_roles': sorted(history_roles),
                'history_assignees': history_assignees,
            }, now))
        return items

    def _transport_items(self, openid, now, history=False):
        business_status_map = {
            TransportOrder.REQUESTED: 'REQUESTED',
            TransportOrder.SCHEDULED: 'SCHEDULED',
            TransportOrder.DRIVER_ASSIGNED: 'DRIVER_ASSIGNED',
            TransportOrder.IN_TRANSIT: 'IN_TRANSIT',
            TransportOrder.ARRIVED: 'ARRIVED',
            TransportOrder.COMPLETED: 'COMPLETED',
            TransportOrder.CANCELLED: 'CANCELLED',
        }
        orders = TransportOrder.objects.filter(openid=openid).exclude(
            status__in=(TransportOrder.COMPLETED, TransportOrder.CANCELLED),
        )
        if history:
            orders = TransportOrder.objects.filter(
                openid=openid,
                status__in=(TransportOrder.COMPLETED, TransportOrder.CANCELLED),
            )
        orders = list(orders)
        customer_names = {order.customer for order in orders if order.customer}
        customer_short_names = dict(SupplierModel.objects.filter(
            openid=openid,
            supplier_name__in=customer_names,
            is_delete=False,
        ).values_list('supplier_name', 'supplier_short_name'))
        items = []
        for order in orders:
            if history:
                operation = 'Cancelled' if order.status == TransportOrder.CANCELLED else 'Completed'
                role = 'LOGISTICS'
                assignee = order.driver_name
                planned = False
            elif order.status in (TransportOrder.REQUESTED, TransportOrder.SCHEDULED):
                operation, role, assignee, planned = 'Assign Driver', 'LOGISTICS', order.logistics_coordinator, False
            elif order.status in (TransportOrder.DRIVER_ASSIGNED, TransportOrder.IN_TRANSIT):
                operation, role, assignee, planned = 'Transport', 'DRIVER', order.driver_name, False
            else:
                operation, role, assignee, planned = 'Confirm Delivery', 'LOGISTICS', order.logistics_coordinator, False
            history_roles = {'LOGISTICS'}
            history_assignees = []
            if order.driver_name:
                history_roles.add('DRIVER')
                history_assignees.append(order.driver_name)
            source_location = order.pickup_location or 'Dock'
            target_location = order.delivery_location or 'Dock'
            items.append(self._format_item({
                'category': 'transport',
                'reference': order.transport_no,
                'customer': customer_short_names.get(order.customer) or generated_supplier_short_name(order.customer),
                'customer_short_name': customer_short_names.get(order.customer) or generated_supplier_short_name(order.customer),
                'customer_full_name': order.customer,
                'operation': operation,
                'location': order.delivery_location or order.pickup_location or 'Dock',
                'action_route': 'transport',
                'status': order.status,
                'quantity': 0,
                'progress_quantity': 0,
                'task_qty': 0,
                'task_total_qty': 0,
                'blocked': False,
                'planned': planned,
                'timestamp': order.update_time or order.create_time,
                'eta': order.eta,
                'assigned_role': role,
                'assignee_name': assignee or '',
                'exception_note': order.note,
                'exception_summary': order.note or '',
                'source_location': source_location,
                'target_location': target_location,
                'location_summary': '%s -> %s' % (source_location, target_location),
                'linked_reference': order.reference_no,
                'business_status': business_status_map.get(order.status, order.status),
                'history': history,
                'history_roles': sorted(history_roles),
                'history_assignees': history_assignees,
            }, now))
        return items

    def _outbound_items(self, openid, now, history=False):
        status_map = {
            1: ('Release', 'Shipping', 'freshorder', True),
            2: ('Release', 'Shipping', 'neworder', True),
            3: ('Pick', 'Storage', 'pickstock', False),
            4: ('Pack', 'Shipping', 'pickedstock', False),
            5: ('Ship', 'Dock', 'shippedstock', False),
        }
        business_status_map = {
            1: 'RELEASED',
            2: 'RELEASED',
            3: 'PICKING',
            4: 'PACKING',
            5: 'IN_TRANSIT',
            6: 'COMPLETED',
            7: 'CANCELLED',
        }
        if history:
            status_map.update({
                6: ('Completed', 'Dock', 'shippedstock', False),
                7: ('Cancelled', 'Dock', 'neworder', False),
            })
        grouped = {}
        history_statuses = (6, 7) if history else tuple(status_map.keys())
        rows = list(DnDetailModel.objects.filter(
            openid=openid,
            dn_status__in=history_statuses,
            is_delete=False,
        ).order_by('-update_time', '-id'))
        customer_names = {row.customer for row in rows if row.customer}
        customer_short_names = dict(SupplierModel.objects.filter(
            openid=openid,
            supplier_name__in=customer_names,
            is_delete=False,
        ).values_list('supplier_name', 'supplier_short_name'))
        dn_codes = {row.dn_code for row in rows}
        dn_context = {
            row.dn_code: row for row in DnListModel.objects.filter(
                openid=openid,
                dn_code__in=dn_codes,
                is_delete=False,
            ).only('dn_code', 'picking_mode', 'transport_required', 'transport_order_no', 'ship_to')
        }
        picking_context = {}
        for picking in PickingListModel.objects.filter(
            openid=openid,
            dn_code__in=dn_codes,
        ).only('dn_code', 'bin_name'):
            bins = picking_context.setdefault(picking.dn_code, [])
            if picking.bin_name and picking.bin_name not in bins:
                bins.append(picking.bin_name)
        dispatch_context = {}
        for dispatch in DispatchListModel.objects.filter(
            openid=openid,
            dn_code__in=dn_codes,
        ).order_by('dn_code', 'id').values('dn_code', 'driver_name', 'staging_bin'):
            # Keep the latest dispatch record when a DN was reassigned.
            dispatch_context[dispatch['dn_code']] = {
                'driver_name': str(dispatch.get('driver_name') or ''),
                'staging_bin': str(dispatch.get('staging_bin') or ''),
            }
        for row in rows:
            customer_name = row.customer or ''
            dn = dn_context.get(row.dn_code)
            dispatch = dispatch_context.get(row.dn_code, {})
            current = grouped.setdefault(row.dn_code, {
                'category': 'outbound',
                'reference': row.dn_code,
                'customer': customer_short_names.get(customer_name) or generated_supplier_short_name(customer_name),
                'customer_short_name': customer_short_names.get(customer_name) or generated_supplier_short_name(customer_name),
                'customer_full_name': customer_name,
                'operation': 'Release',
                'location': 'Shipping',
                'action_route': 'neworder',
                'status': 99,
                'quantity': 0,
                'progress_quantity': 0,
                'blocked': False,
                'timestamp': self._timestamp(row),
                'eta': None,
                'driver_name': dispatch.get('driver_name', ''),
                'staging_bin': dispatch.get('staging_bin', ''),
                'picking_mode': dn.picking_mode if dn else DnListModel.SKU_QTY,
                'transport_required': bool(dn.transport_required) if dn else False,
                'linked_reference': dn.transport_order_no if dn else '',
                'ship_to': dn.ship_to if dn else '',
                'picking_bins': picking_context.get(row.dn_code, []),
                'picked_qty': 0,
                'intransit_qty': 0,
                'delivery_actual_qty': 0,
                'requested_serials': 0,
                'picked_serials': 0,
                'shipped_serials': 0,
                'source_location': 'Storage',
                'target_location': 'Shipping',
                'task_qty': 0,
                'task_total_qty': 0,
                'exception_summary': '',
                'blocking_reason': '',
                'history': history,
                'history_roles': [],
                'history_assignees': [],
            })
            if row.dn_status < current['status']:
                current['status'] = row.dn_status
            operation, location, route, planned = status_map[current['status']]
            current.update({
                'operation': operation,
                'location': location,
                'action_route': route,
                'planned': planned,
                'business_status': business_status_map[current['status']],
            })
            if current['status'] == 5 and current['driver_name']:
                current.update({'assigned_role': 'DRIVER', 'assignee_name': current['driver_name']})
            else:
                current.update({'assigned_role': 'WAREHOUSE', 'assignee_name': ''})
            current['quantity'] += int(row.goods_qty or 0)
            current['progress_quantity'] += int(row.picked_qty or row.delivery_actual_qty or 0)
            current['picked_qty'] += int(row.picked_qty or 0)
            current['intransit_qty'] += int(row.intransit_qty or 0)
            current['delivery_actual_qty'] += int(row.delivery_actual_qty or 0)
            current['requested_serials'] += len(row.requested_serials or [])
            current['picked_serials'] += len(row.picked_serials or [])
            current['shipped_serials'] += len(row.shipped_serials or [])
            current['blocked'] = current['blocked'] or bool(
                row.back_order_label or row.delivery_shortage_qty or row.delivery_more_qty or row.delivery_damage_qty
            )
            current['exception_summary'] = current['exception_summary'] or str(row.delivery_note or '').strip()
            current['timestamp'] = max(current['timestamp'], self._timestamp(row))

        transport_context = {
            order.transport_no: order
            for order in TransportOrder.objects.filter(
                openid=openid,
                transport_no__in={item.get('linked_reference') for item in grouped.values() if item.get('linked_reference')},
            ).only('transport_no', 'eta', 'appointment_at', 'reference_no')
        }
        for item in grouped.values():
            expected_qty = int(item.get('quantity') or 0)
            picked_qty = int(item.get('picked_qty') or 0)
            intransit_qty = int(item.get('intransit_qty') or 0)
            actual_qty = int(item.get('delivery_actual_qty') or 0)
            if item['status'] <= 2:
                item['task_qty'] = expected_qty
                item['task_total_qty'] = expected_qty
                item['source_location'] = ', '.join(item.get('picking_bins') or []) or 'Storage'
                item['target_location'] = item.get('staging_bin') or 'Shipping'
            elif item['status'] == 3:
                item['task_qty'] = max(expected_qty - picked_qty, 0)
                item['task_total_qty'] = expected_qty
                item['source_location'] = ', '.join(item.get('picking_bins') or []) or 'Storage'
                item['target_location'] = item.get('staging_bin') or 'Shipping'
            elif item['status'] == 4:
                item['task_qty'] = max(picked_qty - intransit_qty, 0)
                item['task_total_qty'] = picked_qty or expected_qty
                item['source_location'] = 'Storage'
                item['target_location'] = item.get('staging_bin') or 'Shipping'
            else:
                item['task_qty'] = max(intransit_qty - actual_qty, 0)
                item['task_total_qty'] = intransit_qty or expected_qty
                item['source_location'] = item.get('staging_bin') or 'Shipping'
                item['target_location'] = item.get('ship_to') or 'Customer'
            item['location_summary'] = '%s -> %s' % (
                item['source_location'],
                item['target_location'],
            )
            if item.get('linked_reference'):
                transport = transport_context.get(item['linked_reference'])
                if transport:
                    item['eta'] = transport.eta or transport.appointment_at
                    item['linked_reference'] = transport.reference_no or item['linked_reference']
            item['acceptance_summary'] = {
                'picking_mode': item.get('picking_mode', DnListModel.SKU_QTY),
                'requested_serials': item.get('requested_serials', 0),
                'picked_serials': item.get('picked_serials', 0),
                'shipped_serials': item.get('shipped_serials', 0),
            }
            if item.get('blocked') and not item.get('exception_summary'):
                item['exception_summary'] = 'Outbound quantity or delivery exception'
            if item.get('blocked'):
                item['blocking_reason'] = item['exception_summary']

        if history:
            for item in grouped.values():
                roles = {'WAREHOUSE'}
                assignees = []
                if item.get('driver_name'):
                    roles.add('DRIVER')
                    assignees.append(item['driver_name'])
                item.update({
                    'operation': 'Cancelled' if item['status'] == 7 else 'Completed',
                    'business_status': (
                        'CANCELLED' if item['status'] == 7 else
                        'EXCEPTION' if item.get('blocked') else
                        'COMPLETED'
                    ),
                    'history_roles': sorted(roles),
                    'history_assignees': assignees,
                })
        return [self._format_item(item, now) for item in grouped.values()]

    def _format_item(self, item, now):
        timestamp = item['timestamp']
        eta = item.get('eta')
        if item.get('history'):
            lane = 'cancelled' if item.get('business_status') == 'CANCELLED' else 'completed'
        elif item.get('actual_arrival_at') and item.get('operation') == 'Unload':
            lane = 'blocked' if item['blocked'] else 'now'
        else:
            lane = self._lane(eta, blocked=item['blocked'], planned=item['planned'], now=now)
        eta_status, minutes_to_eta = self._eta_status(
            eta,
            now,
            actual_arrival_at=item.get('actual_arrival_at'),
            business_status=item.get('business_status', ''),
            history=item.get('history', False),
        )
        quantity = item['quantity']
        progress = min(item['progress_quantity'], quantity)
        task_qty = max(int(item.get('task_qty', max(quantity - progress, 0)) or 0), 0)
        task_total_qty = max(int(item.get('task_total_qty', quantity) or 0), 0)
        if item.get('category') == 'transport' and not task_total_qty:
            quantity_label = '—'
        else:
            quantity_label = '%s / %s' % (task_qty, task_total_qty)
        source_location = item.get('source_location', '')
        target_location = item.get('target_location', item.get('location', ''))
        location_summary = item.get('location_summary') or (
            '%s -> %s' % (source_location, target_location)
            if source_location else target_location
        )
        # Production runs with USE_TZ=False, while some API paths can still
        # return aware datetimes. Format both forms without crashing the board.
        if eta:
            eta_text = eta.strftime('%m/%d %H:%M') if timezone.is_naive(eta) else timezone.localtime(eta).strftime('%m/%d %H:%M')
        else:
            eta_text = ''
        return {
            'id': '%s-%s' % (item['category'], item['reference']),
            'category': item['category'],
            'operation': item['operation'],
            'status': item.get('status', ''),
            'business_status': item.get('business_status', item.get('status', '')),
            'next_action': item.get('next_action_label') or item.get('operation', ''),
            'next_action_code': item.get('next_action_code', ''),
            'next_action_label': item.get('next_action_label', ''),
            'operational_status': item.get('operational_status', ''),
            'operational_status_reason': item.get('operational_status_reason', ''),
            'reconciliation_status': item.get('reconciliation_status', ''),
            'exception_note': item.get('exception_note', ''),
            'lane': lane,
            'reference': item['reference'],
            'customer': item.get('customer', ''),
            'customer_short_name': item.get('customer_short_name') or item.get('customer', ''),
            'customer_full_name': item.get('customer_full_name', ''),
            'location': item['location'],
            'source_location': source_location,
            'target_location': target_location,
            'location_summary': location_summary,
            'quantity': max(quantity - progress, 0),
            'progress_quantity': progress,
            'total_quantity': quantity,
            'task_qty': task_qty,
            'task_total_qty': task_total_qty,
            'quantity_label': quantity_label,
            'eta': eta_text,
            'eta_status': eta_status,
            'minutes_to_eta': minutes_to_eta,
            'eta_due_soon_minutes': self.ETA_DUE_SOON_MINUTES,
            'arrival_status': 'ARRIVED' if item.get('actual_arrival_at') else 'PRE_ARRIVAL',
            'staging_reserved_qty': item.get('staging_reserved_qty', 0),
            'staging_occupied_qty': item.get('staging_occupied_qty', 0),
            'staging_reserved_bins': item.get('staging_reserved_bins', []),
            'staging_occupied_bins': item.get('staging_occupied_bins', []),
            'staging_bins': item.get('staging_occupied_bins') or item.get('staging_reserved_bins', []),
            'assigned_role': item.get('assigned_role', 'WAREHOUSE'),
            'assignee_name': item.get('assignee_name', ''),
            'assigned_to': item.get('assignee_name') or item.get('assigned_role', 'WAREHOUSE'),
            'acceptance_summary': item.get('acceptance_summary', {}),
            'exception_summary': item.get('exception_summary') or item.get('exception_note', ''),
            'blocking_reason': item.get('blocking_reason', ''),
            'linked_reference': item.get('linked_reference', ''),
            'picking_mode': item.get('picking_mode', ''),
            'transport_required': bool(item.get('transport_required', False)),
            'action_code': item.get('action_code', self._action_code(item.get('operation'))),
            'available_actions': item.get('available_actions', []),
            'can_act': bool(item.get('can_act', False)),
            'history_roles': item.get('history_roles', []),
            'history_assignees': item.get('history_assignees', []),
            'is_history': bool(item.get('history')),
            'action_route': item['action_route'],
            'sort_time': timestamp or now,
        }
