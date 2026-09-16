"""Role-aware Mail2Task workflow for the legacy GreaterWMS line.

The mailbox Skill creates evidence; this module owns the human work item and
the controlled handoff between Sunny, Maggie and Mark. It deliberately does
not write ASN, Outbound, Receiving or Inventory rows. The final WMS action is
still performed through the existing WMS/operator flows after the task handoff
is recorded.
"""

import hashlib
import re

from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from staff.models import ListModel as Staff

from .models import (
    MailTask,
    MailTaskApproval,
    MailTaskEvent,
    SourceEvidence,
    SourceIntakeEvent,
    SourceIntakeRecord,
)
from .mailtime import latest_mail_datetime


TASK_ROLE_LABELS = {
    MailTask.SUPERVISOR: 'Sunny / Supervisor',
    MailTask.WMS_OPERATOR: 'Maggie / WMS operator',
    MailTask.SITE_OPERATOR: 'Mark / Site operator',
}

TASK_ROLE_STAFF_TYPES = {
    MailTask.SUPERVISOR: frozenset({'admin', 'manager', 'supervisor'}),
    MailTask.WMS_OPERATOR: frozenset({'warehouse', 'inbound', 'outbound', 'stockcontrol', 'logistics'}),
    MailTask.SITE_OPERATOR: frozenset({'warehouse', 'driver'}),
}

# The legacy Staff table only has broad WMS staff types. During the current
# Sunny/Maggie/Mark rollout, their named staff accounts are the operational
# role registry; generic warehouse accounts retain the broad compatibility
# matrix until CIO configures a more specific assignment.
NAMED_TASK_ROLE_HINTS = {
    'sunny': MailTask.SUPERVISOR,
    'maggie': MailTask.WMS_OPERATOR,
    'mark': MailTask.SITE_OPERATOR,
}

TASK_STATUS_LABELS = {
    MailTask.OPEN: 'Open · Maggie',
    MailTask.AWAITING_SUNNY_APPROVAL: 'Awaiting Sunny approval',
    MailTask.READY_FOR_MARK: 'Ready · Mark',
    MailTask.SITE_IN_PROGRESS: 'Site work · Mark',
    MailTask.WMS_FINALIZATION: 'WMS update · Maggie',
    MailTask.COMPLETED: 'Completed',
    MailTask.BLOCKED: 'Blocked · Sunny review',
}

HANDOFF_STATUS_LABELS = {
    MailTask.TO_MAGGIE: 'To Maggie',
    MailTask.TO_SUNNY: 'To Sunny',
    MailTask.TO_MARK: 'To Mark',
    MailTask.SITE_IN_PROGRESS_HANDOFF: 'Mark is working',
    MailTask.RETURNED_TO_MAGGIE: 'Returned to Maggie',
    MailTask.HANDOFF_COMPLETED: 'Completed',
    MailTask.HANDOFF_BLOCKED: 'Blocked',
}

MAIL_FLOW_LABELS = {
    'CLIENT_TO_LOGISTICS': 'Client → Peak Logistics',
    'EXTERNAL_TO_LOGISTICS': 'External service → Peak Logistics',
    'LOGISTICS_TO_WAREHOUSE': 'Peak Logistics → Warehouse',
    'WAREHOUSE_TO_LOGISTICS': 'Warehouse → Peak Logistics',
    'LOGISTICS_TO_EXTERNAL': 'Peak Logistics → External service',
    'WAREHOUSE_TO_EXTERNAL': 'Warehouse → External service',
    'INTERNAL': 'Internal coordination',
    'REVIEW': 'Review direction',
}

