from rest_framework import viewsets
from .models import ListModel, TypeListModel
from . import serializers
from utils.page import MyPageNumberPagination
from rest_framework.filters import OrderingFilter
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.response import Response
from .filter import Filter, TypeFilter
from rest_framework.exceptions import APIException, PermissionDenied
from .serializers import FileRenderSerializer
from django.http import StreamingHttpResponse
from .files import FileRenderCN, FileRenderEN
from rest_framework.settings import api_settings
from .auth import issue_session_token, revoke_staff_tokens


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

    def list(self, request, *args, **kwargs):
        staff_name = request.GET.get('staff_name')
        check_code = request.GET.get('check_code')
        if check_code is None:
            return super().list(request, *args, **kwargs)

        if not getattr(request.auth, 'is_admin', False):
            raise PermissionDenied("Only an administrator can issue staff sessions")

        staff_name_obj = ListModel.objects.filter(
            openid=self.request.auth.openid,
            staff_name=staff_name,
            is_delete=False,
        ).first()
        if staff_name_obj is None:
            raise APIException({"detail": "The user name does not exist"})
        if staff_name_obj.is_lock:
            raise APIException({"detail": "The user has been locked. Please contact the administrator"})
        if staff_name_obj.error_check_code_counter >= 3:
            staff_name_obj.is_lock = True
            staff_name_obj.error_check_code_counter = 0
            staff_name_obj.save(update_fields=['is_lock', 'error_check_code_counter', 'update_time'])
            raise APIException({"detail": "The user has been locked. Please contact the administrator"})

        try:
            check_code = int(check_code)
        except (TypeError, ValueError):
            raise APIException({"detail": "The verification code is incorrect"})

        if staff_name_obj.check_code != check_code:
            staff_name_obj.error_check_code_counter = int(staff_name_obj.error_check_code_counter) + 1
            staff_name_obj.save(update_fields=['error_check_code_counter', 'update_time'])
            raise APIException({"detail": "The verification code is incorrect"})

        staff_name_obj.error_check_code_counter = 0
        staff_name_obj.save(update_fields=['error_check_code_counter', 'update_time'])
        response = super().list(request, *args, **kwargs)
        response.data['auth_token'] = issue_session_token(staff_name_obj, token_kind='staff')
        response.data['token_type'] = 'staff'
        return response


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
        if self.action in ['list', 'retrieve', 'destroy']:
            return serializers.StaffGetSerializer
        elif self.action in ['create']:
            return serializers.StaffPostSerializer
        elif self.action in ['update']:
            return serializers.StaffUpdateSerializer
        elif self.action in ['partial_update']:
            return serializers.StaffPartialUpdateSerializer
        else:
            return self.http_method_not_allowed(request=self.request)

    def create(self, request, *args, **kwargs):
        data = self.request.data.copy()
        data['openid'] = self.request.auth.openid
        if str(data.get('staff_type', '')).strip().casefold() == 'admin' and ListModel.objects.filter(
            openid=data['openid'], staff_type__iexact='Admin', is_delete=False,
        ).exists():
            raise APIException({"detail": "An administrator already exists"})
        if ListModel.objects.filter(openid=data['openid'], staff_name=data['staff_name'], is_delete=False).exists():
            raise APIException({"detail": "Data exists"})
        else:
            serializer = self.get_serializer(data=data)
            serializer.is_valid(raise_exception=True)
            serializer.save()
            headers = self.get_success_headers(serializer.data)
            return Response(serializer.data, status=200, headers=headers)

    def update(self, request, pk):
        qs = self.get_object()
        if qs.openid != self.request.auth.openid:
            raise APIException({"detail": "Cannot Update Data Which Not Yours"})
        else:
            data = self.request.data.copy()
            if str(data.get('staff_type', '')).strip().casefold() == 'admin' and qs.staff_type.casefold() != 'admin' and ListModel.objects.filter(
                openid=qs.openid, staff_type__iexact='Admin', is_delete=False,
            ).exclude(id=qs.id).exists():
                raise APIException({"detail": "An administrator already exists"})
            serializer = self.get_serializer(qs, data=data)
            serializer.is_valid(raise_exception=True)
            serializer.save()
            headers = self.get_success_headers(serializer.data)
            return Response(serializer.data, status=200, headers=headers)

    def partial_update(self, request, pk):
        qs = self.get_object()
        if qs.openid != self.request.auth.openid:
            raise APIException({"detail": "Cannot Partial Update Data Which Not Yours"})
        else:
            data = self.request.data.copy()
            if str(data.get('staff_type', '')).strip().casefold() == 'admin' and qs.staff_type.casefold() != 'admin' and ListModel.objects.filter(
                openid=qs.openid, staff_type__iexact='Admin', is_delete=False,
            ).exclude(id=qs.id).exists():
                raise APIException({"detail": "An administrator already exists"})
            serializer = self.get_serializer(qs, data=data, partial=True)
            serializer.is_valid(raise_exception=True)
            serializer.save()
            headers = self.get_success_headers(serializer.data)
            return Response(serializer.data, status=200, headers=headers)

    def destroy(self, request, pk):
        qs = self.get_object()
        if qs.openid != self.request.auth.openid:
            raise APIException({"detail": "Cannot Delete Data Which Not Yours"})
        if str(qs.staff_type).strip().casefold() == 'admin':
            raise APIException({"detail": "The administrator account cannot be deleted"})
        else:
            qs.is_delete = True
            qs.save()
            revoke_staff_tokens(qs.id, qs.openid)
            serializer = self.get_serializer(qs, many=False)
            headers = self.get_success_headers(serializer.data)
            return Response(serializer.data, status=200, headers=headers)


class TypeAPIViewSet(viewsets.ModelViewSet):
    """
        list:
            Response a data list（all）
    """
    pagination_class = MyPageNumberPagination
    filter_backends = [DjangoFilterBackend, OrderingFilter, ]
    ordering_fields = ['id', "create_time", "update_time", ]
    filter_class = TypeFilter

    def get_queryset(self):
        if self.request.user:
            return TypeListModel.objects.filter(openid='init_data')
        else:
            return TypeListModel.objects.none()

    def get_serializer_class(self):
        if self.action in ['list']:
            return serializers.StaffTypeGetSerializer
        else:
            return self.http_method_not_allowed(request=self.request)


class FileDownloadView(viewsets.ModelViewSet):
    renderer_classes = (FileRenderCN,) + tuple(api_settings.DEFAULT_RENDERER_CLASSES)
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
        response['Content-Disposition'] = "attachment; filename='staff_{}.csv'".format(
            str(dt.strftime('%Y%m%d%H%M%S%f')))
        return response
