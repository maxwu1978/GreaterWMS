import hashlib
import json
import secrets
from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import APIException, PermissionDenied, ValidationError

from staff.models import ListModel as Staff

from .models import (
    AgentCommandPreview,
    EntityProvenance,
    OperationAudit,
    SourceEvidence,
    SourceExtraction,
)


AGENT_CLIENT = 'greaterwms-cli'
AI_AGENT_CLIENT = 'greaterwms-ai'
# Warehouse operators own customer-email intake and the inbound ASN lifecycle.
# Keep master-data administration role-gated elsewhere; this set only controls
# operational Agent previews and confirmations.
WORKFLOW_ROLES = frozenset({'admin', 'manager', 'supervisor', 'inbound', 'warehouse', 'stockcontrol'})
OUTBOUND_WORKFLOW_ROLES = frozenset({'admin', 'manager', 'supervisor', 'outbound', 'warehouse'})
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
    'outbound.create',
    'outbound.detail.create',
    'outbound.release',
    'outbound.order_release',
    'outbound.pick',
    'outbound.dispatch',
    'outbound.pod',
    'outbound.cancel_intransit',
    'tenant.cleanup',
})

EXTERNAL_INSTRUCTION_OPERATIONS = frozenset({
    'asn.create',
    'asn.detail.create',
    'outbound.create',
    'outbound.detail.create',
    'packlist.import',
})


def execution_surface(request):
    value = str(
        request.META.get('HTTP_X_AGENT_SURFACE')
        or request.META.get('HTTP_EXECUTION_SURFACE')
        or ''
    ).strip().lower()
    if value in {'ai', 'web', 'cli'}:
        return value.upper()
    if str(request.META.get('HTTP_X_AGENT_CLIENT') or '').strip().lower() == AI_AGENT_CLIENT:
        return 'AI'
    if str(request.META.get('HTTP_X_AGENT_CLIENT') or '').strip().lower() == AGENT_CLIENT:
        return 'CLI'
    return 'WEB'


def is_agent_request(request):
    return str(request.META.get('HTTP_X_AGENT_CLIENT') or '').strip().lower() in {
        AGENT_CLIENT,
        AI_AGENT_CLIENT,
    }


def is_web_request(request):
    # DRF requests always expose ``method``.  Internal service adapters used
    # by existing workflows may intentionally omit it and keep the legacy
    # direct-call behavior; they are not browser entry points.
    return not is_agent_request(request) and bool(getattr(request, 'method', None))


def agent_roles_for_operation(operation):
    operation = str(operation or '').strip().lower()
    if operation == 'outbound.cancel_intransit':
        return frozenset({'admin'})
    if operation == 'tenant.cleanup':
        return frozenset({'admin'})
    if operation.startswith('outbound.'):
        return OUTBOUND_WORKFLOW_ROLES
    return WORKFLOW_ROLES


def require_agent_role(request, roles=WORKFLOW_ROLES):
    """Require an authenticated warehouse role for CLI workflow mutations."""
    if not is_agent_request(request):
        return None
    return _require_workflow_role(request, roles, 'CLI workflow')


def _require_workflow_role(request, roles, surface):
    """Enforce an operation role for an authenticated workflow surface."""
    openid = getattr(getattr(request, 'auth', None), 'openid', None)
    identity = getattr(request, 'auth', None)
    operator_id = request.META.get('HTTP_OPERATOR') or getattr(identity, 'staff_id', None)
    staff = Staff.objects.filter(openid=openid, id=operator_id, is_delete=False).first()
    if staff is None:
        raise PermissionDenied('A valid operator staff id is required for %s commands' % surface)
    identity_staff_id = getattr(identity, 'staff_id', None)
    if not getattr(identity, 'is_admin', False) and identity_staff_id is not None:
        if str(operator_id) != str(identity_staff_id):
            raise PermissionDenied('Operator identity does not match the authenticated user')
    role = str(staff.staff_type or '').strip().lower()
    if role not in {str(item).strip().lower() for item in roles}:
        raise PermissionDenied('Operator role is not allowed to perform this %s command' % surface)
    return staff


