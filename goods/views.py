from rest_framework import viewsets
from .models import ListModel
from . import serializers
from .page import MyPageNumberPagination
from rest_framework.filters import OrderingFilter
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.response import Response
from .filter import Filter
from rest_framework.exceptions import APIException
from goodsunit.models import ListModel as goods_unit
from goodsclass.models import ListModel as goods_class
from goodsbrand.models import ListModel as goods_brand
from goodscolor.models import ListModel as goods_color
from goodsshape.models import ListModel as goods_shape
from goodsspecs.models import ListModel as goods_specs
from goodsorigin.models import ListModel as goods_origin
from supplier.models import ListModel as supplier
from scanner.models import ListModel as scanner
from utils.md5 import Md5
from .serializers import FileRenderSerializer
from django.http import StreamingHttpResponse
from .files import FileRenderCN, FileRenderEN
from rest_framework.settings import api_settings
from asn.models import AsnDetailModel
from django.db.models import Q
from django.db import transaction
from django.utils import timezone
from asnserial.models import SourceEvidence
from .units import unit_volume_cubic_meters, weight_to_kg


def _operator_name(request):
    identity = getattr(request, 'auth', None)
    return str(
        getattr(identity, 'staff_name', '')
        or request.META.get('HTTP_OPERATOR_NAME', '')
        or getattr(getattr(request, 'user', None), 'username', '')
        or 'system'
    )


def _goods_payload(request, data, instance=None):
    payload = data.copy()
    payload['openid'] = request.auth.openid
    if not payload.get('creater'):
        payload['creater'] = _operator_name(request)

    if not payload.get('bar_code'):
        code = payload.get('goods_code') or getattr(instance, 'goods_code', '')
        if code:
            payload['bar_code'] = Md5.md5(str(code))

    dimensions = {
        key: payload.get(key, getattr(instance, key, 0) if instance else 0)
        for key in ('goods_w', 'goods_d', 'goods_h')
    }
    measurement_unit = payload.get(
        'measurement_unit', getattr(instance, 'measurement_unit', '') if instance else ''
    )
    payload['unit_volume'] = unit_volume_cubic_meters(
        dimensions['goods_w'], dimensions['goods_d'], dimensions['goods_h'], measurement_unit
    )
    return payload


def _source_evidence_for_import(request, evidence_id):
    try:
        return SourceEvidence.objects.get(id=int(evidence_id), openid=request.auth.openid)
    except (SourceEvidence.DoesNotExist, TypeError, ValueError):
        raise APIException({'detail': 'Source evidence does not exist in this tenant'})


def _create_scanner_tag(openid, goods_code, bar_code):
    scanner.objects.update_or_create(
        openid=openid,
        mode='GOODS',
        code=str(goods_code),
        defaults={'bar_code': str(bar_code)},
    )

class SannerGoodsTagView(viewsets.ModelViewSet):

    """
    retrieve:
        Response a data retrieve（get）

    """

    pagination_class = MyPageNumberPagination
    filter_backends = [DjangoFilterBackend, OrderingFilter, ]
    ordering_fields = ['id', "create_time", "update_time", ]
    filter_class = Filter
    lookup_field = 'bar_code'
    def get_project(self):
        try:
            bar_code = self.kwargs['bar_code']
            return bar_code
        except:
            return None

    def get_queryset(self):
        bar_code = self.get_project()
        if self.request.user:
            if bar_code is None:
                return ListModel.objects.filter(openid=self.request.auth.openid, is_delete=False)
            else:
                return ListModel.objects.filter(openid=self.request.auth.openid, bar_code=bar_code, is_delete=False)
        else:
            return ListModel.objects.filter().none()

    def get_serializer_class(self):
        if self.action in ['list', 'retrieve', 'destroy']:
            return serializers.GoodsGetSerializer
        elif self.action in ['create']:
            return serializers.GoodsPostSerializer
        elif self.action in ['update']:
            return serializers.GoodsUpdateSerializer
        elif self.action in ['partial_update']:
            return serializers.GoodsPartialUpdateSerializer
        else:
            return self.http_method_not_allowed(request=self.request)

    def retrieve(self, request, *args, **kwargs):
        data=self.request.GET.get('asn_code')
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        good_detail=AsnDetailModel.objects.filter(asn_code=data,goods_code=serializer.data['goods_code']).first()
        if good_detail is None:
            raise APIException({"detail":"The product label does not exist"})
        else:
            context = {}
            context['goods_code'] = good_detail.goods_code
            context['goods_actual_qty'] = good_detail.goods_actual_qty
        return Response(context, status=200)