MAIL_FLOW_ALIASES = {
    'CLIENT_TO_LOGISTICS': 'CLIENT_TO_LOGISTICS',
    'CLIENT->LOGISTICS': 'CLIENT_TO_LOGISTICS',
    'CLIENT_TO_LOG': 'CLIENT_TO_LOGISTICS',
    'CLIENT->LOG': 'CLIENT_TO_LOGISTICS',
    'EXTERNAL_TO_LOGISTICS': 'EXTERNAL_TO_LOGISTICS',
    'EXTERNAL_SERVICE_TO_LOGISTICS': 'EXTERNAL_TO_LOGISTICS',
    'EXTERNAL->LOGISTICS': 'EXTERNAL_TO_LOGISTICS',
    'EXTERNAL->LOG': 'EXTERNAL_TO_LOGISTICS',
    'LOGISTICS_TO_WAREHOUSE': 'LOGISTICS_TO_WAREHOUSE',
    'LOGISTICS_TO_WH': 'LOGISTICS_TO_WAREHOUSE',
    'LOGISTICS->WAREHOUSE': 'LOGISTICS_TO_WAREHOUSE',
    'LOGISTICS->WH': 'LOGISTICS_TO_WAREHOUSE',
    'WAREHOUSE_TO_LOGISTICS': 'WAREHOUSE_TO_LOGISTICS',
    'WAREHOUSE_TO_LOG': 'WAREHOUSE_TO_LOGISTICS',
    'WAREHOUSE->LOGISTICS': 'WAREHOUSE_TO_LOGISTICS',
    'WAREHOUSE->LOG': 'WAREHOUSE_TO_LOGISTICS',
    'LOGISTICS_TO_EXTERNAL': 'LOGISTICS_TO_EXTERNAL',
    'LOGISTICS_TO_EXT': 'LOGISTICS_TO_EXTERNAL',
    'LOGISTICS->EXTERNAL': 'LOGISTICS_TO_EXTERNAL',
    'LOGISTICS->EXT': 'LOGISTICS_TO_EXTERNAL',
    'WAREHOUSE_TO_EXTERNAL': 'WAREHOUSE_TO_EXTERNAL',
    'WAREHOUSE_TO_EXT': 'WAREHOUSE_TO_EXTERNAL',
    'WAREHOUSE->EXTERNAL': 'WAREHOUSE_TO_EXTERNAL',
    'WAREHOUSE->EXT': 'WAREHOUSE_TO_EXTERNAL',
    'INTERNAL': 'INTERNAL',
    'INTERNAL_COORDINATION': 'INTERNAL',
    'REVIEW': 'REVIEW',
    'REVIEW_DIRECTION': 'REVIEW',
}

PARTY_ROLE_ALIASES = {
    'CLIENT': 'CLIENT',
    'CUSTOMER': 'CLIENT',
    'DELTA': 'CLIENT',
    'EXTERNAL': 'EXTERNAL',
    'EXT': 'EXTERNAL',
    'EXTERNAL_SERVICE': 'EXTERNAL',
    'SERVICE_PROVIDER': 'EXTERNAL',
    'FORWARDER': 'EXTERNAL',
    'CARRIER': 'EXTERNAL',
    'BROKER': 'EXTERNAL',
    'LOGISTICS': 'LOGISTICS',
    'PEAK_LOGISTICS': 'LOGISTICS',
    'PEAK_LOG': 'LOGISTICS',
    'WAREHOUSE': 'WAREHOUSE',
    'WH': 'WAREHOUSE',
    'WAREHOUSE_DEPARTMENT': 'WAREHOUSE',
    'INTERNAL': 'INTERNAL',
}

ACTION_LABELS = {
    'PREPARE_WMS': 'Maggie: prepare WMS',
    'APPROVE_OUTBOUND': 'Sunny: approve outbound',
    'REJECT_OUTBOUND': 'Sunny: reject outbound',
    'START_SITE': 'Mark: start site work',
    'COMPLETE_SITE': 'Mark: complete site work',
    'COMPLETE_WMS': 'Maggie: complete WMS',
    'BLOCK': 'Block / request clarification',
    'REOPEN': 'Reopen for review',
}

# MailTask next actions are a controlled display taxonomy. The database keeps
# the full human instruction in ``next_action`` for evidence and audit, while
# the API also exposes a stable code/label pair for list views and reports.
TASK_NEXT_ACTIONS = {
    'PREPARE_WMS': {'label': 'Prepare WMS', 'owner_role': MailTask.WMS_OPERATOR},
    'APPROVE_OUTBOUND': {'label': 'Approve outbound', 'owner_role': MailTask.SUPERVISOR},
    'START_SITE': {'label': 'Start site work', 'owner_role': MailTask.SITE_OPERATOR},
    'COMPLETE_SITE': {'label': 'Complete site work', 'owner_role': MailTask.SITE_OPERATOR},
    'COMPLETE_WMS': {'label': 'Update WMS', 'owner_role': MailTask.WMS_OPERATOR},
    'RESOLVE_EXCEPTION': {'label': 'Resolve exception', 'owner_role': MailTask.SUPERVISOR},
    'COMPLETE': {'label': 'Complete', 'owner_role': ''},
    'REVIEW': {'label': 'Review', 'owner_role': MailTask.SUPERVISOR},
}

TASK_STATUS_NEXT_ACTIONS = {
    MailTask.OPEN: 'PREPARE_WMS',
    MailTask.AWAITING_SUNNY_APPROVAL: 'APPROVE_OUTBOUND',
    MailTask.READY_FOR_MARK: 'START_SITE',
    MailTask.SITE_IN_PROGRESS: 'COMPLETE_SITE',
    MailTask.WMS_FINALIZATION: 'COMPLETE_WMS',
    MailTask.COMPLETED: 'COMPLETE',
    MailTask.BLOCKED: 'RESOLVE_EXCEPTION',
}

