"""Canonical Mail2Task statistics shared by the page and Agent reports.

The mailbox scan and the operational board intentionally have different
grains: one email can update an existing MailTask.  This module keeps both
grains in one response so a management report can reconcile them without
mistaking email count for task count.
"""

from collections import Counter
from datetime import date, datetime

from django.utils import timezone

from .mailtime import MAILBOX_TIME_ZONE
from .models import MailTask, MailboxSyncRun, SourceAttachment, SourceIntakeRecord


# These are mailbox identities, not hard-coded totals.  Counts are derived
# from the selected mail-date range on every request so the management view
# remains useful as new messages arrive.  Additional aliases can be added
# here when the operating team changes an address or display name.
EXECUTIVE_PEOPLE = (
    {
        'key': 'kelly',
        'name': 'Kelly',
        'sender_names': ('Kelly Wang',),
        'sender_emails': ('op1@peaksmartlogistics.com',),
        'metric': 'emails',
        'responsibility': 'Ocean freight, documentation, and external coordination',
    },
    {
        'key': 'teddy',
        'name': 'Teddy',
        'sender_names': ('Teddy Li',),
        'sender_emails': ('op8@peaksmartlogistics.com',),
        'metric': 'emails',
        'responsibility': 'Air freight and domestic transportation',
    },
    {
        'key': 'peter',
        'name': 'Peter',
        'sender_names': ('Peter Liu',),
        'sender_emails': ('peter@peaksmartlogistics.com',),
        'metric': 'emails',
        'responsibility': 'Internal forwarding and information distribution',
    },
    {
        'key': 'sunny',
        'name': 'Sunny',
        'sender_names': ('Sunny Lee',),
        'sender_emails': ('op2@peaksmartlogistics.com',),
        'metric': 'emails',
        'responsibility': 'Warehouse supervisor coordination and final outbound approval',
    },
    {
        'key': 'xuejie',
        'name': 'Xuejie',
        'sender_names': ('Xuejie Chen',),
        'sender_emails': ('op3@peaksmartlogistics.com',),
        'metric': 'emails',
        'responsibility': 'Domestic transportation and ocean freight support',
    },
)

MAIL_DIRECTION_SUMMARIES = (
    ('EXTERNAL_TO_LOGISTICS', 'External service → Peak Logistics'),
    ('CLIENT_TO_LOGISTICS', 'Delta customer → Peak Logistics'),
    ('LOGISTICS_TO_EXTERNAL', 'Peak Logistics → External service'),
    ('LOGISTICS_TO_WAREHOUSE', 'Peak Logistics → Warehouse'),
    ('WAREHOUSE_TO_LOGISTICS', 'Warehouse → Peak Logistics'),
    ('INTERNAL', 'Internal coordination'),
)

PEAK_LOGISTICS_DOMAIN = 'peaksmartlogistics.com'
DELTA_CUSTOMER_DOMAINS = frozenset({'deltaww.com'})


def _mailbox_datetime(value):
    if value is None:
        return None
    if timezone.is_aware(value):
        return value.astimezone(MAILBOX_TIME_ZONE).replace(tzinfo=None)
    return value


def _coerce_date(value):
    if value is None or value == '':
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def parse_statistics_scope(params, now=None):
    """Parse the safe date controls shared by the list and stats endpoints."""
    mode = str(params.get('statistics_scope') or 'ALL').strip().upper()
    if mode in {'', 'ALL'}:
        return {'date_scope': 'ALL', 'start_date': None, 'end_date': None}
    if mode == 'TODAY':
        current = now or datetime.now(MAILBOX_TIME_ZONE)
        today = current.astimezone(MAILBOX_TIME_ZONE).date() if timezone.is_aware(current) else current.date()
        return {'date_scope': 'TODAY', 'start_date': today, 'end_date': today}
    if mode not in {'CUSTOM', 'RANGE'}:
        raise ValueError('statistics_scope must be ALL, TODAY or CUSTOM')
    try:
        start_date = _coerce_date(params.get('start_date'))
        end_date = _coerce_date(params.get('end_date'))
    except (TypeError, ValueError):
        raise ValueError('start_date and end_date must use YYYY-MM-DD')
    if start_date is None or end_date is None:
        raise ValueError('start_date and end_date are required for CUSTOM statistics')
    if start_date > end_date:
        raise ValueError('start_date cannot be after end_date')
    return {'date_scope': 'CUSTOM', 'start_date': start_date, 'end_date': end_date}