def require_web_workflow_role(request, operation):
    """Apply the same operation matrix to the browser preview/approval flow."""
    return _require_workflow_role(
        request,
        agent_roles_for_operation(operation),
        'Web workflow',
    )


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
        if key in {
            'confirmation_token',
            'idempotency_key',
            '_agent_preview',
            'preview',
            'web_preview_id',
            'web_preview_stage',
            'agent_preview_id',
            'preview_id',
            'source_evidence_id',
        }:
            continue
        if hasattr(value, 'tolist'):
            value = value.tolist()
        payload[str(key)] = value
    if extra:
        payload.update(extra)
    return payload


def _control_value(request, name):
    return request.data.get(name) or request.META.get('HTTP_' + name.upper().replace('-', '_'))


def _source_for_request(request, source_evidence_id, operation, required=False):
    source_id = str(source_evidence_id or '').strip()
    source = None
    if source_id:
        source = SourceEvidence.objects.filter(
            id=source_id,
            openid=request.auth.openid,
            status__in=(SourceEvidence.CAPTURED, SourceEvidence.USED),
        ).first()
        if source is None:
            raise ValidationError({'detail': 'Source evidence does not exist or is not available', 'code': 'SOURCE_EVIDENCE_INVALID'})
        source_operations = {
            operation,
            'external.instruction',
            'asn.create' if operation == 'asn.detail.create' else '',
            'outbound.create' if operation == 'outbound.detail.create' else '',
        }
        if source.operation not in source_operations:
            raise ValidationError({'detail': 'Source evidence is not bound to this operation', 'code': 'SOURCE_EVIDENCE_MISMATCH'})
    if required and source is None:
        raise ValidationError({'detail': 'Source evidence is required before this external instruction can be written', 'code': 'SOURCE_EVIDENCE_REQUIRED'})
    return source


_SENSITIVE_EVIDENCE_KEYS = frozenset({
    'password',
    'check_code',
    'token',
    'openid',
    'confirmation_token',
    'api_key',
    'authorization',
})


def _scrub_evidence_value(value):
    if isinstance(value, dict):
        return {
            str(key): _scrub_evidence_value(item)
            for key, item in value.items()
            if str(key).strip().lower() not in _SENSITIVE_EVIDENCE_KEYS
        }
    if isinstance(value, list):
        return [_scrub_evidence_value(item) for item in value]
    return value


def create_source_evidence(request, source_type, operation, metadata=None, extracted_fields=None,
                           content_hash='', storage_uri='', storage_size=0, ai_session_id=''):
    """Capture source metadata before an AI or web preview is created."""
    if not getattr(getattr(request, 'auth', None), 'openid', None):
        raise PermissionDenied('A tenant-authenticated operator is required to capture source evidence')
    identity = getattr(request, 'auth', None)
    metadata = metadata if isinstance(metadata, dict) else {}
    # Never accept credentials or bearer tokens as evidence metadata.
    metadata = _scrub_evidence_value(metadata)
    mailbox_account = str(
        metadata.get('mailbox_account')
        or metadata.get('mailbox')
        or metadata.get('email_account')
        or ''
    ).strip()[:255]
    message_id = str(metadata.get('message_id') or '').strip()[:512]
    thread_id = str(metadata.get('thread_id') or '').strip()[:512]
    normalized_hash = str(content_hash or '')[:64]
    if source_type == SourceEvidence.EMAIL and mailbox_account and message_id and normalized_hash:
        existing = SourceEvidence.objects.filter(
            openid=request.auth.openid,
            source_type=SourceEvidence.EMAIL,
            mailbox_account=mailbox_account,
            message_id=message_id,
            content_hash=normalized_hash,
        ).first()
        if existing is not None:
            return existing
    source = SourceEvidence.objects.create(
        openid=request.auth.openid,
        mailbox_account=mailbox_account,
        message_id=message_id,
        thread_id=thread_id,
        source_type=str(source_type or SourceEvidence.AI_AGENT).upper(),
        operation=str(operation or 'external.instruction').strip().lower(),
        content_hash=normalized_hash,
        captured_by=str(getattr(identity, 'staff_id', '') or request.META.get('HTTP_OPERATOR') or ''),
        captured_by_name=str(getattr(identity, 'staff_name', '') or ''),
        ai_session_id=str(ai_session_id or '')[:255],
        metadata=metadata,
        storage_uri=str(storage_uri or '')[:1000],
        storage_size=max(int(storage_size or 0), 0),
    )
    for field in extracted_fields or []:
        if not isinstance(field, dict) or not str(field.get('field_name') or '').strip():
            continue
        field_name = str(field.get('field_name')).strip()
        if field_name.lower() in _SENSITIVE_EVIDENCE_KEYS:
            continue
        SourceExtraction.objects.create(
            source=source,
            field_name=field_name[:128],
            raw_value=str(field.get('raw_value') or ''),
            normalized_value=str(field.get('normalized_value') or ''),
            source_location=str(field.get('source_location') or '')[:255],
            confidence=field.get('confidence'),
            human_confirmed=bool(field.get('human_confirmed', False)),
            used_for_write=bool(field.get('used_for_write', False)),
        )
    return source


