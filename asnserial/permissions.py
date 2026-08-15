from rest_framework.permissions import BasePermission

from .agent import is_agent_request


class AgentPreviewPermission(BasePermission):
    """Allow only authenticated CLI previews; operation roles are checked by the view."""

    message = 'A valid operator identity is required for CLI workflow previews.'

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
