from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import StagingAssignment
from .services import (
    StagingError,
    release_staging_slot,
    reserve_staging_slot,
    staging_slots,
)


class StagingSlotsView(APIView):
    def get(self, request):
        flow = str(request.query_params.get('flow', '')).upper() or None
        if flow and flow not in (StagingAssignment.INBOUND, StagingAssignment.OUTBOUND):
            raise APIException({'detail': 'Invalid staging flow'})
        return Response(staging_slots(request.auth.openid, flow=flow), status=status.HTTP_200_OK)


class StagingAssignmentsView(APIView):
    def get(self, request):
        queryset = StagingAssignment.objects.filter(openid=request.auth.openid)
        reference_code = request.query_params.get('reference_code')
        flow = str(request.query_params.get('flow', '')).upper()
        if reference_code:
            queryset = queryset.filter(reference_code=str(reference_code))
        if flow:
            queryset = queryset.filter(flow=flow)
        if request.query_params.get('active', 'true').lower() == 'true':
            queryset = queryset.filter(status=StagingAssignment.ACTIVE)
        return Response([
            {
                'id': item.id,
                'flow': item.flow,
                'reference_code': item.reference_code,
                'goods_code': item.goods_code,
                'quantity': item.quantity,
                'bin_name': item.bin_name,
                'status': item.status,
                'create_time': item.create_time,
                'release_time': item.release_time,
            }
            for item in queryset
        ], status=status.HTTP_200_OK)

    def post(self, request):
        data = request.data
        try:
            assignment = reserve_staging_slot(
                request.auth.openid,
                str(data.get('flow', '')).upper(),
                data.get('reference_code', ''),
                data.get('bin_name', ''),
                data.get('quantity', 0),
                data.get('goods_code', ''),
                request.META.get('HTTP_OPERATOR', ''),
            )
        except StagingError as exc:
            raise APIException({'detail': str(exc)})
        return Response({'id': assignment.id, 'bin_name': assignment.bin_name, 'status': assignment.status})


class StagingReleaseView(APIView):
    def post(self, request):
        flow = str(request.data.get('flow', '')).upper()
        reference_code = request.data.get('reference_code', '')
        if flow not in (StagingAssignment.INBOUND, StagingAssignment.OUTBOUND) or not reference_code:
            raise APIException({'detail': 'Flow and reference_code are required'})
        released = release_staging_slot(request.auth.openid, flow, reference_code)
        return Response({'released': released}, status=status.HTTP_200_OK)
