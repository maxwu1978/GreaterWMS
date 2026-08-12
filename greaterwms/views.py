from django.http import StreamingHttpResponse, JsonResponse
from django.template.response import TemplateResponse
from django.conf import settings
from wsgiref.util import FileWrapper
from rest_framework.exceptions import APIException
import mimetypes, os


NO_CACHE = 'no-cache, no-store, must-revalidate'


def index(request):
    response = TemplateResponse(request, 'dist/spa/index.html')
    response['Cache-Control'] = NO_CACHE
    return response


def _stream_asset(request):
    path = str(settings.BASE_DIR) + '/templates/dist/spa' + request.path_info
    content_type, encoding = mimetypes.guess_type(path)
    response = StreamingHttpResponse(FileWrapper(open(path, 'rb')), content_type=content_type)
    response['Cache-Control'] = NO_CACHE
    return response

def robots(request):
    path = settings.BASE_DIR + request.path_info
    content_type, encoding = mimetypes.guess_type(path)
    resp = StreamingHttpResponse(FileWrapper(open(path, 'rb')), content_type=content_type)
    resp['Cache-Control'] = NO_CACHE
    return resp

def favicon(request):
    path = str(settings.BASE_DIR) + '/static/img/logo.png'
    content_type, encoding = mimetypes.guess_type(path)
    resp = StreamingHttpResponse(FileWrapper(open(path, 'rb')), content_type=content_type)
    resp['Cache-Control'] = NO_CACHE
    return resp

def css(request):
    return _stream_asset(request)

def js(request):
    return _stream_asset(request)

def statics(request):
    return _stream_asset(request)

def fonts(request):
    return _stream_asset(request)

def myip(request):
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(('8.8.8.8', 80))
    print(s.getsockname()[0])
    ip = s.getsockname()[0]
    s.close()
    return JsonResponse({"ip": ip})