def _record_mail_date(record):
    source = getattr(record, 'source', None)
    value = (
        getattr(record, 'received_at', None)
        or getattr(record, 'sent_at', None)
        or getattr(source, 'sent_at', None)
    )
    value = _mailbox_datetime(value)
    return value.date() if value is not None else None


def _records_in_date_scope(records, start_date=None, end_date=None):
    if start_date is None and end_date is None:
        return list(records)
    result = []
    for record in records:
        mail_date = _record_mail_date(record)
        if mail_date is None:
            continue
        if start_date is not None and mail_date < start_date:
            continue
        if end_date is not None and mail_date > end_date:
            continue
        result.append(record)
    return result


def mail_task_time_state(record, now=None):
    """Return the same Due/Event classification used by the board."""
    task = getattr(record, 'task', None) if getattr(record, 'task_id', None) else None
    due_at = _mailbox_datetime(getattr(task, 'due_at', None) or getattr(record, 'due_at', None))
    event_at = _mailbox_datetime(getattr(task, 'event_at', None) or getattr(record, 'event_at', None))
    if due_at is None and event_at is None:
        return 'NO_SCHEDULE'
    current = now or datetime.now(MAILBOX_TIME_ZONE).replace(tzinfo=None)
    if due_at is not None:
        due_precision = getattr(task, 'due_precision', '') or getattr(record, 'due_precision', '')
        overdue = due_at.date() < current.date() if due_precision == 'DATE_ONLY' else due_at < current
        if overdue:
            return 'OVERDUE'
        if due_at.date() == current.date():
            return 'DUE_TODAY'
    return 'SCHEDULED'


def executive_summary_for_records(records, now=None):
    """Build task-grain action metrics for management and the UI."""
    now = now or datetime.now(MAILBOX_TIME_ZONE).replace(tzinfo=None)
    summary = {
        'active': 0,
        'overdue': 0,
        'due_today': 0,
        'awaiting_sunny': 0,
        'wms_pending': 0,
        'exceptions': 0,
        'data_review': 0,
        'schedule_missing': 0,
        'sync_status': 'NOT_RUN',
        'sync_issue_count': None,
    }
    for record in records:
        task = getattr(record, 'task', None) if getattr(record, 'task_id', None) else None
        task_status = getattr(task, 'status', '') or getattr(record, 'status', '')
        if task_status != MailTask.COMPLETED:
            summary['active'] += 1
        if task_status == MailTask.AWAITING_SUNNY_APPROVAL:
            summary['awaiting_sunny'] += 1
        if task_status != MailTask.COMPLETED and mail_task_time_state(record, now=now) == 'OVERDUE':
            summary['overdue'] += 1
        if task_status != MailTask.COMPLETED and mail_task_time_state(record, now=now) == 'DUE_TODAY':
            summary['due_today'] += 1
        if task is not None and task_status != MailTask.COMPLETED and task.wms_handoff_status != MailTask.HANDOFF_COMPLETED:
            summary['wms_pending'] += 1
        if task_status == MailTask.BLOCKED or bool(getattr(record, 'exception_summary', '')):
            summary['exceptions'] += 1
        flow = getattr(task, 'flow', '') or getattr(record, 'flow', '')
        has_schedule = bool(
            _mailbox_datetime(getattr(task, 'due_at', None) or getattr(record, 'due_at', None))
            or _mailbox_datetime(getattr(task, 'event_at', None) or getattr(record, 'event_at', None))
        )
        if flow == 'REVIEW' or getattr(record, 'operation', '') == MailTask.UNKNOWN or not getattr(record, 'external_reference', '') or not has_schedule:
            summary['data_review'] += 1
        if not has_schedule:
            summary['schedule_missing'] += 1
    return summary


def _unique_task_records(records):
    result = []
    seen = set()
    for record in records:
        key = ('task', record.task_id) if getattr(record, 'task_id', None) else ('source', record.id)
        if key in seen:
            continue
        seen.add(key)
        result.append(record)
    return result


def _counts(records, field, fallback='UNKNOWN'):
    counts = Counter()
    for record in records:
        value = str(getattr(record, field, '') or fallback).upper()
        counts[value] += 1
    return dict(counts)