ACTION_STATES = {
    MailTask.OPEN: ('PREPARE_WMS', 'BLOCK'),
    MailTask.AWAITING_SUNNY_APPROVAL: ('APPROVE_OUTBOUND', 'REJECT_OUTBOUND', 'BLOCK'),
    MailTask.READY_FOR_MARK: ('START_SITE', 'BLOCK'),
    MailTask.SITE_IN_PROGRESS: ('COMPLETE_SITE', 'BLOCK'),
    MailTask.WMS_FINALIZATION: ('COMPLETE_WMS', 'BLOCK'),
    MailTask.COMPLETED: (),
    MailTask.BLOCKED: ('REOPEN',),
}


def _text(value, limit=1000):
    return str(value or '').strip()[:limit]


def normalize_mail_flow(value):
    """Normalize a flow value without hard-coding external company names."""
    raw = _text(value, 64).upper().replace('→', '->').replace('—', '-').replace('–', '-')
    raw = re.sub(r'\s*->\s*', '->', raw)
    raw = re.sub(r'\s+', '_', raw).replace(' ', '_')
    return MAIL_FLOW_ALIASES.get(raw, 'REVIEW')


def mail_flow_label(value):
    return MAIL_FLOW_LABELS.get(str(value or '').upper(), MAIL_FLOW_LABELS['REVIEW'])


def _party_role(value):
    raw = _text(value, 64).upper().replace('→', '->')
    raw = re.sub(r'[^A-Z_]+', '_', raw).strip('_')
    return PARTY_ROLE_ALIASES.get(raw, '')


def mail_flow_from_metadata(metadata):
    """Read an explicit flow or compose one from explicit party roles.

    The Skill should provide ``mail_flow`` or ``sender_role`` and
    ``recipient_role`` when the headers establish the organizational
    direction. Names and company strings are never guessed here.
    """
    if not isinstance(metadata, dict):
        return 'REVIEW'
    for key in ('mail_flow', 'message_flow', 'email_flow', 'flow'):
        value = metadata.get(key)
        if value not in (None, ''):
            normalized = normalize_mail_flow(value)
            if normalized != 'REVIEW':
                return normalized
    sender_role = _party_role(
        metadata.get('sender_role')
        or metadata.get('from_role')
        or metadata.get('source_party_role')
    )
    recipient_role = _party_role(
        metadata.get('recipient_role')
        or metadata.get('to_role')
        or metadata.get('target_party_role')
    )
    pairs = {
        ('CLIENT', 'LOGISTICS'): 'CLIENT_TO_LOGISTICS',
        ('EXTERNAL', 'LOGISTICS'): 'EXTERNAL_TO_LOGISTICS',
        ('LOGISTICS', 'WAREHOUSE'): 'LOGISTICS_TO_WAREHOUSE',
        ('WAREHOUSE', 'LOGISTICS'): 'WAREHOUSE_TO_LOGISTICS',
        ('LOGISTICS', 'EXTERNAL'): 'LOGISTICS_TO_EXTERNAL',
        ('WAREHOUSE', 'EXTERNAL'): 'WAREHOUSE_TO_EXTERNAL',
    }
    if sender_role == recipient_role == 'INTERNAL':
        return 'INTERNAL'
    return pairs.get((sender_role, recipient_role), 'REVIEW')


def _normalized_operation(value):
    value = _text(value, 32).upper()
    if value in dict(MailTask.OPERATION_CHOICES):
        return value
    return MailTask.UNKNOWN


def task_role_label(value):
    return TASK_ROLE_LABELS.get(str(value or '').upper(), str(value or '') or 'Unassigned')


def task_status_label(value):
    return TASK_STATUS_LABELS.get(str(value or '').upper(), str(value or '') or 'Unknown')


def handoff_status_label(value):
    return HANDOFF_STATUS_LABELS.get(str(value or '').upper(), str(value or '') or 'Not started')


def task_next_action_display(status='', next_action='', assigned_role=''):
    """Return a stable MailTask next-action code and label.

    Task status is authoritative because free-text instructions can vary by
    mailbox message. The text remains available as ``detail`` for the UI and
    audit trail; it is never used as the primary list label when status is
    known.
    """
    status_code = str(status or '').strip().upper()
    role_code = str(assigned_role or '').strip().upper()
    code = 'REVIEW' if status_code == MailTask.OPEN and role_code == MailTask.SUPERVISOR else TASK_STATUS_NEXT_ACTIONS.get(status_code, '')
    instruction = _text(next_action, 1000)
    normalized = instruction.casefold()
    if not code:
        if 'approve' in normalized and 'outbound' in normalized:
            code = 'APPROVE_OUTBOUND'
        elif 'no further action' in normalized or normalized in {'complete', 'completed'}:
            code = 'COMPLETE'
        elif any(token in normalized for token in ('resolve exception', 'clarify', 'request clarification', 'reopen')):
            code = 'RESOLVE_EXCEPTION'
        elif 'complete' in normalized and ('site' in normalized or 'physical' in normalized):
            code = 'COMPLETE_SITE'
        elif 'prepare' in normalized and 'wms' in normalized:
            code = 'PREPARE_WMS'
        elif 'wms' in normalized and any(token in normalized for token in ('record', 'update', 'close', 'complete')):
            code = 'COMPLETE_WMS'
        elif any(token in normalized for token in ('physical receiving', 'site movement', 'site work', 'confirm physical receipt')):
            code = 'START_SITE'
        elif instruction:
            code = 'REVIEW'

    action = TASK_NEXT_ACTIONS.get(code, TASK_NEXT_ACTIONS['REVIEW'])
    return {
        'code': code or 'REVIEW',
        'label': action['label'],
        'owner_role': action['owner_role'],
        'detail': instruction,
    }


