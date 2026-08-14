from rest_framework import viewsets
from asn.models import AsnDetailModel, AsnListModel
from dn.models import DnDetailModel
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
        lane_order = {
            'blocked': 0,
            'delayed': 1,
            'now': 2,
            'next': 3,
            'completed': 4,
            'cancelled': 5,
        }
        items.sort(key=lambda item: (lane_order[item['lane']], item['sort_time']))

        counts = {
            'total': len(items),
            'now': sum(item['lane'] == 'now' for item in items),
            'next': sum(item['lane'] == 'next' for item in items),
            'delayed': sum(item['lane'] == 'delayed' for item in items),
            'blocked': sum(item['lane'] == 'blocked' for item in items),
            'completed': sum(item['lane'] == 'completed' for item in items),
            'cancelled': sum(item['lane'] == 'cancelled' for item in items),
        }
        for item in items:
            item.pop('sort_time', None)
        try:
            limit = min(max(int(request.query_params.get('limit', 100)), 1), 500)
        except (TypeError, ValueError):
            return Response({'detail': 'limit must be an integer'}, status=400)
        return Response({
            'generated_at': now.isoformat(),
            'view': view,
            'viewer': {
                'staff_name': viewer_name,
                'staff_type': getattr(auth, 'staff_type', '') or '',
                'scope': 'all' if viewer_role in self.MANAGEMENT_ROLES else 'role',
            },
            'items': items[:limit],
            'has_more': len(items) > limit,
            'counts': counts,
        })

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
    def _lane(eta, *, blocked, planned):
        if blocked:
            return 'blocked'
        if eta and timezone.now() > eta:
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
        ).only('reference_code', 'status'):
            summary = staging_context.setdefault(assignment.reference_code, {'reserved': 0, 'occupied': 0})
            if assignment.status == StagingAssignment.RESERVED:
                summary['reserved'] += 1
            else:
                summary['occupied'] += 1
        linked_receipt_asns = set(ReceivingRecord.objects.filter(
            openid=openid,
        ).exclude(
            status=ReceivingRecord.CANCELLED,
        ).exclude(
            linked_asn_code='',
        ).values_list('linked_asn_code', flat=True))
        rows = list(AsnDetailModel.objects.filter(
            openid=openid,
            asn_status__in=status_map.keys(),
            is_delete=False,
        ).exclude(asn_code__in=linked_receipt_asns).order_by('-update_time', '-id'))
        supplier_names = {row.supplier for row in rows if row.supplier}
        supplier_short_names = dict(SupplierModel.objects.filter(
            openid=openid,
            supplier_name__in=supplier_names,
            is_delete=False,
        ).values_list('supplier_name', 'supplier_short_name'))
        for row in rows:
            customer_name = row.supplier or ''
            intake = asn_context.get(row.asn_code, {})
            staging = staging_context.get(row.asn_code, {'reserved': 0, 'occupied': 0})
            current = grouped.setdefault(row.asn_code, {
                'category': 'inbound',
                'reference': row.asn_code,
                'customer': supplier_short_names.get(customer_name) or generated_supplier_short_name(customer_name),
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
                'package_qty': intake.get('package_qty') or 0,
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

        for item in grouped.values():
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
            if item['status'] == 4:
                summary = receiving_summary(openid, item['reference'])
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

        return [self._format_item(item, now) for item in grouped.values()]

    def _receiving_items(self, openid, now, history=False):
        records = ReceivingRecord.objects.filter(
            openid=openid,
        )
        if history:
            records = records.filter(status__in=(ReceivingRecord.CLOSED, ReceivingRecord.CANCELLED))
        else:
            records = records.exclude(status__in=(ReceivingRecord.CLOSED, ReceivingRecord.CANCELLED))
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
            items.append(self._format_item({
                'category': 'receiving',
                'reference': record.receipt_no,
                'customer': generated_supplier_short_name(record.customer),
                'customer_full_name': record.customer,
                'operation': operation,
                'location': 'Stage' if progress < total else 'Storage',
                'action_route': 'receiving',
                'status': record.status,
                'reconciliation_status': record.reconciliation_status,
                'quantity': total,
                'progress_quantity': progress,
                'blocked': blocked,
                'planned': planned,
                'timestamp': record.update_time or record.create_time,
                'eta': None,
                'assigned_role': role,
                'assignee_name': assignee,
                'exception_note': record.exception_note,
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
            items.append(self._format_item({
                'category': 'transport',
                'reference': order.transport_no,
                'customer': generated_supplier_short_name(order.customer),
                'customer_full_name': order.customer,
                'operation': operation,
                'location': order.delivery_location or order.pickup_location or 'Dock',
                'action_route': 'transport',
                'status': order.status,
                'quantity': 0,
                'progress_quantity': 0,
                'blocked': False,
                'planned': planned,
                'timestamp': order.update_time or order.create_time,
                'eta': order.eta,
                'assigned_role': role,
                'assignee_name': assignee or '',
                'exception_note': order.note,
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
        rows = list(DnDetailModel.objects.filter(
            openid=openid,
            dn_status__in=status_map.keys(),
            is_delete=False,
        ).order_by('-update_time', '-id'))
        dispatch_context = {}
        for dn_code, driver_name in DispatchListModel.objects.filter(
            openid=openid,
            dn_code__in={row.dn_code for row in rows},
        ).order_by('dn_code', 'id').values_list('dn_code', 'driver_name'):
            # Keep the latest dispatch record when a DN was reassigned.
            dispatch_context[dn_code] = driver_name
        for row in rows:
            customer_name = row.customer or ''
            current = grouped.setdefault(row.dn_code, {
                'category': 'outbound',
                'reference': row.dn_code,
                'customer': generated_supplier_short_name(customer_name),
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
                'driver_name': dispatch_context.get(row.dn_code, ''),
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
            current['blocked'] = current['blocked'] or bool(
                row.back_order_label or row.delivery_shortage_qty or row.delivery_more_qty or row.delivery_damage_qty
            )
            current['timestamp'] = max(current['timestamp'], self._timestamp(row))

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
            lane = self._lane(eta, blocked=item['blocked'], planned=item['planned'])
        quantity = item['quantity']
        progress = min(item['progress_quantity'], quantity)
        return {
            'id': '%s-%s' % (item['category'], item['reference']),
            'category': item['category'],
            'operation': item['operation'],
            'status': item.get('status', ''),
            'business_status': item.get('business_status', item.get('status', '')),
            'next_action': item.get('operation', ''),
            'reconciliation_status': item.get('reconciliation_status', ''),
            'exception_note': item.get('exception_note', ''),
            'lane': lane,
            'reference': item['reference'],
            'customer': item.get('customer', ''),
            'customer_full_name': item.get('customer_full_name', ''),
            'location': item['location'],
            'quantity': max(quantity - progress, 0),
            'progress_quantity': progress,
            'total_quantity': quantity,
            'eta': timezone.localtime(eta).strftime('%m-%d %H:%M') if eta else '',
            'arrival_status': 'ARRIVED' if item.get('actual_arrival_at') else 'PRE_ARRIVAL',
            'staging_reserved_qty': item.get('staging_reserved_qty', 0),
            'staging_occupied_qty': item.get('staging_occupied_qty', 0),
            'assigned_role': item.get('assigned_role', 'WAREHOUSE'),
            'assignee_name': item.get('assignee_name', ''),
            'assigned_to': item.get('assignee_name') or item.get('assigned_role', 'WAREHOUSE'),
            'history_roles': item.get('history_roles', []),
            'history_assignees': item.get('history_assignees', []),
            'is_history': bool(item.get('history')),
            'action_route': item['action_route'],
            'sort_time': timestamp or now,
        }
