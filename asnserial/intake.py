"""Source intake state helpers shared by the Codex and web read models."""

import hashlib
from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.utils import timezone
from rest_framework.exceptions import ValidationError

from .models import (
    MailboxSyncRun,
    SourceAttachment,
    SourceEvidence,
    SourceIntakeEvent,
    SourceIntakeRecord,
)


INTAKE_ROLES = frozenset({
    'admin', 'manager', 'supervisor', 'inbound', 'outbound', 'warehouse', 'qc',
})

STATUS_TRANSITIONS = {
    SourceIntakeRecord.CAPTURED: {
        SourceIntakeRecord.ANALYZING,
        SourceIntakeRecord.REVIEW_REQUIRED,
        SourceIntakeRecord.READY_FOR_PREVIEW,
        SourceIntakeRecord.APPROVAL_REQUIRED,
        SourceIntakeRecord.EXECUTING,
        SourceIntakeRecord.DUPLICATE,
        SourceIntakeRecord.BLOCKED,
        SourceIntakeRecord.FAILED,
    },
    SourceIntakeRecord.ANALYZING: {
        SourceIntakeRecord.REVIEW_REQUIRED,
        SourceIntakeRecord.READY_FOR_PREVIEW,
        SourceIntakeRecord.APPROVAL_REQUIRED,
        SourceIntakeRecord.EXECUTING,
        SourceIntakeRecord.DUPLICATE,
        SourceIntakeRecord.BLOCKED,
        SourceIntakeRecord.FAILED,
    },
    SourceIntakeRecord.REVIEW_REQUIRED: {
        SourceIntakeRecord.ANALYZING,
        SourceIntakeRecord.READY_FOR_PREVIEW,
        SourceIntakeRecord.APPROVAL_REQUIRED,
        SourceIntakeRecord.EXECUTING,
        SourceIntakeRecord.BLOCKED,
        SourceIntakeRecord.FAILED,
    },
    SourceIntakeRecord.READY_FOR_PREVIEW: {
        SourceIntakeRecord.APPROVAL_REQUIRED,
        SourceIntakeRecord.EXECUTING,
        SourceIntakeRecord.BLOCKED,
        SourceIntakeRecord.FAILED,
    },
    SourceIntakeRecord.APPROVAL_REQUIRED: {
        SourceIntakeRecord.EXECUTING,
        SourceIntakeRecord.BLOCKED,
        SourceIntakeRecord.FAILED,
    },
    SourceIntakeRecord.EXECUTING: {
        SourceIntakeRecord.COMPLETED,
        SourceIntakeRecord.BLOCKED,
        SourceIntakeRecord.FAILED,
    },
    SourceIntakeRecord.COMPLETED: set(),
    SourceIntakeRecord.BLOCKED: {
        SourceIntakeRecord.ANALYZING,
        SourceIntakeRecord.REVIEW_REQUIRED,
    },
    SourceIntakeRecord.DUPLICATE: set(),
    SourceIntakeRecord.FAILED: {
        SourceIntakeRecord.ANALYZING,
        SourceIntakeRecord.REVIEW_REQUIRED,
    },
}


def _text(value, limit=1000):
    return str(value or '').strip()[:limit]


def _metadata_value(metadata, *keys):
    for key in keys:
        value = metadata.get(key)
        if value not in (None, ''):
            return value
    return ''