def _role_for_operation(operation):
    return MailTask.SUPERVISOR if operation in {MailTask.SUPPORTING, MailTask.UNKNOWN} else MailTask.WMS_OPERATOR


def _prefix_for_operation(operation):
    return {
        MailTask.INBOUND: 'IB',
        MailTask.OUTBOUND: 'OB',
        MailTask.SUPPORTING: 'SUP',
        MailTask.UNKNOWN: 'MAIL',
    }.get(operation, 'MAIL')


def _safe_ref(value):
    normalized = re.sub(r'[^A-Za-z0-9]+', '-', _text(value, 180)).strip('-').upper()
    return normalized[:120]


def task_ref_for_source(source, operation, external_reference=''):
    """Return a stable, human-readable task key for related email updates."""
    operation = _normalized_operation(operation)
    reference = _safe_ref(external_reference)
    if not reference:
        seed = '|'.join([
            source.openid,
            source.thread_id or '',
            source.message_id or '',
            source.content_hash or '',
        ])
        reference = 'MAIL-' + hashlib.sha256(seed.encode('utf-8')).hexdigest()[:12].upper()
    return '%s-%s' % (_prefix_for_operation(operation), reference)


def _actor_staff(request, openid=None):
    identity = getattr(request, 'auth', None)
    openid = openid or getattr(identity, 'openid', None)
    operator_id = request.META.get('HTTP_OPERATOR') or getattr(identity, 'staff_id', None)
    staff = Staff.objects.filter(openid=openid, id=operator_id, is_delete=False).first()
    if staff is None:
        raise PermissionDenied('A valid staff identity is required for Mail2Task actions')
    identity_staff_id = getattr(identity, 'staff_id', None)
    if not getattr(identity, 'is_admin', False) and identity_staff_id is not None:
        if str(operator_id) != str(identity_staff_id):
            raise PermissionDenied('Operator identity does not match the authenticated user')
    return staff


def _staff_type(staff):
    return str(getattr(staff, 'staff_type', '') or '').strip().casefold()


def _named_task_role(staff):
    name = _text(getattr(staff, 'staff_name', ''), 255).casefold()
    name = name.split('@', 1)[0].strip()
    return NAMED_TASK_ROLE_HINTS.get(name)


def _default_staff_for_role(openid, task_role):
    """Resolve the current named rollout account when it exists."""
    for staff in Staff.objects.filter(openid=openid, is_delete=False).order_by('id'):
        if _named_task_role(staff) == task_role:
            return staff
    return None


def staff_can_fill_task_role(staff, task_role):
    named_role = _named_task_role(staff)
    if named_role:
        return named_role == task_role
    return _staff_type(staff) in TASK_ROLE_STAFF_TYPES.get(task_role, frozenset())


def _is_management(staff):
    return staff_can_fill_task_role(staff, MailTask.SUPERVISOR)


def _assigned_actor_matches(task, staff):
    return not task.assigned_staff_id or int(task.assigned_staff_id) == int(staff.id)


def _actor_task_role(staff):
    for role in (MailTask.SUPERVISOR, MailTask.WMS_OPERATOR, MailTask.SITE_OPERATOR):
        if staff_can_fill_task_role(staff, role):
            return role
    return ''


def _can_take_action(task, action, staff):
    if action in {'APPROVE_OUTBOUND', 'REJECT_OUTBOUND', 'REOPEN'}:
        return _is_management(staff) and (
            action == 'REOPEN' or task.assigned_role == MailTask.SUPERVISOR
        ) and _assigned_actor_matches(task, staff)
    if action == 'BLOCK':
        return _is_management(staff) or (
            staff_can_fill_task_role(staff, task.assigned_role)
            and _assigned_actor_matches(task, staff)
        )
    if action == 'PREPARE_WMS' or action == 'COMPLETE_WMS':
        return (
            task.assigned_role == MailTask.WMS_OPERATOR
            and staff_can_fill_task_role(staff, MailTask.WMS_OPERATOR)
            and _assigned_actor_matches(task, staff)
        )
    if action in {'START_SITE', 'COMPLETE_SITE'}:
        return (
            task.assigned_role == MailTask.SITE_OPERATOR
            and staff_can_fill_task_role(staff, MailTask.SITE_OPERATOR)
            and _assigned_actor_matches(task, staff)
        )
    return False