class APIViewSet(viewsets.ModelViewSet):
    """
        retrieve:
            Response a data list（get）

        list:
            Response a data list（all）

        create:
            Create a data line（post）

        delete:
            Delete a data line（delete)

        partial_update:
            Partial_update a data（patch：partial_update）

        update:
            Update a data（put：update）
    """
    pagination_class = MyPageNumberPagination
    filter_backends = [DjangoFilterBackend, OrderingFilter, ]
    ordering_fields = ['id', "create_time", "update_time", ]
    filter_class = Filter

    def get_project(self):
        try:
            id = self.kwargs.get('pk')
            return id
        except:
            return None

    def get_queryset(self):
        id = self.get_project()
        if self.request.user:
            search_word = self.request.GET.get('search', '')
            if search_word:
                if id is None:
                    data_list = ListModel.objects.filter(openid=self.request.auth.openid, is_delete=False)
                    search_list = data_list.filter(Q(goods_shape=search_word) | Q(goods_specs=search_word))
                    return search_list
                else:
                    data_list = ListModel.objects.filter(openid=self.request.auth.openid, id=id, is_delete=False)
                    search_list = data_list.filter(Q(goods_shape=search_word) | Q(goods_specs=search_word))
                    return search_list
            else:
                if id is None:
                    return ListModel.objects.filter(openid=self.request.auth.openid, is_delete=False)
                else:
                    return ListModel.objects.filter(openid=self.request.auth.openid, id=id, is_delete=False)
        else:
            return ListModel.objects.filter().none()

    def get_serializer_class(self):
        if self.action in ['list', 'retrieve', 'destroy']:
            return serializers.GoodsGetSerializer
        elif self.action in ['create']:
            return serializers.GoodsPostSerializer
        elif self.action in ['update']:
            return serializers.GoodsUpdateSerializer
        elif self.action in ['partial_update']:
            return serializers.GoodsPartialUpdateSerializer
        else:
            return self.http_method_not_allowed(request=self.request)

    def create(self, request, *args, **kwargs):
        data = _goods_payload(request, self.request.data)
        if not data.get('goods_code'):
            raise APIException({'detail': 'Goods Code is required'})
        if ListModel.objects.filter(openid=data['openid'], goods_code=data['goods_code'], is_delete=False).exists():
            raise APIException({"detail": "Data Exists"})
        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        _create_scanner_tag(data['openid'], data['goods_code'], data['bar_code'])
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=200, headers=headers)

    def update(self, request, pk):
        qs = self.get_object()
        if qs.openid != self.request.auth.openid:
            raise APIException({"detail": "Cannot update data which not yours"})
        data = _goods_payload(request, self.request.data, qs)
        next_code = str(data.get('goods_code') or qs.goods_code)
        if ListModel.objects.filter(
            openid=self.request.auth.openid, goods_code=next_code, is_delete=False
        ).exclude(id=qs.id).exists():
            raise APIException({"detail": "Data Exists"})
        serializer = self.get_serializer(qs, data=data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        _create_scanner_tag(self.request.auth.openid, next_code, data.get('bar_code'))
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=200, headers=headers)

    def partial_update(self, request, pk):
        qs = self.get_object()
        if qs.openid != self.request.auth.openid:
            raise APIException({"detail": "Cannot partial_update data which not yours"})
        data = _goods_payload(request, self.request.data, qs)
        next_code = str(data.get('goods_code') or qs.goods_code)
        if ListModel.objects.filter(
            openid=self.request.auth.openid, goods_code=next_code, is_delete=False
        ).exclude(id=qs.id).exists():
            raise APIException({"detail": "Data Exists"})
        serializer = self.get_serializer(qs, data=data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        _create_scanner_tag(self.request.auth.openid, next_code, data.get('bar_code'))
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=200, headers=headers)

    def destroy(self, request, pk):
        qs = self.get_object()
        if qs.openid != self.request.auth.openid:
            raise APIException({"detail": "Cannot delete data which not yours"})
        else:
            qs.is_delete = True
            qs.save()
            serializer = self.get_serializer(qs, many=False)
            headers = self.get_success_headers(serializer.data)
            return Response(serializer.data, status=200, headers=headers)

