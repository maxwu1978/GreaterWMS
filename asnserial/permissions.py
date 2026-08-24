from rest_framework.permissions import BasePermission

from .agent import is_agent_request


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
    """Allow operational owners to read the Mail2Task source intake board.

    AI/CLI mailbox capture and processing use AgentPreviewPermission and the
    operation-role checks in the agent layer. The board contains external
    instructions and email evidence, so access is limited to administrators,
    managers, and warehouse operators. Other operational roles continue to
    use the task-specific CLI/API paths without receiving the full evidence
    board.
    """

    message = 'Your role cannot view source intake records.'
    VIEW_ROLES = frozenset({'admin', 'manager', 'warehouse'})

    def has_permission(self, request, view):
        identity = getattr(request, 'auth', None)
        if not getattr(request.user, 'is_authenticated', False):
            return False
        if not getattr(identity, 'openid', None):
            return False
        role = str(getattr(identity, 'staff_type', '') or '').strip().casefold()
        return role in self.VIEW_ROLES and (
            role != 'admin' or bool(getattr(identity, 'is_admin', False))
        )