def _claim_if_unassigned(task, staff):
    if task.assigned_staff_id is None:
        task.assigned_staff_id = staff.id
        task.assigned_staff_name = staff.staff_name


def _assign_default_role(task, task_role):
    target = _default_staff_for_role(task.openid, task_role)
    task.assigned_role = task_role
    task.assigned_staff_id = target.id if target else None
    task.assigned_staff_name = target.staff_name if target else ''


def _new_task_defaults(source, record):
    operation = _normalized_operation(record.operation)
    assigned_role = _role_for_operation(operation)
    defaults = {
        'openid': source.openid,
        'task_ref': task_ref_for_source(source, operation, record.external_reference),
        'operation': operation,
        'subject': _text(record.subject, 1000),
        'external_reference': _text(record.external_reference, 255),
        'status': MailTask.OPEN,
        'flow': record.flow or 'REVIEW',
        'assigned_role': assigned_role,
        'next_action': 'Maggie: review the email and prepare the WMS handoff.' if assigned_role == MailTask.WMS_OPERATOR else 'Sunny: review and assign the operational next step.',
        'wms_handoff_status': MailTask.TO_MAGGIE if assigned_role == MailTask.WMS_OPERATOR else MailTask.TO_SUNNY,
        'due_at': record.due_at,
        'due_type': record.due_type,
        'due_precision': record.due_precision,
        'event_at': record.event_at,
        'event_type': record.event_type,
        'event_precision': record.event_precision,
        'last_mail_at': latest_mail_datetime(record.sent_at, record.received_at),
    }
    target = _default_staff_for_role(source.openid, assigned_role)
    if target:
        defaults['assigned_staff_id'] = target.id
        defaults['assigned_staff_name'] = target.staff_name
    return defaults


def _sync_task_time_and_flow(task, record):
    """Project the newest source mail's direction and schedule onto the task."""
    incoming_last_mail = latest_mail_datetime(record.sent_at, record.received_at)
    current_last_mail = task.last_mail_at
    is_newer = current_last_mail is None or (
        incoming_last_mail is not None and incoming_last_mail >= current_last_mail
    )
    if not is_newer:
        return []

    updates = []
    if record.flow and record.flow != 'REVIEW' and task.flow != record.flow:
        task.flow = record.flow
        updates.append('flow')
    for field in ('due_at', 'due_type', 'due_precision', 'event_at', 'event_type', 'event_precision'):
        value = getattr(record, field, None)
        if value not in (None, '') and value != getattr(task, field):
            setattr(task, field, value)
            updates.append(field)
    if incoming_last_mail is not None and incoming_last_mail != current_last_mail:
        task.last_mail_at = incoming_last_mail
        updates.append('last_mail_at')
    return updates


def ensure_mail_task(source, record):
    """Attach an intake record to its durable task, merging follow-up emails."""
    defaults = _new_task_defaults(source, record)
    try:
        task, created = MailTask.objects.get_or_create(
            openid=source.openid,
            task_ref=defaults['task_ref'],
            defaults={key: value for key, value in defaults.items() if key not in {'openid', 'task_ref'}},
        )
    except IntegrityError:
        task = MailTask.objects.get(openid=source.openid, task_ref=defaults['task_ref'])
        created = False

    updates = []
    for field in ('subject', 'external_reference', 'assigned_staff_id', 'assigned_staff_name'):
        default_value = defaults.get(field)
        if getattr(task, field) in ('', None) and default_value:
            setattr(task, field, default_value)
            updates.append(field)
    if task.operation == MailTask.UNKNOWN and defaults['operation'] != MailTask.UNKNOWN:
        task.operation = defaults['operation']
        updates.append('operation')
    updates.extend(_sync_task_time_and_flow(task, record))
    if updates:
        task.save(update_fields=updates + ['updated_at'])

    if record.task_id != task.id:
        record.task = task
        record.save(update_fields=['task'])
    if created:
        MailTaskEvent.objects.create(
            task=task,
            source_evidence=source,
            openid=source.openid,
            action='CREATED',
            to_status=task.status,
            actor_role=task.assigned_role,
            note='Task created from email evidence.',
        )
    return task


