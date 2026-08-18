from rest_framework.permissions import BasePermission

from .agent import is_agent_request
from .intake import INTAKE_ROLES


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
    """Allow approved warehouse roles to read the source intake board."""

    message = 'Your role cannot view source intake records.'

    def has_permission(self, request, view):
        identity = getattr(request, 'auth', None)
        if not getattr(request.user, 'is_authenticated', False):
            return False
        if not getattr(identity, 'openid', None):
            return False
        role = str(getattr(identity, 'staff_type', '') or '').strip().casefold()
        return role in {item.casefold() for item in INTAKE_ROLES}