def _source_summary(source):
    if source is None:
        return None
    return {
        'id': source.id,
        'source_type': source.source_type,
        'operation': source.operation,
        'captured_by': source.captured_by_name or source.captured_by,
        'captured_at': source.captured_at.isoformat(),
        'content_hash': source.content_hash,
        'metadata': source.metadata,
        'extractions': [
            {
                'field_name': item.field_name,
                'normalized_value': item.normalized_value,
                'source_location': item.source_location,
                'confidence': item.confidence,
                'human_confirmed': item.human_confirmed,
                'used_for_write': item.used_for_write,
            }
            for item in source.extractions.all()
        ],
    }


def _record_operation_audit(command, status, request=None, result=None,
                            failure_reason='', approved_at=None):
    """Write a safe audit event without persisting request credentials or payloads."""
    identity = getattr(request, 'auth', None) if request is not None else None
    source = command.source_evidence
    return OperationAudit.objects.create(
        preview=command,
        source_evidence=source,
        openid=command.openid,
        operation=command.operation,
        execution_surface=command.execution_surface,
        status=status,
        operator_id=str(
            getattr(identity, 'staff_id', '')
            or command.created_by
            or (request.META.get('HTTP_OPERATOR', '') if request is not None else '')
        ),
        operator_name=str(getattr(identity, 'staff_name', '') or ''),
        operator_role=str(getattr(identity, 'staff_type', '') or ''),
        ai_session_id=str(getattr(source, 'ai_session_id', '') or ''),
        payload_hash=command.payload_hash,
        result=result if isinstance(result, dict) else {},
        failure_reason=str(failure_reason or '')[:4000],
        approved_at=approved_at,
    )


def _provenance_value(value):
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)
    return str(value if value is not None else '')


def _record_entity_provenance(command, result):
    source = command.source_evidence
    if source is None or not isinstance(result, dict):
        return
    entity_sections = (
        ('ASN', 'asn', 'header'),
        ('ASN_DETAIL', 'asn_detail', 'detail'),
        ('OUTBOUND', 'outbound', 'header'),
        ('OUTBOUND_DETAIL', 'outbound_detail', 'detail'),
    )
    for entity_type, result_key, payload_key in entity_sections:
        entity = result.get(result_key)
        if not isinstance(entity, dict):
            continue
        entity_ref = str(
            entity.get('asn_code')
            or entity.get('dn_code')
            or entity.get('id')
            or ''
        )
        if not entity_ref:
            continue
        payload = command.preview_payload.get(payload_key) or {}
        if not isinstance(payload, dict):
            continue
        for field_name, value in payload.items():
            if field_name in {'web_preview_id', 'web_preview_stage', 'agent_preview_id', 'preview_id'}:
                continue
            values = value if isinstance(value, list) else [value]
            for index, item in enumerate(values):
                stored_name = '%s[%s]' % (field_name, index) if isinstance(value, list) else field_name
                extraction = source.extractions.filter(field_name=field_name).first()
                EntityProvenance.objects.create(
                    source=source,
                    source_extraction=extraction,
                    openid=command.openid,
                    entity_type=entity_type,
                    entity_ref=entity_ref,
                    field_name=stored_name,
                    raw_value=_provenance_value(item),
                    normalized_value=_provenance_value(item),
                    used_for_write=True,
                )