def _sync_linked_intake_records(task, action, actor):
    """Keep the email projection readable without making it the task source."""
    status_map = {
        MailTask.AWAITING_SUNNY_APPROVAL: SourceIntakeRecord.APPROVAL_REQUIRED,
        MailTask.READY_FOR_MARK: SourceIntakeRecord.READY_FOR_PREVIEW,
        MailTask.SITE_IN_PROGRESS: SourceIntakeRecord.EXECUTING,
        MailTask.WMS_FINALIZATION: SourceIntakeRecord.EXECUTING,
        MailTask.COMPLETED: SourceIntakeRecord.COMPLETED,
        MailTask.BLOCKED: SourceIntakeRecord.BLOCKED,
    }
    next_status = status_map.get(task.status)
    for record in task.intake_records.all():
        changed = []
        if record.owner_role != task.assigned_role:
            record.owner_role = task.assigned_role
            changed.append('owner_role')
        if record.next_action != task.next_action:
            record.next_action = task.next_action
            changed.append('next_action')
        if next_status and record.status != next_status:
            record.status = next_status
            changed.append('status')
        if task.status == MailTask.COMPLETED and record.completed_at is None:
            record.completed_at = task.completed_at or timezone.now()
            changed.append('completed_at')
        if changed:
            record.save(update_fields=changed + ['updated_at'])
            SourceIntakeEvent.objects.create(
                intake=record,
                openid=record.openid,
                status=record.status,
                event_type='MAILTASK_%s' % action,
                message=task.next_action,
                actor_type='MAILTASK',
                actor_name=getattr(actor, 'staff_name', ''),
                metadata={'task_ref': task.task_ref, 'changed_fields': changed},
            )


def _task_event(task, source, action, previous_status, actor, note=''):
    return MailTaskEvent.objects.create(
        task=task,
        source_evidence=source,
        openid=task.openid,
        action=action,
        from_status=previous_status,
        to_status=task.status,
        actor_role=_actor_task_role(actor),
        actor_id=actor.id if actor else None,
        actor_name=actor.staff_name if actor else '',
        note=_text(note or task.next_action, 4000),
    )


def available_task_actions(task, request=None):
    candidates = ACTION_STATES.get(task.status, ())
    if request is None:
        return [
            {'code': code, 'label': ACTION_LABELS[code]}
            for code in candidates
        ]
    try:
        actor = _actor_staff(request, task.openid)
    except PermissionDenied:
        return []
    return [
        {'code': code, 'label': ACTION_LABELS[code]}
        for code in candidates
        if _can_take_action(task, code, actor)
    ]


