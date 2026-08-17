from django.http import StreamingHttpResponse, JsonResponse
from django.template.response import TemplateResponse
from django.conf import settings
from wsgiref.util import FileWrapper
from rest_framework.exceptions import APIException
from utils.health import health
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


def cli_install(request):
    """Return the public, machine-readable CLI installation contract."""
    if request.method != 'GET':
        return JsonResponse({'detail': 'Method not allowed'}, status=405)

    response = JsonResponse({
        'schema_version': '1',
        'product': 'GreaterWMS',
        'web_url': 'https://app.maxsmartwms.online',
        'api_base_url': 'https://api.maxsmartwms.online',
        'cli': {
            'entrypoint': 'tools/greaterwms.mjs',
            'runtime': {
                'node_min': '18.0.0',
                'recommended': 'Node.js 18 LTS or newer',
            },
            'repository': 'https://github.com/maxwu1978/GreaterWMS',
            'source_ref': 'codex/cli-install-info',
            'install_commands': [
                'git clone --branch codex/cli-install-info https://github.com/maxwu1978/GreaterWMS.git',
                'cd GreaterWMS',
                'node tools/greaterwms.mjs --help',
            ],
            'auth': [
                {
                    'role': 'Admin',
                    'command': 'node tools/greaterwms.mjs login --env production --name ADMIN',
                    'endpoint': '/login/',
                    'credential': 'username and password',
                },
                {
                    'role': 'Staff',
                    'command': 'node tools/greaterwms.mjs login --env production --staff --name STAFF',
                    'endpoint': '/staff/login/',
                    'credential': 'staff name and check code',
                    'check_code_env': 'GREATERWMS_CHECK_CODE',
                },
            ],
            'first_commands': [
                'node tools/greaterwms.mjs auth status --json',
                'node tools/greaterwms.mjs dashboard-operations list --env production --json',
                'node tools/greaterwms.mjs receiving list --env production --json',
            ],
            'safety': [
                'The CLI calls GreaterWMS APIs and never writes directly to the database.',
                'Read commands run after login; write commands require --dry-run and then --confirm.',
                'Agent operations require a server confirmation token and idempotency key.',
                'Passwords and check codes are never written to the local session file.',
            ],
        },
    })
    response['Cache-Control'] = 'no-store'
    return response