def create_web_preview(request, operation, payload, page=''):
    if operation not in {'asn.create', 'outbound.create'}:
        raise ValidationError({'detail': 'Only ASN and outbound external instructions can use the Web preview flow'})
    identity = getattr(request, 'auth', None)
    if not getattr(identity, 'openid', None):
        raise PermissionDenied('A tenant-authenticated operator is required for a Web preview')
    require_web_workflow_role(request, operation)
    source = create_source_evidence(
        request,
        SourceEvidence.WEB_FORM,
        operation,
        metadata={'page': str(page or operation), 'entry_point': 'WMS web'},
        content_hash=payload_hash(payload),
    )
    now = timezone.now()
    command = AgentCommandPreview.objects.create(
        openid=request.auth.openid,
        operation=operation,
        payload_hash=payload_hash(payload),
        confirmation_token_hash='',
        preview_payload=_canonical(payload),
        status=AgentCommandPreview.PENDING,
        execution_surface='WEB',
        source_evidence=source,
        created_by=str(getattr(identity, 'staff_id', '') or request.META.get('HTTP_OPERATOR') or ''),
        expires_at=now + timedelta(minutes=15),
    )
    _record_operation_audit(command, OperationAudit.PREVIEWED, request=request)
    return {
        'detail': 'preview',
        'execution_surface': 'web',
        'preview_id': command.id,
        'payload_hash': command.payload_hash,
        'expires_at': command.expires_at.isoformat(),
        'source_evidence': _source_summary(source),
    }


def approve_surface_preview(request, preview_id, surface):
    with transaction.atomic():
        command = AgentCommandPreview.objects.select_for_update().select_related('source_evidence').filter(
            id=preview_id,
            openid=request.auth.openid,
            execution_surface=surface,
        ).first()
        if command is None:
            raise ValidationError({
                'detail': '%s preview does not exist' % surface.title(),
                'code': '%s_PREVIEW_INVALID' % surface,
            })
        if surface == 'WEB':
            require_web_workflow_role(request, command.operation)
        if command.status == AgentCommandPreview.EXECUTED:
            return command
        if command.expires_at <= timezone.now():
            raise ValidationError({
                'detail': '%s preview has expired; create a new preview' % surface.title(),
                'code': '%s_PREVIEW_EXPIRED' % surface,
            })
        if command.status not in {AgentCommandPreview.PENDING, AgentCommandPreview.APPROVED}:
            raise ValidationError({
                'detail': '%s preview cannot be approved in its current state' % surface.title(),
                'code': '%s_PREVIEW_STATE_INVALID' % surface,
            })
        if command.status == AgentCommandPreview.APPROVED:
            return command
        command.status = AgentCommandPreview.APPROVED
        command.idempotency_key = '%s-%s' % (surface.lower(), command.id)
        command.save(update_fields=['status', 'idempotency_key'])
        _record_operation_audit(
            command,
            OperationAudit.APPROVED,
            request=request,
            approved_at=timezone.now(),
        )
        return command


def approve_web_preview(request, preview_id):
    return approve_surface_preview(request, preview_id, 'WEB')


def approve_ai_preview(request, preview_id):
    return approve_surface_preview(request, preview_id, 'AI')


