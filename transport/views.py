from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from driver.models import ListModel as DriverModel

from .models import TransportOrder
from .serializers import TransportOrderSerializer


TRANSITIONS = {
    TransportOrder.REQUESTED: {
        TransportOrder.SCHEDULED,
        TransportOrder.DRIVER_ASSIGNED,
        TransportOrder.CANCELLED,
    },
    TransportOrder.SCHEDULED: {
        TransportOrder.DRIVER_ASSIGNED,
        TransportOrder.CANCELLED,
    },
    TransportOrder.DRIVER_ASSIGNED: {
        TransportOrder.IN_TRANSIT,
        TransportOrder.CANCELLED,
    },
    TransportOrder.IN_TRANSIT: {
        TransportOrder.ARRIVED,
        TransportOrder.CANCELLED,
    },
    TransportOrder.ARRIVED: {TransportOrder.COMPLETED},
    TransportOrder.COMPLETED: set(),
    TransportOrder.CANCELLED: set(),
}


def _openid(request):
    openid = getattr(getattr(request, 'auth', None), 'openid', '')
    if not openid:
        raise ValidationError({'detail': 'Authentication is required'})
    return openid


def _operator_name(request):
    return str(
        getattr(getattr(request, 'auth', None), 'staff_name', '')
        or request.META.get('HTTP_OPERATOR', '')
    ).strip()


def _ensure_roles(request, *roles):
    identity = getattr(request, 'auth', None)
    if getattr(identity, 'is_admin', False):
        return
    role = str(getattr(identity, 'staff_type', '') or '').strip().casefold()
    if role not in {value.casefold() for value in roles}:
        raise ValidationError({'detail': 'This operation is not allowed for your role'})


def _transport_no(openid):
    prefix = 'TR' + timezone.now().strftime('%Y%m%d')
    number = TransportOrder.objects.filter(
        openid=openid,
        transport_no__startswith=prefix,
    ).count() + 1
    candidate = '%s-%04d' % (prefix, number)
    while TransportOrder.objects.filter(openid=openid, transport_no=candidate).exists():
        number += 1
        candidate = '%s-%04d' % (prefix, number)
    return candidate


def _record(request, transport_no, *, lock=False):
    qs = TransportOrder.objects.filter(
        openid=_openid(request),
        transport_no=transport_no,
    )
    if lock:
        qs = qs.select_for_update()
    order = qs.first()
    if order is None:
        raise ValidationError({'detail': 'Transport order does not exist'})
    return order


class TransportOrderListView(APIView):
    def get(self, request):
        qs = TransportOrder.objects.filter(openid=_openid(request))
        status = str(request.GET.get('status') or '').strip().upper()
        direction = str(request.GET.get('direction') or '').strip().upper()
        driver_name = str(request.GET.get('driver_name') or '').strip()
        if status:
            qs = qs.filter(status=status)
        if direction:
            qs = qs.filter(direction=direction)
        if driver_name:
            qs = qs.filter(driver_name=driver_name)
        return Response({
            'count': qs.count(),
            'results': TransportOrderSerializer(qs[:200], many=True).data,
        })

    @transaction.atomic
    def post(self, request):
        _ensure_roles(request, 'Manager', 'Supervisor', 'Logistics')
        openid = _openid(request)
        data = request.data.copy()
        data['transport_no'] = str(data.get('transport_no') or '').strip() or _transport_no(openid)
        data['status'] = TransportOrder.REQUESTED
        serializer = TransportOrderSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        order = serializer.save(openid=openid, created_by=_operator_name(request))
        return Response(TransportOrderSerializer(order).data, status=201)


class TransportOrderDetailView(APIView):
    def get(self, request, transport_no):
        order = _record(request, transport_no)
        return Response(TransportOrderSerializer(order).data)


class TransportAssignView(APIView):
    @transaction.atomic
    def post(self, request):
        _ensure_roles(request, 'Manager', 'Supervisor', 'Logistics')
        order = _record(request, str(request.data.get('transport_no') or '').strip(), lock=True)
        driver_name = str(request.data.get('driver_name') or '').strip()
        if not driver_name:
            raise ValidationError({'detail': 'Driver is required'})
        if not DriverModel.objects.filter(
            openid=order.openid,
            driver_name=driver_name,
            is_delete=False,
        ).exists():
            raise ValidationError({'detail': 'Driver does not exist'})
        if order.status not in (TransportOrder.REQUESTED, TransportOrder.SCHEDULED):
            raise ValidationError({'detail': 'Driver can only be assigned before departure'})
        order.driver_name = driver_name
        order.truck_plate = str(request.data.get('truck_plate') or order.truck_plate or '').strip()
        order.logistics_coordinator = str(
            request.data.get('logistics_coordinator') or order.logistics_coordinator or _operator_name(request)
        ).strip()
        order.status = TransportOrder.DRIVER_ASSIGNED
        order.save(update_fields=[
            'driver_name', 'truck_plate', 'logistics_coordinator', 'status', 'update_time',
        ])
        return Response(TransportOrderSerializer(order).data)


class TransportTransitionView(APIView):
    @transaction.atomic
    def post(self, request):
        identity = getattr(request, 'auth', None)
        _ensure_roles(request, 'Manager', 'Supervisor', 'Logistics', 'Driver')
        order = _record(request, str(request.data.get('transport_no') or '').strip(), lock=True)
        target = str(request.data.get('status') or '').strip().upper()
        if target not in dict(TransportOrder.STATUS_CHOICES):
            raise ValidationError({'detail': 'Unsupported transport status'})
        if target not in TRANSITIONS.get(order.status, set()):
            raise ValidationError({
                'detail': 'Invalid transport transition: %s -> %s' % (order.status, target),
            })
        if str(getattr(identity, 'staff_type', '') or '').casefold() == 'driver':
            if target not in (TransportOrder.IN_TRANSIT, TransportOrder.ARRIVED):
                raise ValidationError({'detail': 'Drivers can only update departure or arrival status'})
            if order.driver_name.casefold() != str(getattr(identity, 'staff_name', '') or '').casefold():
                raise ValidationError({'detail': 'A driver can only update their own transport task'})
        if target == TransportOrder.IN_TRANSIT and not order.driver_name:
            raise ValidationError({'detail': 'Assign a driver before departure'})
        if target == TransportOrder.COMPLETED:
            pod_reference = str(request.data.get('pod_reference') or '').strip()
            if not pod_reference and not order.pod_reference:
                raise ValidationError({'detail': 'POD reference is required to complete transport'})
            order.pod_reference = pod_reference or order.pod_reference
            order.pod_note = str(request.data.get('pod_note') or order.pod_note or '').strip()
            order.completed_by = _operator_name(request)
            order.completed_at = timezone.now()
        if target == TransportOrder.CANCELLED:
            note = str(request.data.get('note') or '').strip()
            if not note:
                raise ValidationError({'detail': 'Cancellation reason is required'})
            order.note = note
        order.status = target
        order.save()
        return Response(TransportOrderSerializer(order).data)