def apply_mail_task_action(task_id, request, data):
    """Apply one explicit handoff action with role and state enforcement."""
    action = _text(data.get('action'), 64).upper()
    if action not in ACTION_LABELS:
        raise ValidationError({'action': 'Unsupported Mail2Task action'})

    with transaction.atomic():
        task = MailTask.objects.select_for_update().filter(
            id=task_id,
            openid=request.auth.openid,
        ).first()
        if task is None:
            raise ValidationError({'detail': 'Mail task not found'})
        actor = _actor_staff(request, task.openid)
        if action not in ACTION_STATES.get(task.status, ()):
            raise ValidationError({
                'action': 'Action is not available for the current task status',
                'status': task.status,
            })
        if not _can_take_action(task, action, actor):
            raise PermissionDenied('Your role cannot perform this Mail2Task action')

        previous_status = task.status
        note = _text(data.get('note'), 4000)
        wms_ref = _text(data.get('wms_entity_ref'), 255)
        wms_type = _text(data.get('wms_entity_type'), 64)
        wms_system = _text(data.get('wms_entity_system'), 32).upper()
        if wms_system and wms_system not in dict(MailTask.WMS_SYSTEM_CHOICES):
            raise ValidationError({'wms_entity_system': 'Use LEGACY_PROD or MIGRATED'})
        if wms_ref:
            task.wms_entity_ref = wms_ref
        if wms_type:
            task.wms_entity_type = wms_type
        if wms_system:
            task.wms_entity_system = wms_system
        _claim_if_unassigned(task, actor)

        if action == 'PREPARE_WMS':
            if task.operation == MailTask.OUTBOUND:
                task.status = MailTask.AWAITING_SUNNY_APPROVAL
                _assign_default_role(task, MailTask.SUPERVISOR)
                task.wms_handoff_status = MailTask.TO_SUNNY
                task.next_action = 'Sunny: give final approval before Mark performs outbound site work.'
                MailTaskApproval.objects.get_or_create(
                    task=task,
                    status=MailTaskApproval.PENDING,
                    defaults={
                        'openid': task.openid,
                        'approval_type': MailTaskApproval.OUTBOUND_FINAL,
                        'requested_by_id': actor.id,
                        'requested_by_name': actor.staff_name,
                    },
                )
            else:
                task.status = MailTask.READY_FOR_MARK
                _assign_default_role(task, MailTask.SITE_OPERATOR)
                task.wms_handoff_status = MailTask.TO_MARK
                task.next_action = 'Mark: confirm the physical receiving or site movement.'
        elif action == 'APPROVE_OUTBOUND':
            approval = MailTaskApproval.objects.filter(
                task=task,
                status=MailTaskApproval.PENDING,
            ).first()
            if approval is None:
                raise ValidationError({'action': 'No pending outbound approval exists'})
            approval.status = MailTaskApproval.APPROVED
            approval.decided_by_id = actor.id
            approval.decided_by_name = actor.staff_name
            approval.note = note
            approval.decided_at = timezone.now()
            approval.save(update_fields=['status', 'decided_by_id', 'decided_by_name', 'note', 'decided_at'])
            task.status = MailTask.READY_FOR_MARK
            _assign_default_role(task, MailTask.SITE_OPERATOR)
            task.wms_handoff_status = MailTask.TO_MARK
            task.next_action = 'Mark: perform the approved outbound site work and report the result.'
        elif action == 'REJECT_OUTBOUND':
            approval = MailTaskApproval.objects.filter(task=task, status=MailTaskApproval.PENDING).first()
            if approval is not None:
                approval.status = MailTaskApproval.REJECTED
                approval.decided_by_id = actor.id
                approval.decided_by_name = actor.staff_name
                approval.note = note
                approval.decided_at = timezone.now()
                approval.save(update_fields=['status', 'decided_by_id', 'decided_by_name', 'note', 'decided_at'])
            task.status = MailTask.BLOCKED
            task.assigned_role = MailTask.SUPERVISOR
            task.assigned_staff_id = actor.id
            task.assigned_staff_name = actor.staff_name
            task.wms_handoff_status = MailTask.HANDOFF_BLOCKED
            task.next_action = 'Sunny: clarify the outbound instruction before resubmitting.'
        elif action == 'START_SITE':
            task.status = MailTask.SITE_IN_PROGRESS
            task.assigned_role = MailTask.SITE_OPERATOR
            task.wms_handoff_status = MailTask.SITE_IN_PROGRESS_HANDOFF
            task.next_action = 'Mark: complete the physical site work and report quantities or exceptions.'
        elif action == 'COMPLETE_SITE':
            task.status = MailTask.WMS_FINALIZATION
            _assign_default_role(task, MailTask.WMS_OPERATOR)
            task.wms_handoff_status = MailTask.RETURNED_TO_MAGGIE
            task.next_action = 'Maggie: record the confirmed site result in WMS and close the task.'
        elif action == 'COMPLETE_WMS':
            if not (wms_ref or task.wms_entity_ref):
                raise ValidationError({'wms_entity_ref': 'WMS reference is required before completion'})
            task.status = MailTask.COMPLETED
            task.wms_handoff_status = MailTask.HANDOFF_COMPLETED
            task.next_action = 'No further action.'
            task.completed_at = timezone.now()
        elif action == 'BLOCK':
            task.status = MailTask.BLOCKED
            task.assigned_role = MailTask.SUPERVISOR
            task.assigned_staff_id = actor.id if _is_management(actor) else task.assigned_staff_id
            task.assigned_staff_name = actor.staff_name if _is_management(actor) else task.assigned_staff_name
            task.wms_handoff_status = MailTask.HANDOFF_BLOCKED
            task.next_action = 'Sunny: review the exception or request clarification from the sender.'
        elif action == 'REOPEN':
            task.status = MailTask.OPEN
            _assign_default_role(task, MailTask.WMS_OPERATOR)
            task.wms_handoff_status = MailTask.TO_MAGGIE
            task.next_action = 'Maggie: review the updated email evidence and prepare the WMS handoff.'

        if note:
            task.wms_handoff_note = note
        task.save()
        source = task.intake_records.select_related('source').first()
        _task_event(task, source.source if source else None, action, previous_status, actor, note=note)
        _sync_linked_intake_records(task, action, actor)
        return task