def _consume_approved_preview(request, operation, payload, section, preview_id,
                              execution_surface, asn_code=''):
    allowed_detail_operation = {
        'asn.create': {'asn.create', 'asn.detail.create'},
        'outbound.create': {'outbound.create', 'outbound.detail.create'},
    }
    with transaction.atomic():
        command = AgentCommandPreview.objects.select_for_update().select_related('source_evidence').filter(
            id=preview_id,
            openid=request.auth.openid,
            execution_surface=execution_surface,
        ).first()
        if command is None or operation not in allowed_detail_operation.get(command.operation, set()):
            raise ValidationError({
                'detail': '%s preview does not match this operation' % execution_surface.title(),
                'code': '%s_PREVIEW_MISMATCH' % execution_surface,
            })
        if command.status == AgentCommandPreview.EXECUTED:
            return command, command.result
        if command.status != AgentCommandPreview.APPROVED:
            raise ValidationError({
                'detail': 'Approve the %s preview before writing' % execution_surface.title(),
                'code': '%s_APPROVAL_REQUIRED' % execution_surface,
            })
        if command.expires_at <= timezone.now():
            raise ValidationError({
                'detail': '%s preview has expired; create a new preview' % execution_surface.title(),
                'code': '%s_PREVIEW_EXPIRED' % execution_surface,
            })
        expected = command.preview_payload.get(section)
        actual_payload = dict(payload)
        # The server assigns the ASN/DN number between the header and detail
        # writes; that generated identifier is not user-editable source data.
        if section == 'detail':
            actual_payload.pop('asn_code', None)
            actual_payload.pop('dn_code', None)
        if expected is None or payload_hash(expected) != payload_hash(actual_payload):
            raise ValidationError({
                'detail': 'Payload differs from the reviewed %s preview' % execution_surface.lower(),
                'code': '%s_PAYLOAD_CHANGED' % execution_surface,
            })
        # Parent and detail are committed by the outer workflow transaction;
        # only that transaction has the complete result for audit/provenance.
        command._defer_completion = True
        return command, None


def consume_web_preview(request, operation, payload, section, resource_id='', asn_code=''):
    if is_agent_request(request) and execution_surface(request) == 'AI':
        preview_id = request.data.get('agent_preview_id') or request.data.get('preview_id')
        if preview_id:
            return _consume_approved_preview(
                request,
                operation,
                payload,
                section,
                preview_id,
                'AI',
                asn_code=asn_code,
            )
    if is_agent_request(request):
        return consume_preview(
            request,
            operation,
            payload,
            resource_id=resource_id,
            asn_code=asn_code,
        )
    if not is_web_request(request):
        return None, None
    preview_id = request.data.get('web_preview_id')
    if not preview_id:
        raise ValidationError({
            'detail': 'Web preview and approval are required before this external instruction can be written',
            'code': 'WEB_PREVIEW_REQUIRED',
        })
    return _consume_approved_preview(
        request,
        operation,
        payload,
        section,
        preview_id,
        'WEB',
        asn_code=asn_code,
    )


def create_source_capture(request, data):
    source_type = str(data.get('source_type') or SourceEvidence.EMAIL).upper()
    if source_type not in {SourceEvidence.EMAIL, SourceEvidence.AI_AGENT, SourceEvidence.CLI}:
        raise ValidationError({'source_type': 'AI source capture supports EMAIL, AI_AGENT or CLI'})
    return create_source_evidence(
        request,
        source_type,
        data.get('operation') or 'external.instruction',
        metadata=data.get('metadata') or {},
        extracted_fields=data.get('extracted_fields') or [],
        content_hash=data.get('content_hash') or '',
        storage_uri=data.get('storage_uri') or '',
        storage_size=data.get('storage_size') or 0,
        ai_session_id=data.get('ai_session_id') or '',
    )


