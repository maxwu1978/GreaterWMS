from django.http import FileResponse, StreamingHttpResponse, JsonResponse, HttpResponse
from django.template.response import TemplateResponse
from django.conf import settings
from wsgiref.util import FileWrapper
from rest_framework.exceptions import APIException
from utils.health import health
import io
import mimetypes
import os
import zipfile


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
            'download_url': 'https://api.maxsmartwms.online/cli/download/',
            'runtime': {
                'node_min': '18.0.0',
                'recommended': 'Node.js 18 LTS or newer',
            },
            'repository': 'https://github.com/maxwu1978/GreaterWMS',
            'source_ref': 'codex/cli-install-info',
            'install_commands': [
                'mkdir -p greaterwms-cli && cd greaterwms-cli',
                'curl -fsSL https://api.maxsmartwms.online/cli/download/ -o greaterwms.mjs',
                'chmod +x greaterwms.mjs && node greaterwms.mjs --help',
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
                'node tools/greaterwms.mjs source intake --env production --json',
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
        'skills': [
            {
                'name': 'wms-scheduled-email-intake',
                'version': '2.0.0',
                'description': 'Use the local Mail CLI to scan warehouse email, classify documents, reconcile GreaterWMS data, and prepare the next safe workflow step.',
                'download_url': 'https://api.maxsmartwms.online/skills/wms-scheduled-email-intake/download/',
                'archive': 'zip',
                'install_commands': [
                    'mkdir -p ~/.codex/skills && curl -fsSL https://api.maxsmartwms.online/skills/wms-scheduled-email-intake/download/ -o /tmp/wms-scheduled-email-intake.zip',
                    'unzip -q -o /tmp/wms-scheduled-email-intake.zip -d ~/.codex/skills',
                ],
                'safety': [
                    'The Skill is read-only by default and requires GreaterWMS dry-run and confirmation gates before writes.',
                    'It never sends or deletes email and never writes directly to the database.',
                ],
            },
        ],
    })
    response['Cache-Control'] = 'no-store'
    return response


def cli_download(request):
    """Download only the CLI entrypoint, without exposing the repository."""
    if request.method != 'GET':
        return JsonResponse({'detail': 'Method not allowed'}, status=405)

    cli_path = os.path.join(settings.BASE_DIR, 'tools', 'greaterwms.mjs')
    if not os.path.isfile(cli_path):
        return JsonResponse({'detail': 'CLI file is unavailable'}, status=404)

    response = FileResponse(
        open(cli_path, 'rb'),
        as_attachment=True,
        filename='greaterwms.mjs',
        content_type='text/javascript; charset=utf-8',
    )
    response['Cache-Control'] = 'no-store'
    return response


def email_intake_skill_download(request, archive_name='wms-scheduled-email-intake'):
    """Download the governed warehouse email intake Skill as a ZIP bundle."""
    if request.method != 'GET':
        return JsonResponse({'detail': 'Method not allowed'}, status=405)

    skill_root = os.path.join(
        settings.BASE_DIR,
        'tools',
        'skills',
        'wms-scheduled-email-intake',
    )
    skill_files = (
        'SKILL.md',
        os.path.join('agents', 'openai.yaml'),
        os.path.join('references', 'document-mapping.md'),
    )
    if not all(os.path.isfile(os.path.join(skill_root, path)) for path in skill_files):
        return JsonResponse({'detail': 'Email intake Skill is unavailable'}, status=404)

    archive = io.BytesIO()
    with zipfile.ZipFile(archive, mode='w', compression=zipfile.ZIP_DEFLATED) as bundle:
        for relative_path in skill_files:
            bundle.write(
                os.path.join(skill_root, relative_path),
                arcname=os.path.join(archive_name, relative_path),
            )

    response = HttpResponse(archive.getvalue(), content_type='application/zip')
    response['Content-Disposition'] = f'attachment; filename="{archive_name}.zip"'
    response['Cache-Control'] = 'no-store'
    return response


def legacy_email_intake_skill_download(request):
    """Compatibility URL for the pre-scheduled Skill name."""
    return email_intake_skill_download(request, archive_name='wms-email-intake-operator')
