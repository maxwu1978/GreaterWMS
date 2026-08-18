"""Safe, tenant-scoped cleanup for disposable test data.

The service deliberately operates through the authenticated WMS request. It
does not connect to or mutate the production database outside Django's API.
"""

from django.apps import apps
from django.conf import settings
from django.db import transaction
from rest_framework.exceptions import PermissionDenied, ValidationError

from asnserial.agent import complete_preview, consume_preview
from asnserial.models import AgentCommandPreview
from staff.auth import hash_session_token
from staff.models import ListModel as Staff
from staff.models import StaffSessionToken
from userprofile.models import Users


CLEANUP_OPERATION = 'tenant.cleanup'
CLEANUP_PAYLOAD = {
    'scope': 'current_tenant',
    'preserve': 'current_admin_and_active_session',
}

# Receiving putaway rows use PROTECT, so they must be removed before their
# receipt/detail parents. The remaining models are ordered for readability;
# the final pass also handles newly added tenant models automatically.
PREFERRED_DELETE_ORDER = (
    'receiving.ReceivingPutaway',
    'receiving.ReceivingSerial',
    'receiving.ReceivingReconciliationEvent',
    'receiving.ReceivingDetail',
    'receiving.ReceivingRecord',
    'asnserial.AsnSerialRecord',
    'asnserial.PackListLine',
    'asnserial.PackListDocument',
    'asnserial.PackListImportBatch',
    'asnserial.ExceptionQuantityMovement',
    'staging.StagingAssignment',
    'driver.DispatchListModel',
    'transport.TransportOrder',
    'dn.DnSerialAllocation',
    'dn.PickingListModel',
    'dn.DnDetailModel',
    'dn.DnListModel',
    'asn.AsnEventModel',
    'asn.AsnDetailModel',
    'asn.AsnListModel',
    'stock.StockBinModel',
    'stock.StockListModel',
    'cyclecount.QTYRecorder',
    'cyclecount.CyclecountModeDayModel',
    'cyclecount.ManualCyclecountModeModel',
    'scanner.ListModel',
    'payment.TransportationFeeListModel',
    'driver.ListModel',
    'goods.ListModel',
    'goodsunit.ListModel',
    'goodsclass.ListModel',
    'goodscolor.ListModel',
    'goodsbrand.ListModel',
    'goodsshape.ListModel',
    'goodsspecs.ListModel',
    'goodsorigin.ListModel',
    'supplier.ListModel',
    'customer.ListModel',
    'capital.ListModel',
    'company.ListModel',
    'binset.ListModel',
    'binsize.ListModel',
    'binproperty.ListModel',
    'warehouse.ListModel',
    'throttle.ListModel',
    'staff.StaffSessionToken',
    'staff.ListModel',
    'userprofile.Users',
)


def _model_map():
    return {
        model._meta.label: model
        for model in apps.get_models()
        if not model._meta.abstract and not model._meta.proxy
    }


def _tenant_models():
    for model in _model_map().values():
        if any(field.name == 'openid' for field in model._meta.fields):
            yield model


def _require_admin_context(request):
    identity = getattr(request, 'auth', None)
    if not getattr(identity, 'is_admin', False):
        raise PermissionDenied('Only the platform administrator can clean tenant data')

    tenant_openid = str(getattr(identity, 'openid', '') or '')
    if (
        not settings.TENANT_CLEANUP_ENABLED
        or tenant_openid not in settings.TENANT_CLEANUP_ALLOWED_OPENIDS
    ):
        raise PermissionDenied(
            'Tenant cleanup is disabled unless this tenant is explicitly allowlisted as disposable'
        )
    admin_id = getattr(identity, 'staff_id', None)
    admin = Staff.objects.filter(
        id=admin_id,
        openid=tenant_openid,
        staff_type__iexact='Admin',
        is_delete=False,
    ).first()
    if admin is None:
        raise ValidationError({'detail': 'The authenticated administrator is unavailable'})

    profiles = list(Users.objects.filter(
        openid=tenant_openid,
        name=admin.staff_name,
        is_delete=False,
    ).order_by('id'))
    if not profiles:
        raise ValidationError({'detail': 'The administrator login profile is missing'})

    raw_token = request.META.get('HTTP_TOKEN')
    session = StaffSessionToken.objects.filter(
        openid=tenant_openid,
        staff_id=admin.id,
        token_hash=hash_session_token(raw_token),
        is_revoked=False,
    ).first() if raw_token else None
    if session is None:
        raise ValidationError({
            'detail': 'An active session token is required so the administrator remains logged in',
        })

    return {
        'tenant_openid': tenant_openid,
        'admin': admin,
        'profile_ids': {profile.id for profile in profiles},
        'session_id': session.id,
    }