def create_preview(request, operation, payload, resource_id='', asn_code='', source_evidence_id=''):
    if operation not in SUPPORTED_OPERATIONS:
        raise APIException({'detail': 'Unsupported agent operation', 'operation': operation})
    require_agent_role(request, agent_roles_for_operation(operation))
    surface = execution_surface(request)
    source = _source_for_request(
        request,
        source_evidence_id or request.data.get('source_evidence_id'),
        operation,
        required=surface == 'AI' and operation in EXTERNAL_INSTRUCTION_OPERATIONS,
    )
    token = secrets.token_urlsafe(32)
    now = timezone.now()
    command = AgentCommandPreview.objects.create(
        openid=request.auth.openid,
        operation=operation,
        resource_id=str(resource_id or ''),
        asn_code=str(asn_code or ''),
        payload_hash=payload_hash(payload),
        confirmation_token_hash=(
            hashlib.sha256(token.encode('utf-8')).hexdigest()
            if surface != 'AI' else ''
        ),
        preview_payload=_canonical(payload),
        execution_surface=surface,
        source_evidence=source,
        created_by=request.META.get('HTTP_OPERATOR', ''),
        expires_at=now + timedelta(minutes=15),
    )
    _record_operation_audit(command, OperationAudit.PREVIEWED, request=request)
    return {
        'detail': 'preview',
        'operation': operation,
        **({'confirmation_token': token} if surface != 'AI' else {}),
        'evidence_id': 'AGENT-PREVIEW-%s' % command.id,
        'preview_id': command.id,
        'payload_hash': command.payload_hash,
        'expires_at': command.expires_at.isoformat(),
        'execution_surface': surface.lower(),
        'source_evidence': _source_summary(source),
    }


def consume_preview(request, operation, payload, resource_id='', asn_code=''):
    """Validate a CLI preview token and return (command, replay_result)."""
    if not is_agent_request(request):
        return None, None
    require_agent_role(request, agent_roles_for_operation(operation))
    token = _control_value(request, 'confirmation_token')
    idempotency_key = _control_value(request, 'idempotency_key')
    if not token or not idempotency_key:
        if execution_surface(request) == 'AI' and operation in EXTERNAL_INSTRUCTION_OPERATIONS:
            raise ValidationError({
                'detail': 'AI previews must be approved with the structured AI action, not a CLI token',
                'code': 'AI_APPROVAL_REQUIRED',
            })
        raise ValidationError({
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
            raise ValidationError({'detail': 'Confirmation token is invalid or belongs to another tenant', 'code': 'AGENT_TOKEN_INVALID'})
        if command.operation != operation or command.resource_id != str(resource_id or ''):
            raise ValidationError({'detail': 'Confirmation token does not match this operation', 'code': 'AGENT_TOKEN_MISMATCH'})
        if command.asn_code and command.asn_code != str(asn_code or ''):
            raise ValidationError({'detail': 'Confirmation token does not match this ASN', 'code': 'AGENT_TOKEN_MISMATCH'})
        if command.payload_hash != payload_hash(payload):
            raise ValidationError({'detail': 'Payload differs from the reviewed preview', 'code': 'AGENT_PAYLOAD_CHANGED'})
        if command.idempotency_key and command.idempotency_key != str(idempotency_key):
            raise ValidationError({'detail': 'Idempotency key differs from the reviewed command', 'code': 'AGENT_IDEMPOTENCY_CHANGED'})
        if command.status == AgentCommandPreview.EXECUTED:
            return command, command.result
        if command.expires_at <= timezone.now():
            raise ValidationError({'detail': 'Confirmation token has expired; create a new preview', 'code': 'AGENT_TOKEN_EXPIRED'})
        command.idempotency_key = str(idempotency_key)
        command.save(update_fields=['idempotency_key'])
        if not OperationAudit.objects.filter(
            preview=command,
            status=OperationAudit.APPROVED,
        ).exists():
            _record_operation_audit(
                command,
                OperationAudit.APPROVED,
                request=request,
                approved_at=timezone.now(),
            )
        return command, None


def complete_preview(command, result):
    if command is None:
        return
    if getattr(command, '_defer_completion', False):
        return
    command.status = AgentCommandPreview.EXECUTED
    command.result = json.loads(json.dumps(result, ensure_ascii=True, default=str))
    command.used_at = timezone.now()
    command.save(update_fields=['status', 'result', 'used_at'])
    if command.source_evidence_id:
        SourceEvidence.objects.filter(id=command.source_evidence_id).update(
            status=SourceEvidence.USED,
            used_at=timezone.now(),
        )
    _record_operation_audit(
        command,
        OperationAudit.SUCCEEDED,
        result=command.result or {},
    )
    _record_entity_provenance(command, command.result or {})