class SourceImportView(viewsets.ViewSet):
    """Import source-traced SKUs without requiring lookup-table placeholders."""

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        raw_items = request.data.get('items') if hasattr(request.data, 'get') else None
        items = raw_items if isinstance(raw_items, list) else [request.data]
        if not items:
            raise APIException({'detail': 'At least one SKU is required'})
        if len(items) > 1000:
            raise APIException({'detail': 'A single source import cannot exceed 1000 SKUs'})

        created = []
        reused = []
        evidence_ids = set()
        for raw in items:
            data = raw.copy()
            evidence_id = data.get('source_evidence_id') or request.data.get('source_evidence_id')
            evidence = _source_evidence_for_import(request, evidence_id)
            evidence_ids.add(evidence.id)
            data['source_evidence_id'] = evidence.id
            data = _goods_payload(request, data)
            if not data.get('goods_code'):
                raise APIException({'detail': 'Goods Code is required'})

            existing = ListModel.objects.filter(
                openid=request.auth.openid,
                goods_code=str(data['goods_code']),
                is_delete=False,
            ).first()
            if existing:
                if existing.source_evidence_id == evidence.id:
                    reused.append(existing.id)
                    continue
                raise APIException({
                    'detail': f"Goods Code {data['goods_code']} already exists from another source"
                })

            serializer = serializers.GoodsSourceImportSerializer(data=data)
            serializer.is_valid(raise_exception=True)
            instance = serializer.save(openid=request.auth.openid)
            _create_scanner_tag(request.auth.openid, instance.goods_code, instance.bar_code)
            created.append(instance.id)

        SourceEvidence.objects.filter(
            openid=request.auth.openid,
            id__in=evidence_ids,
        ).update(status=SourceEvidence.USED, used_at=timezone.now())
        return Response({
            'detail': 'source SKU import complete',
            'created_ids': created,
            'reused_ids': reused,
            'created_count': len(created),
            'reused_count': len(reused),
        }, status=200)


class FileDownloadView(viewsets.ModelViewSet):
    renderer_classes = (FileRenderCN, ) + tuple(api_settings.DEFAULT_RENDERER_CLASSES)
    filter_backends = [DjangoFilterBackend, OrderingFilter, ]
    ordering_fields = ['id', "create_time", "update_time", ]
    filter_class = Filter

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
                return ListModel.objects.filter(openid=self.request.auth.openid, is_delete=False)
            else:
                return ListModel.objects.filter(openid=self.request.auth.openid, id=id, is_delete=False)
        else:
            return ListModel.objects.none()

    def get_serializer_class(self):
        if self.action in ['list']:
            return serializers.FileRenderSerializer
        else:
            return self.http_method_not_allowed(request=self.request)

    def get_lang(self, data):
        lang = self.request.META.get('HTTP_LANGUAGE')
        if lang:
            if lang == 'zh-hans':
                return FileRenderCN().render(data)
            else:
                return FileRenderEN().render(data)
        else:
            return FileRenderEN().render(data)

    def list(self, request, *args, **kwargs):
        from datetime import datetime
        dt = datetime.now()
        data = (
            FileRenderSerializer(instance).data
            for instance in self.filter_queryset(self.get_queryset())
        )
        renderer = self.get_lang(data)
        response = StreamingHttpResponse(
            renderer,
            content_type="text/csv"
        )
        response['Content-Disposition'] = "attachment; filename='goodslist_{}.csv'".format(str(dt.strftime('%Y%m%d%H%M%S%f')))
        return response
