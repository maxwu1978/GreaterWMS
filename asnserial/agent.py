import hashlib
import json
import secrets
from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import APIException, PermissionDenied

from staff.models import ListModel as Staff

from .models import AgentCommandPreview


AGENT_CLIENT = 'greaterwms-cli'
WORKFLOW_ROLES = frozenset({'admin', 'manager', 'supervisor', 'inbound', 'stockcontrol'})
SUPPORTED_OPERATIONS = frozenset({
    'asn.create',
    'asn.detail.create',
    'asn.eta',
    'asn.arrival',
    'asn.reserve_staging',
    'asn.unload_start',
    'asn.unload_finish',
    'asn.receive',
    'asn.putaway',
    'asn.putaway_bulk',
    'serial.resolve',
    'serial.resolve_quantity',
    'serial.exception_move',
    'serial.exception_move_quantity',
    'packlist.confirm',
    'packlist.import',
    'serial.import',
    'inspection.import',
})


def is_agent_request(request):
    return str(request.META.get('HTTP_X_AGENT_CLIENT') or '').strip().lower() == AGENT_CLIENT


def require_agent_role(request, roles=WORKFLOW_ROLES):
    """Require an authenticated warehouse role for CLI workflow mutations."""
    if not is_agent_request(request):
        return None
    openid = getattr(getattr(request, 'auth', None), 'openid', None)
    operator_id = request.META.get('HTTP_OPERATOR')
    staff = Staff.objects.filter(openid=openid, id=operator_id, is_delete=False).first()
    if staff is None:
        raise PermissionDenied('A valid operator staff id is required for CLI workflow commands')
    role = str(staff.staff_type or '').strip().lower()
    if role not in {str(item).strip().lower() for item in roles}:
        raise PermissionDenied('Operator role is not allowed to perform this workflow command')
    return staff


def _canonical(value):
    if isinstance(value, dict):
        return {str(key): _canonical(item) for key, item in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return [_canonical(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def payload_hash(payload):
    encoded = json.dumps(_canonical(payload), ensure_ascii=True, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(encoded.encode('utf-8')).hexdigest()


def request_payload(request, extra=None):
    payload = {}
    for key, value in request.data.items():
        if key in {'confirmation_token', 'idempotency_key', '_agent_preview', 'preview'}:
            continue
        if hasattr(value, 'tolist'):
            value = value.tolist()
        payload[str(key)] = value
    if extra:
        payload.update(extra)
    return payload


def _control_value(request, name):
    return request.data.get(name) or request.META.get('HTTP_' + name.upper().replace('-', '_'))


def create_preview(request, operation, payload, resource_id='', asn_code=''):
    if operation not in SUPPORTED_OPERATIONS:
        raise APIException({'detail': 'Unsupported agent operation', 'operation': operation})
    require_agent_role(request)
    token = secrets.token_urlsafe(32)
    now = timezone.now()
    command = AgentCommandPreview.objects.create(
        openid=request.auth.openid,
        operation=operation,
        resource_id=str(resource_id or ''),
        asn_code=str(asn_code or ''),
        payload_hash=payload_hash(payload),
        confirmation_token_hash=hashlib.sha256(token.encode('utf-8')).hexdigest(),
        preview_payload=_canonical(payload),
        created_by=request.META.get('HTTP_OPERATOR', ''),
        expires_at=now + timedelta(minutes=15),
    )
    return {
        'detail': 'preview',
        'operation': operation,
        'confirmation_token': token,
        'evidence_id': 'AGENT-PREVIEW-%s' % command.id,
        'preview_id': command.id,
        'payload_hash': command.payload_hash,
        'expires_at': command.expires_at.isoformat(),
    }


def consume_preview(request, operation, payload, resource_id='', asn_code=''):
    """Validate a CLI preview token and return (command, replay_result)."""
    if not is_agent_request(request):
        return None, None
    require_agent_role(request)
    token = _control_value(request, 'confirmation_token')
    idempotency_key = _control_value(request, 'idempotency_key')
    if not token or not idempotency_key:
        raise APIException({
            'detail': 'A confirmation token and idempotency key are required. Run the command with --dry-run first.',
            'code': 'AGENT_CONFIRMATION_REQUIRED',
        })
    token_hash = hashlib.sha256(str(token).encode('utf-8')).hexdigest()
    with transaction.atomic():
        command = AgentCommandPreview.objects.select_for_update().filter(
            openid=request.auth.openid,
            confirmation_token_hash=token_hash,
        ).first()
        if command is None:
            raise APIException({'detail': 'Confirmation token is invalid or belongs to another tenant', 'code': 'AGENT_TOKEN_INVALID'})
        if command.operation != operation or command.resource_id != str(resource_id or ''):
            raise APIException({'detail': 'Confirmation token does not match this operation', 'code': 'AGENT_TOKEN_MISMATCH'})
        if command.asn_code and command.asn_code != str(asn_code or ''):
            raise APIException({'detail': 'Confirmation token does not match this ASN', 'code': 'AGENT_TOKEN_MISMATCH'})
        if command.payload_hash != payload_hash(payload):
            raise APIException({'detail': 'Payload differs from the reviewed preview', 'code': 'AGENT_PAYLOAD_CHANGED'})
        if command.idempotency_key and command.idempotency_key != str(idempotency_key):
            raise APIException({'detail': 'Idempotency key differs from the reviewed command', 'code': 'AGENT_IDEMPOTENCY_CHANGED'})
        if command.status == AgentCommandPreview.EXECUTED:
            return command, command.result
        if command.expires_at <= timezone.now():
            raise APIException({'detail': 'Confirmation token has expired; create a new preview', 'code': 'AGENT_TOKEN_EXPIRED'})
        command.idempotency_key = str(idempotency_key)
        command.save(update_fields=['idempotency_key'])
        return command, None


def complete_preview(command, result):
    if command is None:
        return
    command.status = AgentCommandPreview.EXECUTED
    command.result = json.loads(json.dumps(result, ensure_ascii=True, default=str))
    command.used_at = timezone.now()
    command.save(update_fields=['status', 'result', 'used_at'])