def assign_mail_task(task_id, request, data):
    """Let Sunny assign the named Maggie/Mark/Sunny staff member."""
    with transaction.atomic():
        task = MailTask.objects.select_for_update().filter(
            id=task_id,
            openid=request.auth.openid,
        ).first()
        if task is None:
            raise ValidationError({'detail': 'Mail task not found'})
        actor = _actor_staff(request, task.openid)
        if not _is_management(actor):
            raise PermissionDenied('Only Sunny or another supervisor can assign Mail2Task work')
        role = _text(data.get('assigned_role') or data.get('role'), 32).upper()
        if role not in dict(MailTask.TASK_ROLE_CHOICES):
            raise ValidationError({'assigned_role': 'Use SUPERVISOR, WMS_OPERATOR or SITE_OPERATOR'})
        staff_id = data.get('staff_id')
        target = None
        if staff_id not in (None, ''):
            try:
                target = Staff.objects.filter(openid=task.openid, id=int(staff_id), is_delete=False).first()
            except (TypeError, ValueError):
                target = None
            if target is None:
                raise ValidationError({'staff_id': 'Target staff does not exist for this tenant'})
            if not staff_can_fill_task_role(target, role):
                raise ValidationError({'staff_id': 'Target staff type cannot fill this task role'})
        previous_role = task.assigned_role
        task.assigned_role = role
        task.assigned_staff_id = target.id if target else None
        task.assigned_staff_name = target.staff_name if target else ''
        if role == MailTask.SUPERVISOR:
            task.wms_handoff_status = MailTask.TO_SUNNY
        elif role == MailTask.SITE_OPERATOR:
            task.wms_handoff_status = MailTask.TO_MARK
        else:
            task.wms_handoff_status = MailTask.TO_MAGGIE
        task.save(update_fields=['assigned_role', 'assigned_staff_id', 'assigned_staff_name', 'wms_handoff_status', 'updated_at'])
        source = task.intake_records.select_related('source').first()
        _task_event(
            task,
            source.source if source else None,
            'ASSIGNED',
            task.status,
            actor,
            note='Assignment changed from %s to %s.' % (previous_role, task_role_label(role)),
        )
        _sync_linked_intake_records(task, 'ASSIGNED', actor)
        return task


def task_actors(openid):
    staff = Staff.objects.filter(openid=openid, is_delete=False).order_by('staff_name')
    return [
        {
            'id': item.id,
            'name': item.staff_name,
            'staff_type': item.staff_type,
            'task_roles': [role for role in dict(MailTask.TASK_ROLE_CHOICES) if staff_can_fill_task_role(item, role)],
        }
        for item in staff
        if any(staff_can_fill_task_role(item, role) for role in dict(MailTask.TASK_ROLE_CHOICES))
    ]


def task_payload(task, request=None, detail=False):
    linked_records = list(task.intake_records.select_related('source').order_by('-updated_at', '-id'))
    next_action = task_next_action_display(task.status, task.next_action, task.assigned_role)
    payload = {
        'id': task.id,
        'task_ref': task.task_ref,
        'task_status': task.status,
        'task_status_label': task_status_label(task.status),
        'operation': task.operation,
        'flow': task.flow,
        'flow_label': mail_flow_label(task.flow),
        'subject': task.subject,
        'external_reference': task.external_reference,
        'assigned_role': task.assigned_role,
        'assigned_role_label': task_role_label(task.assigned_role),
        'assigned_staff_id': task.assigned_staff_id,
        'assigned_staff_name': task.assigned_staff_name,
        'wms_handoff_status': task.wms_handoff_status,
        'wms_handoff_label': handoff_status_label(task.wms_handoff_status),
        'wms_entity_system': task.wms_entity_system,
        'wms_entity_type': task.wms_entity_type,
        'wms_entity_ref': task.wms_entity_ref,
        'wms_handoff_note': task.wms_handoff_note,
        'task_next_action': task.next_action,
        'task_next_action_code': next_action['code'],
        'task_next_action_label': next_action['label'],
        'due_at': task.due_at,
        'due_type': task.due_type,
        'due_precision': task.due_precision,
        'event_at': task.event_at,
        'event_type': task.event_type,
        'event_precision': task.event_precision,
        'last_mail_at': task.last_mail_at,
        'task_email_count': len(linked_records),
        'task_actions': available_task_actions(task, request=request),
        'created_at': task.created_at,
        'updated_at': task.updated_at,
        'completed_at': task.completed_at,
    }
    if detail:
        payload.update({
            'approvals': [
                {
                    'id': item.id,
                    'approval_type': item.approval_type,
                    'status': item.status,
                    'requested_by_name': item.requested_by_name,
                    'decided_by_name': item.decided_by_name,
                    'note': item.note,
                    'requested_at': item.requested_at,
                    'decided_at': item.decided_at,
                }
                for item in task.approvals.all()[:20]
            ],
            'task_events': [
                {
                    'id': item.id,
                    'action': item.action,
                    'from_status': item.from_status,
                    'to_status': item.to_status,
                    'actor_role': item.actor_role,
                    'actor_name': item.actor_name,
                    'note': item.note,
                    'created_at': item.created_at,
                }
                for item in task.task_events.all()[:100]
            ],
            'email_records': [
                {
                    'id': item.id,
                    'source_evidence_id': item.source_id,
                    'subject': item.subject,
                    'sender_email': item.sender_email,
                    'flow': item.flow,
                    'flow_label': mail_flow_label(item.flow),
                    'sent_at': item.sent_at,
                    'status': item.status,
                    'received_at': item.received_at,
                    'due_at': item.due_at,
                    'event_at': item.event_at,
                }
                for item in linked_records
            ],
        })
    return payload