def _task_counts(records, field, fallback='UNKNOWN'):
    counts = Counter()
    for record in records:
        task = getattr(record, 'task', None) if getattr(record, 'task_id', None) else None
        value = str(getattr(task, field, '') or getattr(record, field, '') or fallback).upper()
        counts[value] += 1
    return dict(counts)


def _task_status_counts(records):
    counts = Counter()
    for record in records:
        task = getattr(record, 'task', None) if getattr(record, 'task_id', None) else None
        counts[str(getattr(task, 'status', '') or getattr(record, 'status', '') or 'UNKNOWN').upper()] += 1
    return dict(counts)


def _task_owner_counts(records):
    counts = Counter()
    for record in records:
        task = getattr(record, 'task', None) if getattr(record, 'task_id', None) else None
        name = str(getattr(task, 'assigned_staff_name', '') or '').strip()
        role = str(getattr(task, 'assigned_role', '') or getattr(record, 'owner_role', '') or '').strip()
        counts[name or role or 'UNASSIGNED'] += 1
    return dict(counts)


def _task_owner_count(records, name, role):
    count = 0
    for record in records:
        task = getattr(record, 'task', None) if getattr(record, 'task_id', None) else None
        assigned_name = str(getattr(task, 'assigned_staff_name', '') or '').strip().lower()
        assigned_role = str(getattr(task, 'assigned_role', '') or '').strip().upper()
        if assigned_name == name.lower() or (not assigned_name and assigned_role == role):
            count += 1
    return count


def _sender_email(record):
    return str(getattr(record, 'sender_email', '') or '').strip().lower()


def _sender_name(record):
    return str(getattr(record, 'sender_name', '') or '').strip().lower()


def _sender_domain(record):
    email = _sender_email(record)
    return email.rsplit('@', 1)[1] if '@' in email else ''


def _management_summary(source_records, task_records):
    people = []
    named_sender_keys = set()
    for definition in EXECUTIVE_PEOPLE:
        names = {item.lower() for item in definition['sender_names']}
        emails = {item.lower() for item in definition['sender_emails']}
        count = 0
        for record in source_records:
            if _sender_name(record) in names or _sender_email(record) in emails:
                count += 1
                named_sender_keys.add(record.id)
        people.append({
            'key': definition['key'],
            'name': definition['name'],
            'count': count,
            'metric': definition['metric'],
            'responsibility': definition['responsibility'],
        })

    people.append({
        'key': 'maggie',
        'name': 'Maggie',
        'count': _task_owner_count(task_records, 'Maggie', MailTask.WMS_OPERATOR),
        'metric': 'tasks',
        'responsibility': 'WMS operator for inbound and outbound tasks',
    })
    mark_tasks = _task_owner_count(task_records, 'Mark', MailTask.SITE_OPERATOR)
    people.append({
        'key': 'mark',
        'name': 'Mark',
        'count': mark_tasks,
        'metric': 'site_tasks',
        'responsibility': 'Primarily coordinates on-site receiving and shipping; no active site tasks yet',
    })

    other_internal_count = sum(
        1 for record in source_records
        if _sender_domain(record) == PEAK_LOGISTICS_DOMAIN and record.id not in named_sender_keys
    )
    if other_internal_count:
        people.append({
            'key': 'other_internal',
            'name': 'Other internal sender',
            'count': other_internal_count,
            'metric': 'emails',
            'responsibility': 'Responsibility not yet confirmed',
        })

    external_service_count = 0
    customer_count = 0
    for record in source_records:
        domain = _sender_domain(record)
        if domain in DELTA_CUSTOMER_DOMAINS:
            customer_count += 1
        elif domain != PEAK_LOGISTICS_DOMAIN:
            external_service_count += 1

    sender_groups = [
        {'key': 'EXTERNAL_SERVICE', 'label': 'External service senders', 'count': external_service_count},
        {'key': 'DELTA_CUSTOMER', 'label': 'Delta customer senders', 'count': customer_count},
    ]
    direction_counts = [
        {'key': key, 'label': label, 'count': _counts(source_records, 'flow').get(key, 0)}
        for key, label in MAIL_DIRECTION_SUMMARIES
    ]
    return {
        'people': people,
        'sender_groups': sender_groups,
        'direction_counts': direction_counts,
    }


