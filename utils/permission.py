from rest_framework.permissions import BasePermission


READ_METHODS = {'GET', 'HEAD', 'OPTIONS'}
ADMIN_ONLY_MODULES = {'staff', 'company', 'warehouse'}
MASTER_DATA_MODULES = {
    'binproperty', 'binsize', 'capital', 'customer', 'driver', 'goods',
    'goodsbrand', 'goodsclass', 'goodscolor', 'goodsorigin', 'goodsshape',
    'goodsspecs', 'goodsunit', 'payment', 'supplier',
}
INBOUND_MODULES = {'asn', 'asnserial', 'staging', 'scanner', 'uploadfile'}
OUTBOUND_MODULES = {'dn', 'driver', 'staging', 'scanner'}
INVENTORY_MODULES = {'stock', 'cyclecount', 'asnserial', 'staging', 'scanner'}
WAREHOUSE_MODULES = INBOUND_MODULES | OUTBOUND_MODULES | INVENTORY_MODULES
QC_MODULES = {'asnserial', 'scanner'}


ROLE_MODULES = {
    'manager': MASTER_DATA_MODULES | INBOUND_MODULES | OUTBOUND_MODULES | INVENTORY_MODULES,
    'supervisor': MASTER_DATA_MODULES | INBOUND_MODULES | OUTBOUND_MODULES | INVENTORY_MODULES,
    'inbound': INBOUND_MODULES,
    'outbound': OUTBOUND_MODULES,
    'stockcontrol': INVENTORY_MODULES,
    'warehouse': WAREHOUSE_MODULES,
    'qc': QC_MODULES,
    # Drivers receive a read-only dashboard queue.  Operational writes remain
    # with warehouse staff and are protected by the existing role checks.
    'driver': set(),
}


def _module_name(view):
    return view.__class__.__module__.split('.')[0]


def _operator_matches_identity(request):
    """Prevent a non-admin from writing an audit record as another worker."""
    identity = getattr(request, 'auth', None)
    operator = request.META.get('HTTP_OPERATOR')
    if getattr(identity, 'is_admin', False):
        return True
    if not operator:
        return False
    return str(operator) == str(getattr(identity, 'staff_id', ''))


class Normalpermission(BasePermission):
    """Tenant isolation plus role-based write authorization."""

    def has_permission(self, request, view):
        identity = getattr(request, 'auth', None)
        if not getattr(request.user, 'is_authenticated', False) or not getattr(identity, 'openid', None):
            return False

        module = _module_name(view)
        if module == 'staff':
            # Staff records are user-management data.  Operators do not need
            # to enumerate or mutate them through the WMS API.
            if getattr(identity, 'is_admin', False):
                return True
            return (
                request.method in READ_METHODS
                and request.GET.get('staff_name') == getattr(identity, 'staff_name', None)
                and getattr(view, 'action', None) == 'list'
            )

        if request.method in READ_METHODS:
            return True

        if getattr(identity, 'is_admin', False):
            return True
        if not _operator_matches_identity(request):
            return False

        role = str(getattr(identity, 'staff_type', '')).strip().casefold()
        return module in ROLE_MODULES.get(role, set())

    def has_object_permission(self, request, view, obj):
        return self.has_permission(request, view)
