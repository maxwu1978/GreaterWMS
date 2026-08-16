from rest_framework.response import Response
from rest_framework.views import APIView

from asnserial.permissions import AgentPreviewPermission

from .service import confirm_cleanup, preview_cleanup


class TenantCleanupPreviewView(APIView):
    permission_classes = [AgentPreviewPermission]

    def post(self, request):
        return Response(preview_cleanup(request))


class TenantCleanupView(APIView):
    permission_classes = [AgentPreviewPermission]

    def post(self, request):
        return Response(confirm_cleanup(request))