def _mailbox_stats(openid, source_records, latest_run, date_scoped=False):
    classification = {}
    metadata = latest_run.metadata if latest_run and isinstance(latest_run.metadata, dict) else {}
    if isinstance(metadata.get('classification'), dict):
        classification = metadata['classification']

    source_status_counts = _counts(source_records, 'status', fallback='UNKNOWN')
    captured = len(source_records)
    review = source_status_counts.get(SourceIntakeRecord.REVIEW_REQUIRED, 0)
    failed = source_status_counts.get(SourceIntakeRecord.FAILED, 0)
    accepted = source_status_counts.get(SourceIntakeRecord.CAPTURED, 0)
    scanned = int(classification.get('total') or (latest_run.fetched_count if latest_run else captured) or 0)
    unique = int(classification.get('unique') or max(scanned - int(classification.get('duplicates') or 0), 0))

    def metadata_count(name, fallback):
        if name in classification and classification[name] is not None:
            return int(classification[name] or 0)
        return int(fallback or 0)

    duplicate_count = metadata_count('duplicates', latest_run.duplicate_count if latest_run else 0)
    review = metadata_count('review_required', latest_run.review_count if latest_run else review)
    failed = metadata_count('failed', latest_run.failed_count if latest_run else failed)
    accepted = metadata_count('accepted_operational', accepted or max(captured - review - failed, 0))
    operational_written = int(latest_run.captured_count if latest_run else captured)
    excluded = metadata_count('excluded_non_operational', max(scanned - operational_written - duplicate_count - failed, 0))
    mailbox_account = latest_run.mailbox_account if latest_run else (source_records[0].mailbox_account if source_records else '')
    attachment_queryset = SourceAttachment.objects.filter(source__openid=openid)
    if mailbox_account:
        attachment_queryset = attachment_queryset.filter(source__mailbox_account=mailbox_account)
    if date_scoped:
        attachment_queryset = attachment_queryset.filter(source_id__in=[record.source_id for record in source_records])
    attachments = attachment_queryset.count()
    attachment_parts = int(classification.get('attachments_saved') or metadata.get('attachment_parts') or attachments)
    unique_attachment_files = int(
        classification.get('attachment_files')
        or metadata.get('deduplicated_attachment_files')
        or attachments
    )
    if date_scoped:
        # A date-scoped report has no per-message scan ledger.  Use captured
        # source records as the honest denominator, excluding audit-only
        # duplicate projections. Keep the duplicate status breakdown below so
        # the audit trail remains visible without inflating the mailbox count.
        operational_records = [
            record for record in source_records
            if getattr(record, 'status', '') != SourceIntakeRecord.DUPLICATE
        ]
        operational_source_ids = [record.source_id for record in operational_records]
        scoped_attachments = SourceAttachment.objects.filter(source_id__in=operational_source_ids)
        scoped_attachment_parts = scoped_attachments.count()
        scoped_accepted = sum(
            1 for record in operational_records
            if getattr(record, 'status', '') == SourceIntakeRecord.CAPTURED
        )
        scoped_review = sum(
            1 for record in operational_records
            if getattr(record, 'status', '') == SourceIntakeRecord.REVIEW_REQUIRED
        )
        scoped_failed = sum(
            1 for record in operational_records
            if getattr(record, 'status', '') == SourceIntakeRecord.FAILED
        )
        return {
            'account': mailbox_account,
            'sync_run_id': latest_run.id if latest_run else None,
            'sync_status': latest_run.status if latest_run else 'NOT_RUN',
            'scanned': len(operational_records),
            'unique': len(operational_records),
            'duplicate': 0,
            'operational_written': len(operational_records),
            'accepted': scoped_accepted,
            'review': scoped_review,
            'excluded': None,
            'failed': scoped_failed,
            'attachment_parts': scoped_attachment_parts,
            'attachments_db_records': scoped_attachments.count(),
            'unique_attachment_files': scoped_attachments.count(),
            'source_status_counts': source_status_counts,
            'scan_finished_at': metadata.get('scanFinishedAt') or '',
            'basis': 'CAPTURED_SOURCE_RECORDS',
        }
    return {
        'account': mailbox_account,
        'sync_run_id': latest_run.id if latest_run else None,
        'sync_status': latest_run.status if latest_run else 'NOT_RUN',
        'scanned': scanned,
        'unique': unique,
        'duplicate': duplicate_count,
        'operational_written': operational_written,
        'accepted': accepted,
        'review': review,
        'excluded': excluded,
        'failed': failed,
        'attachment_parts': attachment_parts,
        'attachments_db_records': attachments,
        'unique_attachment_files': unique_attachment_files,
        'source_status_counts': source_status_counts,
        'scan_finished_at': metadata.get('scanFinishedAt') or '',
        'basis': 'MAILBOX_SCAN',
    }


