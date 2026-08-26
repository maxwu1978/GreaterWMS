from rest_framework.permissions import BasePermission

from .agent import is_agent_request


INTERNAL_MAILTASK_ROLES = frozenset({
    'admin', 'manager', 'supervisor', 'inbound', 'outbound',
    'stockcontrol', 'warehouse', 'qc', 'driver', 'logistics',
})


class AgentPreviewPermission(BasePermission):
    """Allow authenticated AI/CLI previews; operation roles are checked by the view."""

    message = 'A valid operator identity is required for AI/CLI workflow previews.'

    def has_permission(self, request, view):
        identity = getattr(request, 'auth', None)
        if not getattr(request.user, 'is_authenticated', False):
            return False
        if not getattr(identity, 'openid', None):
            return False
        if not is_agent_request(request):
            return False
        operator = request.META.get('HTTP_OPERATOR')
        if getattr(identity, 'is_admin', False):
            return bool(operator)
        return bool(operator) and str(operator) == str(getattr(identity, 'staff_id', ''))


class SourceIntakePermission(BasePermission):
    """Allow authenticated internal staff to read the Mail2Task board.

    AI/CLI mailbox capture and processing use AgentPreviewPermission and the
    operation-role checks in the agent layer. This permission protects the
    human-facing task/evidence board from external supplier and customer roles.
    """

    message = 'Your role cannot view source intake records.'

    def has_permission(self, request, view):
        identity = getattr(request, 'auth', None)
        if not getattr(request.user, 'is_authenticated', False):
            return False
        if not getattr(identity, 'openid', None):
            return False
        role = str(getattr(identity, 'staff_type', '') or '').strip().casefold()
        return (
            bool(getattr(identity, 'is_admin', False)) and role == 'admin'
        ) or role in INTERNAL_MAILTASK_ROLES