def _query_for_model(model, context, protected_preview_id=None):
    queryset = model._default_manager.filter(openid=context['tenant_openid'])
    label = model._meta.label
    if label == 'staff.ListModel':
        return queryset.exclude(id=context['admin'].id)
    if label == 'userprofile.Users':
        return queryset.exclude(id__in=context['profile_ids'])
    if label == 'staff.StaffSessionToken':
        return queryset.exclude(id=context['session_id'])
    if label == 'asnserial.AgentCommandPreview' and protected_preview_id:
        return queryset.exclude(id=protected_preview_id)
    return queryset


def _ordered_tenant_models():
    models = _model_map()
    seen = set()
    for label in PREFERRED_DELETE_ORDER:
        model = models.get(label)
        if model is not None and label not in seen:
            seen.add(label)
            yield model
    for model in sorted(_tenant_models(), key=lambda item: item._meta.label):
        if model._meta.label not in seen:
            yield model


def build_cleanup_plan(request, protected_preview_id=None, context=None):
    context = context or _require_admin_context(request)
    deletions = {}
    protected = {
        'admin_staff_id': context['admin'].id,
        'admin_name': context['admin'].staff_name,
        'profile_ids': sorted(context['profile_ids']),
        'session_id': context['session_id'],
        'preview_id': protected_preview_id,
    }
    for model in _ordered_tenant_models():
        queryset = _query_for_model(model, context, protected_preview_id)
        count = queryset.count()
        if count:
            deletions[model._meta.label] = count
    return {
        'scope': 'current_tenant',
        'tenant_openid_present': bool(context['tenant_openid']),
        'deletions': deletions,
        'delete_total': sum(deletions.values()),
        'protected': protected,
    }


def execute_cleanup(request, command):
    """Delete the reviewed tenant rows and retain the current admin context."""
    with transaction.atomic():
        locked_command = AgentCommandPreview.objects.select_for_update().get(id=command.id)
        if locked_command.status == AgentCommandPreview.EXECUTED:
            return locked_command.result

        context = _require_admin_context(request)
        plan = build_cleanup_plan(
            request,
            protected_preview_id=locked_command.id,
            context=context,
        )
        deleted = {}
        for model in _ordered_tenant_models():
            queryset = _query_for_model(
                model,
                context,
                protected_preview_id=locked_command.id,
            )
            before = queryset.count()
            if before:
                queryset.delete()
            deleted[model._meta.label] = before

        remaining = {}
        for model in _tenant_models():
            remaining_count = _query_for_model(
                model,
                context,
                protected_preview_id=locked_command.id,
            ).count()
            if remaining_count:
                remaining[model._meta.label] = remaining_count

        result = {
            'detail': 'Tenant test data cleaned',
            'scope': 'current_tenant',
            'delete_total': sum(deleted.values()),
            'deleted': {label: count for label, count in deleted.items() if count},
            'remaining_non_protected': remaining,
            'protected': plan['protected'],
        }
        complete_preview(locked_command, result)
        return result


def preview_cleanup(request):
    """Create a server preview using the same fixed cleanup payload."""
    from asnserial.agent import create_preview

    plan = build_cleanup_plan(request)
    preview = create_preview(request, CLEANUP_OPERATION, CLEANUP_PAYLOAD)
    preview.update(plan)
    return preview


def confirm_cleanup(request):
    command, replay_result = consume_preview(
        request,
        CLEANUP_OPERATION,
        CLEANUP_PAYLOAD,
    )
    if replay_result is not None:
        return replay_result
    return execute_cleanup(request, command)
