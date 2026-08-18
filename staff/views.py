import json
import hashlib

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from rest_framework import viewsets
from .models import ListModel, TypeListModel
from . import serializers
from utils.page import MyPageNumberPagination
from rest_framework.filters import OrderingFilter
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.response import Response
from .filter import Filter, TypeFilter
from rest_framework.exceptions import APIException, PermissionDenied
from utils.fbmsg import FBMsg
from .serializers import FileRenderSerializer
from django.http import StreamingHttpResponse
from .files import FileRenderCN, FileRenderEN
from rest_framework.settings import api_settings
from .auth import issue_session_token, revoke_staff_tokens


def _staff_login_client_ip(request):
    """Use the address supplied by the deployment proxy when available."""
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if forwarded:
        return forwarded.split(',')[0].strip() or 'unknown'
    return request.META.get('REMOTE_ADDR') or 'unknown'


def _staff_login_cache_key(scope, value):
    digest = hashlib.sha256(str(value).encode('utf-8')).hexdigest()
    return 'greaterwms:staff-login:%s:%s' % (scope, digest)


def _increment_login_counter(key, timeout):
    """Increment a short-lived counter; fail open if cache is unavailable."""
    try:
        if cache.add(key, 1, timeout=timeout):
            return 1
        return cache.incr(key)
    except (ValueError, TypeError):
        # A cache restart between add/incr should not make every operator
        # unable to log in. The account-level lockout is no longer used here.
        try:
            cache.set(key, 1, timeout=timeout)
        except Exception:
            pass
        return 1
    except Exception:
        return 1


def _staff_login_rate_limited(request, staff_name):
    timeout = settings.STAFF_LOGIN_RATE_LIMIT_WINDOW_SECONDS
    client_ip = _staff_login_client_ip(request)
    account = str(staff_name).strip().casefold()
    account_key = _staff_login_cache_key('account-ip', '%s\x00%s' % (client_ip, account))
    ip_key = _staff_login_cache_key('ip', client_ip)
    account_count = _increment_login_counter(account_key, timeout)
    ip_count = _increment_login_counter(ip_key, timeout)
    return (
        account_count > settings.STAFF_LOGIN_ACCOUNT_RATE_LIMIT
        or ip_count > settings.STAFF_LOGIN_IP_RATE_LIMIT
    )


def _clear_staff_login_account_counter(request, staff_name):
    client_ip = _staff_login_client_ip(request)
    account = str(staff_name).strip().casefold()
    cache.delete(_staff_login_cache_key('account-ip', '%s\x00%s' % (client_ip, account)))


@csrf_exempt
def staff_login(request, *args, **kwargs):
    """Issue a staff session without requiring an administrator session.

    Staff names are tenant-scoped in the data model. Direct login therefore
    requires the name to identify exactly one active non-admin staff record;
    ambiguous names are rejected instead of guessing a tenant.
    """
    if request.method != 'POST':
        return JsonResponse({'detail': 'Method not allowed'}, status=405)

    try:
        post_data = json.loads(request.body.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return JsonResponse({'detail': 'Request body must be valid JSON'}, status=400)

    if not isinstance(post_data, dict):
        return JsonResponse({'detail': 'Request body must be a JSON object'}, status=400)

    staff_name = str(post_data.get('staff_name', post_data.get('name', ''))).strip()
    raw_check_code = post_data.get('check_code')
    if not staff_name or raw_check_code in (None, ''):
        return JsonResponse({'detail': 'Staff name and check code are required'}, status=400)

    if _staff_login_rate_limited(request, staff_name):
        return JsonResponse(
            {'detail': 'Too many login attempts. Please try again later'},
            status=429,
        )

    try:
        check_code = int(raw_check_code)
    except (TypeError, ValueError):
        return JsonResponse({'detail': 'The verification code is incorrect'}, status=401)

    with transaction.atomic():
        matches = list(ListModel.objects.select_for_update().filter(
            staff_name__iexact=staff_name,
            is_delete=False,
        ).exclude(staff_type__iexact='Admin'))
        if not matches:
            return JsonResponse({'detail': 'Invalid staff credentials'}, status=401)
        if len(matches) > 1:
            return JsonResponse(
                {'detail': 'Staff account is ambiguous; contact an administrator'},
                status=409,
            )
        staff_record = matches[0]
        if staff_record.is_delete or str(staff_record.staff_type).strip().casefold() == 'admin':
            return JsonResponse({'detail': 'Invalid staff credentials'}, status=401)
        if staff_record.is_lock:
            return JsonResponse(
                {'detail': 'Staff account is locked. Please contact an administrator'},
                status=423,
            )

        if staff_record.check_code != check_code:
            return JsonResponse({'detail': 'Invalid staff credentials'}, status=401)

        staff_record.error_check_code_counter = 0
        staff_record.save(update_fields=['error_check_code_counter', 'update_time'])
        _clear_staff_login_account_counter(request, staff_name)
        api_token = issue_session_token(staff_record, token_kind='staff')

    ret = FBMsg.ret()
    ret['msg'] = 'Success Login'
    ret['data'] = {
        'name': staff_record.staff_name,
        # ``openid`` is retained as the frontend's historical token field.
        'openid': api_token,
        'token': api_token,
        'tenant_openid': staff_record.openid,
        'user_id': staff_record.id,
        'staff_type': staff_record.staff_type,
        'login_mode': 'user',
    }
    return JsonResponse(ret, status=200)


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