def build_mailtask_statistics(
    openid,
    source_records=None,
    task_records=None,
    now=None,
    date_scope='ALL',
    start_date=None,
    end_date=None,
):
    """Return the canonical source-grain and task-grain Mail2Task metrics."""
    if source_records is None:
        source_records = list(
            SourceIntakeRecord.objects.filter(openid=openid)
            .select_related('source', 'task')
        )
    else:
        source_records = list(source_records)
    date_scope = str(date_scope or 'ALL').strip().upper()
    start_date = _coerce_date(start_date)
    end_date = _coerce_date(end_date)
    if date_scope == 'TODAY' and start_date is None and end_date is None:
        current = now or datetime.now(MAILBOX_TIME_ZONE)
        current = current.astimezone(MAILBOX_TIME_ZONE) if timezone.is_aware(current) else current
        start_date = end_date = current.date()
    scoped = start_date is not None or end_date is not None
    scoped_source_records = _records_in_date_scope(source_records, start_date, end_date)
    # Duplicate source projections are retained as audit evidence, but they
    # are not another operational email. Keep them available to mailbox-level
    # audit metrics while excluding them from the source/task/management
    # grains so a smoke-test retry cannot inflate today's business counts.
    operational_source_records = [
        record for record in scoped_source_records
        if getattr(record, 'status', '') != SourceIntakeRecord.DUPLICATE
    ]
    if scoped:
        # A follow-up email in the selected range still contributes to its
        # one canonical task, but must not make an unrelated task appear.
        task_records = _unique_task_records(operational_source_records)
    elif task_records is None:
        task_records = _unique_task_records(
            record for record in source_records
            if getattr(record, 'status', '') != SourceIntakeRecord.DUPLICATE
        )
    else:
        task_records = list(task_records)
    latest_run = MailboxSyncRun.objects.filter(openid=openid).order_by('-started_at', '-id').first()

    email_counts = Counter()
    for record in operational_source_records:
        key = ('task', record.task_id) if getattr(record, 'task_id', None) else ('source', record.id)
        email_counts[key] += 1

    task_status_counts = _task_status_counts(task_records)
    task_stats = {
        'total': len(task_records),
        'linked_emails': len(operational_source_records),
        'multi_email_tasks': sum(1 for count in email_counts.values() if count > 1),
        'email_distribution': dict(sorted(Counter(str(count) for count in email_counts.values()).items(), key=lambda item: int(item[0]))),
        'status_counts': task_status_counts,
        'operation_counts': _task_counts(task_records, 'operation'),
        'flow_counts': _task_counts(task_records, 'flow'),
        'owner_counts': _task_owner_counts(task_records),
        'wms_handoff_counts': _task_counts(task_records, 'wms_handoff_status'),
        'executive_summary': executive_summary_for_records(task_records, now=now),
    }
    source_stats = {
        'total': len(operational_source_records),
        'operation_counts': _counts(operational_source_records, 'operation'),
        'flow_counts': _counts(operational_source_records, 'flow'),
        'document_counts': _counts(operational_source_records, 'document_type'),
        'status_counts': _counts(operational_source_records, 'status'),
    }
    scope = {
        'mode': date_scope if scoped else 'ALL',
        'start_date': start_date.isoformat() if start_date else None,
        'end_date': end_date.isoformat() if end_date else None,
        'timezone': str(MAILBOX_TIME_ZONE),
        'basis': 'received_at, fallback sent_at; source records without a mail date are excluded from a date range',
    }
    return {
        'scope': scope,
        'grain_definitions': {
            'mail': 'One row per scanned mailbox message; follow-up messages remain separate evidence.',
            'source': 'One row per operational email written to SourceIntakeRecord.',
            'task': 'One row per merged business task; linked follow-up emails do not create a second task.',
        },
        'mailbox': _mailbox_stats(openid, scoped_source_records, latest_run, date_scoped=scoped),
        'source': source_stats,
        'task': task_stats,
        'management': _management_summary(operational_source_records, task_records),
        'executive_summary': task_stats['executive_summary'],
        'reconciliation': {
            'status': 'NOT_RUN',
            'issue_count': None,
            'scope': 'Mail vs Dashboard vs Delta Daily Summary vs WMS',
        },
    }