def _parse_datetime(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except (TypeError, ValueError):
        return None
    if timezone.is_naive(parsed):
        return parsed
    if timezone.is_aware(parsed) and not timezone.is_aware(timezone.now()):
        return timezone.make_naive(parsed)
    return parsed


def _confidence(value):
    if value in (None, ''):
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if parsed < 0 or parsed > 1:
        return None
    return parsed


def _operation(metadata, source):
    value = str(_metadata_value(metadata, 'business_operation', 'document_operation', 'operation')).strip().lower()
    if value.startswith('asn') or value in {'inbound', 'receiving'}:
        return SourceIntakeRecord.INBOUND
    if value.startswith('outbound') or value in {'dn', 'delivery', 'shipping'}:
        return SourceIntakeRecord.OUTBOUND
    if source.source_type == SourceEvidence.EMAIL:
        return SourceIntakeRecord.UNKNOWN
    return SourceIntakeRecord.SUPPORTING


def _document_type(metadata):
    value = str(_metadata_value(metadata, 'document_type', 'document_class', 'classification')).strip().lower()
    mapping = {
        'inbound notice': SourceIntakeRecord.INBOUND_NOTICE,
        'inbound list': SourceIntakeRecord.INBOUND_NOTICE,
        'pack list': SourceIntakeRecord.PACK_LIST,
        'packlist': SourceIntakeRecord.PACK_LIST,
        'pick ticket': SourceIntakeRecord.PICK_TICKET,
        'delivery request': SourceIntakeRecord.DELIVERY_REQUEST,
        'appointment': SourceIntakeRecord.APPOINTMENT,
        'qc': SourceIntakeRecord.QC_SCAN,
        'scan sheet': SourceIntakeRecord.QC_SCAN,
        'qc / scan sheet': SourceIntakeRecord.QC_SCAN,
        'other': SourceIntakeRecord.OTHER,
    }
    return mapping.get(value, SourceIntakeRecord.OTHER)


def _attachment_hash(attachment):
    value = _text(
        attachment.get('sha256')
        or attachment.get('content_hash')
        or attachment.get('hash'),
        64,
    ).lower()
    if value:
        return value
    fallback = '|'.join([
        _text(attachment.get('name') or attachment.get('filename'), 512),
        _text(attachment.get('content_type') or attachment.get('mime_type'), 255),
        str(attachment.get('size') or attachment.get('storage_size') or 0),
    ])
    return hashlib.sha256(fallback.encode('utf-8')).hexdigest()


def _create_attachments(source, openid, metadata):
    attachments = metadata.get('attachments')
    if not isinstance(attachments, list):
        return
    for item in attachments:
        if not isinstance(item, dict):
            continue
        name = _text(item.get('name') or item.get('filename'), 512)
        if not name:
            continue
        content_hash = _attachment_hash(item)
        SourceAttachment.objects.get_or_create(
            source=source,
            content_hash=content_hash,
            defaults={
                'openid': openid,
                'attachment_name': name,
                'content_type': _text(item.get('content_type') or item.get('mime_type'), 255),
                'storage_uri': _text(item.get('storage_uri') or item.get('storage_key'), 1000),
                'storage_size': max(int(item.get('size') or item.get('storage_size') or 0), 0),
                'security_status': _text(item.get('security_status') or SourceAttachment.PENDING, 16).upper(),
                'source_location': _text(item.get('source_location'), 255),
                'metadata': {
                    'hash_verified': bool(item.get('sha256') or item.get('content_hash') or item.get('hash')),
                },
            },
        )


def _event(record, status, event_type, message='', actor_type='', actor_name='', metadata=None):
    return SourceIntakeEvent.objects.create(
        intake=record,
        openid=record.openid,
        status=status,
        event_type=_text(event_type, 64),
        message=_text(message, 4000),
        actor_type=_text(actor_type, 64),
        actor_name=_text(actor_name, 255),
        metadata=metadata if isinstance(metadata, dict) else {},
    )


def ensure_source_intake_record(source, sync_run=None, duplicate=False):
    """Create the board record when a source is captured, without business writes."""
    metadata = source.metadata if isinstance(source.metadata, dict) else {}
    defaults = {
        'sync_run': sync_run,
        'openid': source.openid,
        'mailbox_account': source.mailbox_account,
        'operation': _operation(metadata, source),
        'document_type': _document_type(metadata),
        'status': SourceIntakeRecord.DUPLICATE if duplicate else SourceIntakeRecord.CAPTURED,
        'sender_name': _text(_metadata_value(metadata, 'sender_name', 'from_name'), 255),
        'sender_email': _text(_metadata_value(metadata, 'sender_email', 'from_email', 'sender'), 255),
        'subject': _text(_metadata_value(metadata, 'subject'), 1000),
        'external_reference': _text(_metadata_value(metadata, 'external_reference', 'reference', 'container_tracking'), 255),
        'owner_role': _text(_metadata_value(metadata, 'owner_role'), 64),
        'next_action': _text(_metadata_value(metadata, 'next_action'), 1000),
        'exception_summary': _text(_metadata_value(metadata, 'exception_summary', 'conflict_summary'), 4000),
        'classification_confidence': _confidence(metadata.get('classification_confidence')),
        'metadata': {
            key: value for key, value in metadata.items()
            if key not in {'body', 'raw_body', 'password', 'token', 'authorization'}
        },
        'sent_at': source.sent_at or _parse_datetime(_metadata_value(metadata, 'sent_at', 'email_sent_at')),
        'received_at': _parse_datetime(_metadata_value(metadata, 'received_at', 'email_received_at')),
    }
    record, created = SourceIntakeRecord.objects.get_or_create(source=source, defaults=defaults)
    if not created and (sync_run_id := getattr(sync_run, 'id', None)):
        if record.sync_run_id is None:
            SourceIntakeRecord.objects.filter(id=record.id).update(sync_run_id=sync_run_id)
    if created:
        _event(
            record,
            record.status,
            'CAPTURED' if not duplicate else 'DUPLICATE',
            'Source evidence captured by Codex intake.' if not duplicate else 'Source was already captured; duplicate processing skipped.',
            actor_type='CODEX_AUTOMATION',
        )
    elif duplicate and record.status == SourceIntakeRecord.CAPTURED:
        update_source_intake(
            record,
            {'status': SourceIntakeRecord.DUPLICATE},
            actor_type='CODEX_AUTOMATION',
            event_type='DUPLICATE',
        )
    _create_attachments(source, source.openid, metadata)
    return record, created


def update_source_intake(record, data, actor_type='', actor_name='', allow_terminal=False, event_type='STATUS_CHANGED'):
    if not isinstance(data, dict):
        raise ValidationError({'detail': 'Intake update must be a JSON object'})
    allowed = {
        'operation', 'document_type', 'status', 'sender_name', 'sender_email', 'subject',
        'external_reference', 'matched_entity_type', 'matched_entity_ref', 'owner_role',
        'next_action', 'exception_summary', 'last_error', 'classification_confidence',
        'received_at', 'reviewed_at', 'completed_at', 'metadata',
    }
    values = {key: value for key, value in data.items() if key in allowed}
    if not values:
        raise ValidationError({'detail': 'No supported intake fields were provided'})
    new_status = values.get('status')
    if new_status:
        new_status = _text(new_status, 32).upper()
        if new_status not in dict(SourceIntakeRecord.STATUS_CHOICES):
            raise ValidationError({'status': 'Unsupported intake status'})
        if not allow_terminal and new_status != record.status:
            allowed_next = STATUS_TRANSITIONS.get(record.status, set())
            if new_status not in allowed_next:
                raise ValidationError({
                    'status': 'Invalid intake status transition',
                    'from_status': record.status,
                    'to_status': new_status,
                })
        values['status'] = new_status
    for field in ('operation', 'document_type', 'status', 'owner_role'):
        if field in values and isinstance(values[field], str):
            values[field] = values[field].strip().upper()
    if 'operation' in values and values['operation'] not in dict(SourceIntakeRecord.OPERATION_CHOICES):
        raise ValidationError({'operation': 'Unsupported intake operation'})
    if 'document_type' in values and values['document_type'] not in dict(SourceIntakeRecord.DOCUMENT_CHOICES):
        raise ValidationError({'document_type': 'Unsupported source document type'})
    if 'classification_confidence' in values:
        values['classification_confidence'] = _confidence(values['classification_confidence'])
    for field in ('sender_name', 'sender_email', 'subject', 'external_reference', 'matched_entity_type', 'matched_entity_ref', 'owner_role', 'next_action'):
        if field in values:
            values[field] = _text(values[field], 1000)
    for field in ('exception_summary', 'last_error'):
        if field in values:
            values[field] = _text(values[field], 4000)
    if 'metadata' in values and not isinstance(values['metadata'], dict):
        raise ValidationError({'metadata': 'metadata must be a JSON object'})
    if 'received_at' in values:
        values['received_at'] = _parse_datetime(values['received_at'])
    for field in ('reviewed_at', 'completed_at'):
        if field in values:
            values[field] = _parse_datetime(values[field]) or timezone.now()
    previous_status = record.status
    changed_fields = [key for key, value in values.items() if value != getattr(record, key, None)]
    for key, value in values.items():
        setattr(record, key, value)
    record.save(update_fields=list(values.keys()) + ['updated_at'])
    if changed_fields:
        _event(
            record,
            record.status,
            event_type,
            values.get('next_action') or values.get('exception_summary') or '',
            actor_type=actor_type,
            actor_name=actor_name,
            metadata={'changed_fields': changed_fields, 'previous_status': previous_status},
        )
    return record
