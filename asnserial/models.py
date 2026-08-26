from django.db import models
from django.db.models import Q


class SourceEvidence(models.Model):
    """Immutable-ish provenance record for an external warehouse instruction."""

    WEB_FORM = 'WEB_FORM'
    EMAIL = 'EMAIL'
    AI_AGENT = 'AI_AGENT'
    CLI = 'CLI'
    SOURCE_TYPES = (
        (WEB_FORM, 'Web form'),
        (EMAIL, 'Email'),
        (AI_AGENT, 'AI agent'),
        (CLI, 'CLI'),
    )

    CAPTURED = 'CAPTURED'
    USED = 'USED'
    EXPIRED = 'EXPIRED'
    STATUS_CHOICES = (
        (CAPTURED, 'Captured'),
        (USED, 'Used'),
        (EXPIRED, 'Expired'),
    )

    openid = models.CharField(max_length=255)
    mailbox_account = models.CharField(max_length=255, blank=True, default='')
    message_id = models.CharField(max_length=512, blank=True, default='')
    thread_id = models.CharField(max_length=512, blank=True, default='')
    source_type = models.CharField(max_length=32, choices=SOURCE_TYPES)
    operation = models.CharField(max_length=64)
    content_hash = models.CharField(max_length=64, blank=True, default='')
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=CAPTURED)
    captured_by = models.CharField(max_length=255, blank=True, default='')
    captured_by_name = models.CharField(max_length=255, blank=True, default='')
    ai_session_id = models.CharField(max_length=255, blank=True, default='')
    metadata = models.JSONField(default=dict)
    storage_uri = models.CharField(max_length=1000, blank=True, default='')
    storage_size = models.PositiveBigIntegerField(default=0)
    sent_at = models.DateTimeField(blank=True, null=True)
    captured_at = models.DateTimeField(auto_now_add=True)
    used_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = 'sourceevidence'
        ordering = ['-captured_at', '-id']
        indexes = [
            models.Index(fields=['openid', 'operation', 'captured_at']),
            models.Index(fields=['openid', 'content_hash']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['openid', 'source_type', 'mailbox_account', 'message_id', 'content_hash'],
                condition=Q(
                    source_type='EMAIL',
                    mailbox_account__gt='',
                    message_id__gt='',
                    content_hash__gt='',
                ),
                name='sourceevidence_email_message_hash_unique',
            ),
        ]


class MailboxSyncRun(models.Model):
    """One Codex Automation mailbox scan, kept separate from business writes."""

    CODEX_AUTOMATION = 'CODEX_AUTOMATION'
    MANUAL = 'MANUAL'
    TRIGGER_CHOICES = (
        (CODEX_AUTOMATION, 'Codex Automation'),
        (MANUAL, 'Manual'),
    )

    RUNNING = 'RUNNING'
    SUCCEEDED = 'SUCCEEDED'
    PARTIAL = 'PARTIAL'
    FAILED = 'FAILED'
    STATUS_CHOICES = (
        (RUNNING, 'Running'),
        (SUCCEEDED, 'Succeeded'),
        (PARTIAL, 'Partial'),
        (FAILED, 'Failed'),
    )

    openid = models.CharField(max_length=255)
    mailbox_account = models.CharField(max_length=255)
    trigger_source = models.CharField(max_length=32, choices=TRIGGER_CHOICES, default=CODEX_AUTOMATION)
    automation_run_id = models.CharField(max_length=255, blank=True, default='')
    cursor_before = models.CharField(max_length=1000, blank=True, default='')
    cursor_after = models.CharField(max_length=1000, blank=True, default='')
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=RUNNING)
    fetched_count = models.PositiveIntegerField(default=0)
    captured_count = models.PositiveIntegerField(default=0)
    duplicate_count = models.PositiveIntegerField(default=0)
    review_count = models.PositiveIntegerField(default=0)
    failed_count = models.PositiveIntegerField(default=0)
    error_summary = models.TextField(blank=True, default='')
    metadata = models.JSONField(default=dict)
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = 'mailboxsyncrun'
        ordering = ['-started_at', '-id']
        indexes = [
            models.Index(fields=['openid', 'mailbox_account', 'started_at']),
            models.Index(fields=['openid', 'status', 'started_at']),
        ]


class MailboxSyncState(models.Model):
    """Durable cursor and lease for one tenant mailbox automation stream."""

    openid = models.CharField(max_length=255)
    mailbox_account = models.CharField(max_length=255)
    cursor = models.CharField(max_length=1000, blank=True, default='')
    active_run = models.ForeignKey(
        MailboxSyncRun,
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name='+',
    )
    last_successful_run = models.ForeignKey(
        MailboxSyncRun,
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name='+',
    )
    lease_expires_at = models.DateTimeField(blank=True, null=True)
    last_error = models.TextField(blank=True, default='')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'mailboxsyncstate'
        constraints = [
            models.UniqueConstraint(
                fields=['openid', 'mailbox_account'],
                name='mailboxsyncstate_tenant_account_unique',
            ),
        ]
        indexes = [
            models.Index(fields=['openid', 'mailbox_account']),
            models.Index(fields=['openid', 'lease_expires_at']),
        ]


class SourceAttachment(models.Model):
    """Metadata for an email attachment; bytes live outside the WMS database."""

    PENDING = 'PENDING'
    STORED = 'STORED'
    REJECTED = 'REJECTED'
    SECURITY_STATUS_CHOICES = (
        (PENDING, 'Pending'),
        (STORED, 'Stored'),
        (REJECTED, 'Rejected'),
    )

    source = models.ForeignKey(
        SourceEvidence,
        related_name='attachments',
        on_delete=models.PROTECT,
    )
    openid = models.CharField(max_length=255)
    attachment_name = models.CharField(max_length=512)
    content_type = models.CharField(max_length=255, blank=True, default='')
    content_hash = models.CharField(max_length=64)
    storage_uri = models.CharField(max_length=1000, blank=True, default='')
    storage_size = models.PositiveBigIntegerField(default=0)
    security_status = models.CharField(max_length=16, choices=SECURITY_STATUS_CHOICES, default=PENDING)
    source_location = models.CharField(max_length=255, blank=True, default='')
    metadata = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'sourceattachment'
        ordering = ['id']
        indexes = [
            models.Index(fields=['openid', 'content_hash']),
            models.Index(fields=['source', 'attachment_name']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['source', 'content_hash'],
                name='sourceattachment_source_hash_unique',
            ),
        ]


class SourceIntakeRecord(models.Model):
    """Current processing state for one captured external source."""

    INBOUND = 'INBOUND'
    OUTBOUND = 'OUTBOUND'
    SUPPORTING = 'SUPPORTING'
    UNKNOWN = 'UNKNOWN'
    OPERATION_CHOICES = (
        (INBOUND, 'Inbound'),
        (OUTBOUND, 'Outbound'),
        (SUPPORTING, 'Supporting'),
        (UNKNOWN, 'Unknown'),
    )

    INBOUND_NOTICE = 'INBOUND_NOTICE'
    PACK_LIST = 'PACK_LIST'
    PICK_TICKET = 'PICK_TICKET'
    DELIVERY_REQUEST = 'DELIVERY_REQUEST'
    APPOINTMENT = 'APPOINTMENT'
    QC_SCAN = 'QC_SCAN'
    OTHER = 'OTHER'
    DOCUMENT_CHOICES = (
        (INBOUND_NOTICE, 'Inbound notice'),
        (PACK_LIST, 'Pack List'),
        (PICK_TICKET, 'Pick Ticket'),
        (DELIVERY_REQUEST, 'Delivery request'),
        (APPOINTMENT, 'Appointment'),
        (QC_SCAN, 'QC / scan sheet'),
        (OTHER, 'Other'),
    )

    CAPTURED = 'CAPTURED'
    ANALYZING = 'ANALYZING'
    REVIEW_REQUIRED = 'REVIEW_REQUIRED'
    READY_FOR_PREVIEW = 'READY_FOR_PREVIEW'
    APPROVAL_REQUIRED = 'APPROVAL_REQUIRED'
    EXECUTING = 'EXECUTING'
    COMPLETED = 'COMPLETED'
    BLOCKED = 'BLOCKED'
    DUPLICATE = 'DUPLICATE'
    FAILED = 'FAILED'
    STATUS_CHOICES = (
        (CAPTURED, 'Captured'),
        (ANALYZING, 'Analyzing'),
        (REVIEW_REQUIRED, 'Review required'),
        (READY_FOR_PREVIEW, 'Ready for preview'),
        (APPROVAL_REQUIRED, 'Approval required'),
        (EXECUTING, 'Executing'),
        (COMPLETED, 'Completed'),
        (BLOCKED, 'Blocked'),
        (DUPLICATE, 'Duplicate'),
        (FAILED, 'Failed'),
    )

    source = models.OneToOneField(
        SourceEvidence,
        related_name='intake_record',
        on_delete=models.PROTECT,
    )
    sync_run = models.ForeignKey(
        MailboxSyncRun,
        related_name='intake_records',
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
    )
    task = models.ForeignKey(
        'MailTask',
        related_name='intake_records',
        blank=True,
        null=True,
        on_delete=models.PROTECT,
    )
    openid = models.CharField(max_length=255)
    mailbox_account = models.CharField(max_length=255, blank=True, default='')
    operation = models.CharField(max_length=16, choices=OPERATION_CHOICES, default=UNKNOWN)
    document_type = models.CharField(max_length=32, choices=DOCUMENT_CHOICES, default=OTHER)
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default=CAPTURED)
    sender_name = models.CharField(max_length=255, blank=True, default='')
    sender_email = models.CharField(max_length=255, blank=True, default='')
    subject = models.CharField(max_length=1000, blank=True, default='')
    external_reference = models.CharField(max_length=255, blank=True, default='')
    matched_entity_type = models.CharField(max_length=64, blank=True, default='')
    matched_entity_ref = models.CharField(max_length=255, blank=True, default='')
    owner_role = models.CharField(max_length=64, blank=True, default='')
    next_action = models.CharField(max_length=1000, blank=True, default='')
    exception_summary = models.TextField(blank=True, default='')
    last_error = models.TextField(blank=True, default='')
    classification_confidence = models.DecimalField(max_digits=5, decimal_places=4, blank=True, null=True)
    metadata = models.JSONField(default=dict)
    sent_at = models.DateTimeField(blank=True, null=True)
    received_at = models.DateTimeField(blank=True, null=True)
    reviewed_at = models.DateTimeField(blank=True, null=True)
    completed_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'sourceintakerecord'
        ordering = ['-updated_at', '-id']
        indexes = [
            models.Index(fields=['openid', 'status', 'updated_at']),
            models.Index(fields=['openid', 'operation', 'updated_at']),
            models.Index(fields=['openid', 'mailbox_account', 'received_at']),
            models.Index(fields=['openid', 'matched_entity_type', 'matched_entity_ref']),
        ]


class MailTask(models.Model):
    """Canonical work item shared by one or more email intake records.

    SourceIntakeRecord remains the immutable-ish email/evidence projection. A
    MailTask is the operational record that can receive follow-up messages
    without resetting the same warehouse job to a new status.
    """

    INBOUND = 'INBOUND'
    OUTBOUND = 'OUTBOUND'
    SUPPORTING = 'SUPPORTING'
    UNKNOWN = 'UNKNOWN'
    OPERATION_CHOICES = (
        (INBOUND, 'Inbound'),
        (OUTBOUND, 'Outbound'),
        (SUPPORTING, 'Supporting'),
        (UNKNOWN, 'Unknown'),
    )

    OPEN = 'OPEN'
    AWAITING_SUNNY_APPROVAL = 'AWAITING_SUNNY_APPROVAL'
    READY_FOR_MARK = 'READY_FOR_MARK'
    SITE_IN_PROGRESS = 'SITE_IN_PROGRESS'
    WMS_FINALIZATION = 'WMS_FINALIZATION'
    COMPLETED = 'COMPLETED'
    BLOCKED = 'BLOCKED'
    STATUS_CHOICES = (
        (OPEN, 'Open'),
        (AWAITING_SUNNY_APPROVAL, 'Awaiting Sunny approval'),
        (READY_FOR_MARK, 'Ready for Mark'),
        (SITE_IN_PROGRESS, 'Site work in progress'),
        (WMS_FINALIZATION, 'Awaiting Maggie WMS update'),
        (COMPLETED, 'Completed'),
        (BLOCKED, 'Blocked'),
    )

    SUPERVISOR = 'SUPERVISOR'
    WMS_OPERATOR = 'WMS_OPERATOR'
    SITE_OPERATOR = 'SITE_OPERATOR'
    TASK_ROLE_CHOICES = (
        (SUPERVISOR, 'Sunny / Supervisor'),
        (WMS_OPERATOR, 'Maggie / WMS operator'),
        (SITE_OPERATOR, 'Mark / Site operator'),
    )

    TO_MAGGIE = 'TO_MAGGIE'
    TO_SUNNY = 'TO_SUNNY'
    TO_MARK = 'TO_MARK'
    SITE_IN_PROGRESS_HANDOFF = 'SITE_IN_PROGRESS'
    RETURNED_TO_MAGGIE = 'RETURNED_TO_MAGGIE'
    HANDOFF_COMPLETED = 'COMPLETED'
    HANDOFF_BLOCKED = 'BLOCKED'
    HANDOFF_STATUS_CHOICES = (
        (TO_MAGGIE, 'To Maggie'),
        (TO_SUNNY, 'To Sunny'),
        (TO_MARK, 'To Mark'),
        (SITE_IN_PROGRESS_HANDOFF, 'Mark is working'),
        (RETURNED_TO_MAGGIE, 'Returned to Maggie'),
        (HANDOFF_COMPLETED, 'Completed'),
        (HANDOFF_BLOCKED, 'Blocked'),
    )

    LEGACY_PROD = 'LEGACY_PROD'
    MIGRATED = 'MIGRATED'
    WMS_SYSTEM_CHOICES = (
        (LEGACY_PROD, 'Legacy production'),
        (MIGRATED, 'Migrated GreaterWMS'),
    )

    openid = models.CharField(max_length=255)
    task_ref = models.CharField(max_length=255)
    operation = models.CharField(max_length=16, choices=OPERATION_CHOICES, default=UNKNOWN)
    subject = models.CharField(max_length=1000, blank=True, default='')
    external_reference = models.CharField(max_length=255, blank=True, default='')
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default=OPEN)
    assigned_role = models.CharField(max_length=32, choices=TASK_ROLE_CHOICES, default=WMS_OPERATOR)
    assigned_staff_id = models.PositiveBigIntegerField(blank=True, null=True)
    assigned_staff_name = models.CharField(max_length=255, blank=True, default='')
    next_action = models.CharField(max_length=1000, blank=True, default='')
    wms_handoff_status = models.CharField(max_length=32, choices=HANDOFF_STATUS_CHOICES, default=TO_MAGGIE)
    wms_entity_system = models.CharField(max_length=32, choices=WMS_SYSTEM_CHOICES, blank=True, default='')
    wms_entity_type = models.CharField(max_length=64, blank=True, default='')
    wms_entity_ref = models.CharField(max_length=255, blank=True, default='')
    wms_handoff_note = models.TextField(blank=True, default='')
    completed_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'mailtask'
        ordering = ['-updated_at', '-id']
        constraints = [
            models.UniqueConstraint(
                fields=['openid', 'task_ref'],
                name='mailtask_tenant_task_ref_unique',
            ),
        ]
        indexes = [
            models.Index(fields=['openid', 'status', 'updated_at']),
            models.Index(fields=['openid', 'assigned_role', 'status']),
            models.Index(fields=['openid', 'wms_handoff_status', 'updated_at']),
        ]


class MailTaskApproval(models.Model):
    """Separate approval record for Sunny's outbound final decision."""

    OUTBOUND_FINAL = 'OUTBOUND_FINAL'
    APPROVAL_TYPE_CHOICES = ((OUTBOUND_FINAL, 'Outbound final approval'),)
    PENDING = 'PENDING'
    APPROVED = 'APPROVED'
    REJECTED = 'REJECTED'
    STATUS_CHOICES = (
        (PENDING, 'Pending'),
        (APPROVED, 'Approved'),
        (REJECTED, 'Rejected'),
    )

    task = models.ForeignKey(MailTask, related_name='approvals', on_delete=models.PROTECT)
    openid = models.CharField(max_length=255)
    approval_type = models.CharField(max_length=32, choices=APPROVAL_TYPE_CHOICES, default=OUTBOUND_FINAL)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=PENDING)
    requested_by_id = models.PositiveBigIntegerField(blank=True, null=True)
    requested_by_name = models.CharField(max_length=255, blank=True, default='')
    decided_by_id = models.PositiveBigIntegerField(blank=True, null=True)
    decided_by_name = models.CharField(max_length=255, blank=True, default='')
    note = models.TextField(blank=True, default='')
    requested_at = models.DateTimeField(auto_now_add=True)
    decided_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = 'mailtaskapproval'
        ordering = ['-requested_at', '-id']
        constraints = [
            models.UniqueConstraint(
                fields=['task', 'status'],
                condition=Q(status='PENDING'),
                name='mailtask_one_pending_approval',
            ),
        ]
        indexes = [
            models.Index(fields=['openid', 'status', 'requested_at']),
            models.Index(fields=['task', 'approval_type', 'requested_at']),
        ]


class MailTaskEvent(models.Model):
    """Append-only task workflow history, independent of individual emails."""

    task = models.ForeignKey(MailTask, related_name='task_events', on_delete=models.PROTECT)
    source_evidence = models.ForeignKey(
        SourceEvidence,
        related_name='mailtask_events',
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
    )
    openid = models.CharField(max_length=255)
    action = models.CharField(max_length=64)
    from_status = models.CharField(max_length=32, blank=True, default='')
    to_status = models.CharField(max_length=32, blank=True, default='')
    actor_role = models.CharField(max_length=32, blank=True, default='')
    actor_id = models.PositiveBigIntegerField(blank=True, null=True)
    actor_name = models.CharField(max_length=255, blank=True, default='')
    note = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'mailtaskevent'
        ordering = ['-created_at', '-id']
        indexes = [
            models.Index(fields=['openid', 'task', 'created_at']),
            models.Index(fields=['openid', 'action', 'created_at']),
        ]


class SourceIntakeEvent(models.Model):
    """Append-only state changes for the source intake board."""

    intake = models.ForeignKey(
        SourceIntakeRecord,
        related_name='events',
        on_delete=models.PROTECT,
    )
    openid = models.CharField(max_length=255)
    status = models.CharField(max_length=32)
    event_type = models.CharField(max_length=64)
    message = models.TextField(blank=True, default='')
    actor_type = models.CharField(max_length=64, blank=True, default='')
    actor_name = models.CharField(max_length=255, blank=True, default='')
    metadata = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'sourceintakeevent'
        ordering = ['-created_at', '-id']
        indexes = [
            models.Index(fields=['openid', 'intake', 'created_at']),
            models.Index(fields=['openid', 'status', 'created_at']),
        ]


class SourceExtraction(models.Model):
    """A normalized field extracted from a source without storing credentials."""

    source = models.ForeignKey(SourceEvidence, related_name='extractions', on_delete=models.CASCADE)
    field_name = models.CharField(max_length=128)
    raw_value = models.TextField(blank=True, default='')
    normalized_value = models.TextField(blank=True, default='')
    source_location = models.CharField(max_length=255, blank=True, default='')
    confidence = models.DecimalField(max_digits=5, decimal_places=4, blank=True, null=True)
    human_confirmed = models.BooleanField(default=False)
    used_for_write = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'sourceextraction'
        ordering = ['id']
        indexes = [
            models.Index(fields=['source', 'field_name']),
        ]


class EntityProvenance(models.Model):
    """Field-level link from a WMS entity back to captured source evidence."""

    source = models.ForeignKey(
        SourceEvidence,
        related_name='provenance',
        on_delete=models.PROTECT,
    )
    source_extraction = models.ForeignKey(
        SourceExtraction,
        blank=True,
        null=True,
        related_name='provenance',
        on_delete=models.SET_NULL,
    )
    openid = models.CharField(max_length=255)
    entity_type = models.CharField(max_length=64)
    entity_ref = models.CharField(max_length=255)
    field_name = models.CharField(max_length=128)
    raw_value = models.TextField(blank=True, default='')
    normalized_value = models.TextField(blank=True, default='')
    used_for_write = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'entityprovenance'
        ordering = ['id']
        indexes = [
            models.Index(fields=['openid', 'entity_type', 'entity_ref']),
            models.Index(fields=['source', 'field_name']),
        ]


class PackListImportBatch(models.Model):
    PACK_LIST = 'PACK_LIST'
    EXPECTED_SERIALS = 'EXPECTED_SERIALS'
    RECEIVING_ACCEPTANCE = 'RECEIVING_ACCEPTANCE'

    IMPORT_TYPES = (
        (PACK_LIST, 'Pack List'),
        (EXPECTED_SERIALS, 'Expected serials'),
        (RECEIVING_ACCEPTANCE, 'Receiving acceptance'),
    )

    IMPORTED = 'IMPORTED'
    PASSED = 'PASSED'
    EXCEPTION = 'EXCEPTION'
    PARTIAL = 'PARTIAL'

    STATUS_CHOICES = (
        (IMPORTED, 'Imported'),
        (PASSED, 'Passed'),
        (EXCEPTION, 'Exception'),
        (PARTIAL, 'Partial'),
    )

    openid = models.CharField(max_length=255)
    asn_code = models.CharField(max_length=255)
    import_type = models.CharField(max_length=32, choices=IMPORT_TYPES)
    content_hash = models.CharField(max_length=64, blank=True, default='')
    row_count = models.PositiveIntegerField(default=0)
    matched_count = models.PositiveIntegerField(default=0)
    accepted_count = models.PositiveIntegerField(default=0)
    exception_count = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default=IMPORTED)
    source_type = models.CharField(max_length=32, blank=True, default='AI_AGENT')
    imported_by = models.CharField(max_length=255, blank=True, default='')
    note = models.TextField(blank=True, default='')
    evidence_url = models.CharField(max_length=1000, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'packlistimportbatch'
        ordering = ['-created_at', '-id']
        indexes = [
            models.Index(fields=['openid', 'asn_code', 'import_type']),
            models.Index(fields=['openid', 'import_type', 'content_hash']),
        ]


class PackListDocument(models.Model):
    PENDING = 'PENDING'
    CONFIRMED = 'CONFIRMED'
    ARCHIVED = 'ARCHIVED'

    STATUS_CHOICES = (
        (PENDING, 'Pending confirmation'),
        (CONFIRMED, 'Confirmed'),
        (ARCHIVED, 'Archived'),
    )

    SOURCE_TYPES = (
        ('AI_AGENT', 'AI Agent'),
        ('UPLOAD', 'Uploaded file'),
        ('EMAIL', 'Email attachment'),
        ('GOOGLE_DRIVE', 'Google Drive'),
        ('MANUAL', 'Manual entry'),
    )

    openid = models.CharField(max_length=255)
    asn_code = models.CharField(max_length=255)
    version = models.PositiveIntegerField(default=1)
    source_type = models.CharField(max_length=32, choices=SOURCE_TYPES, default='AI_AGENT')
    content_hash = models.CharField(max_length=64, blank=True, default='')
    is_current = models.BooleanField(default=True)
    import_batch = models.ForeignKey(
        'PackListImportBatch',
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name='pack_lists',
    )
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default=PENDING)
    late_reference = models.BooleanField(default=False)
    has_serials = models.BooleanField(default=False)
    package_qty = models.PositiveIntegerField(default=0)
    note = models.TextField(blank=True, default='')
    created_by = models.CharField(max_length=255, blank=True, default='')
    confirmed_by = models.CharField(max_length=255, blank=True, default='')
    confirmed_at = models.DateTimeField(blank=True, null=True)
    create_time = models.DateTimeField(auto_now_add=True)
    update_time = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'packlistdocument'
        ordering = ['-version', '-id']
        indexes = [
            models.Index(fields=['openid', 'asn_code', 'status']),
            models.Index(fields=['openid', 'asn_code', 'content_hash']),
            models.Index(fields=['openid', 'source_type']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['openid', 'asn_code'],
                condition=Q(is_current=True),
                name='packlistdocument_one_current_per_asn',
            ),
        ]


class PackListLine(models.Model):
    pack_list = models.ForeignKey(PackListDocument, related_name='lines', on_delete=models.CASCADE)
    openid = models.CharField(max_length=255)
    asn_code = models.CharField(max_length=255)
    goods_code = models.CharField(max_length=255)
    customer_goods_code = models.CharField(max_length=255, blank=True, default='')
    is_current = models.BooleanField(default=True)
    goods_qty = models.PositiveIntegerField(default=0)
    total_qty = models.PositiveIntegerField(default=0)
    package_type = models.CharField(max_length=255, blank=True, default='')
    goods_desc = models.CharField(max_length=1000, blank=True, default='')
    customer_ssku = models.CharField(max_length=255, blank=True, default='')
    goods_weight = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    goods_volume = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    source_row = models.PositiveIntegerField(default=0)
    create_time = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'packlistline'
        ordering = ['source_row', 'goods_code', 'id']
        indexes = [
            models.Index(fields=['openid', 'asn_code', 'goods_code']),
            models.Index(fields=['pack_list', 'goods_code']),
        ]


class AgentCommandPreview(models.Model):
    """One-time server-side preview used by the GreaterWMS CLI."""

    PENDING = 'PENDING'
    APPROVED = 'APPROVED'
    EXECUTED = 'EXECUTED'

    openid = models.CharField(max_length=255)
    operation = models.CharField(max_length=64)
    resource_id = models.CharField(max_length=255, blank=True, default='')
    asn_code = models.CharField(max_length=255, blank=True, default='')
    payload_hash = models.CharField(max_length=64)
    confirmation_token_hash = models.CharField(max_length=64, blank=True, default='')
    idempotency_key = models.CharField(max_length=255, blank=True, default='')
    preview_payload = models.JSONField(default=dict)
    result = models.JSONField(blank=True, null=True)
    status = models.CharField(max_length=16, default=PENDING)
    execution_surface = models.CharField(max_length=16, default='CLI')
    source_evidence = models.ForeignKey(
        SourceEvidence,
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name='previews',
    )
    created_by = models.CharField(max_length=255, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = 'agentcommandpreview'
        ordering = ['-created_at', '-id']
        indexes = [
            models.Index(fields=['openid', 'operation', 'created_at']),
            models.Index(fields=['openid', 'confirmation_token_hash']),
            models.Index(fields=['openid', 'idempotency_key']),
        ]


class OperationAudit(models.Model):
    """Append-only audit summary for AI, web and legacy CLI operations."""

    PREVIEWED = 'PREVIEWED'
    APPROVED = 'APPROVED'
    SUCCEEDED = 'SUCCEEDED'
    FAILED = 'FAILED'
    REJECTED = 'REJECTED'

    preview = models.ForeignKey(
        AgentCommandPreview,
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name='operation_audits',
    )
    source_evidence = models.ForeignKey(
        SourceEvidence,
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name='operation_audits',
    )
    openid = models.CharField(max_length=255)
    operation = models.CharField(max_length=64)
    execution_surface = models.CharField(max_length=16)
    status = models.CharField(max_length=16)
    operator_id = models.CharField(max_length=255, blank=True, default='')
    operator_name = models.CharField(max_length=255, blank=True, default='')
    operator_role = models.CharField(max_length=64, blank=True, default='')
    ai_session_id = models.CharField(max_length=255, blank=True, default='')
    payload_hash = models.CharField(max_length=64, blank=True, default='')
    result = models.JSONField(default=dict)
    failure_reason = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    approved_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = 'operationaudit'
        ordering = ['-created_at', '-id']
        indexes = [
            models.Index(fields=['openid', 'operation', 'created_at']),
            models.Index(fields=['openid', 'execution_surface', 'status']),
        ]


class AsnSerialRecord(models.Model):
    EXPECTED = 'EXPECTED'
    ACCEPTED = 'ACCEPTED'
    UNEXPECTED = 'UNEXPECTED'
    DUPLICATE = 'DUPLICATE'
    WRONG_SKU = 'WRONG_SKU'
    DAMAGED = 'DAMAGED'
    REJECTED = 'REJECTED'
    UNVERIFIED = 'UNVERIFIED'

    STATUS_CHOICES = (
        (EXPECTED, 'Expected'),
        (ACCEPTED, 'Accepted'),
        (UNEXPECTED, 'Unexpected'),
        (DUPLICATE, 'Duplicate'),
        (WRONG_SKU, 'Wrong SKU'),
        (DAMAGED, 'Damaged'),
        (REJECTED, 'Rejected'),
        (UNVERIFIED, 'Scanned without Pack List'),
    )

    openid = models.CharField(max_length=255)
    asn_code = models.CharField(max_length=255)
    goods_code = models.CharField(max_length=255)
    expected_goods_code = models.CharField(max_length=255, blank=True, default='')
    scanned_goods_code = models.CharField(max_length=255, blank=True, default='')
    serial_number = models.CharField(max_length=255)
    double_scan_sn = models.CharField(max_length=255, blank=True, default='')
    inbound_po = models.CharField(max_length=255, blank=True, default='')
    inbound_date = models.DateField(blank=True, null=True)
    source_location = models.CharField(max_length=255, blank=True, default='')
    shipout_ref = models.CharField(max_length=255, blank=True, default='')
    source_row = models.PositiveIntegerField(default=0)
    import_batch = models.ForeignKey(
        PackListImportBatch,
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name='serial_records',
    )
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default=EXPECTED)
    is_expected = models.BooleanField(default=True)
    is_received = models.BooleanField(default=False)
    scan_count = models.PositiveIntegerField(default=0)
    damaged = models.BooleanField(default=False)
    note = models.TextField(blank=True, default='')
    evidence_url = models.CharField(max_length=1000, blank=True, default='')
    exception_resolved = models.BooleanField(default=False)
    exception_resolution_action = models.CharField(max_length=64, blank=True, default='')
    exception_resolution_note = models.TextField(blank=True, default='')
    exception_resolution_location = models.CharField(max_length=255, blank=True, default='')
    exception_resolved_by = models.CharField(max_length=255, blank=True, default='')
    exception_resolved_at = models.DateTimeField(blank=True, null=True)
    exception_moved = models.BooleanField(default=False)
    exception_move_bin = models.CharField(max_length=255, blank=True, default='')
    exception_moved_at = models.DateTimeField(blank=True, null=True)
    expected_by = models.CharField(max_length=255, blank=True, default='')
    received_by = models.CharField(max_length=255, blank=True, default='')
    expected_at = models.DateTimeField(blank=True, null=True)
    received_at = models.DateTimeField(blank=True, null=True)
    pack_list = models.ForeignKey(
        PackListDocument,
        related_name='serial_records',
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
    )
    create_time = models.DateTimeField(auto_now_add=True)
    update_time = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'asnserialrecord'
        ordering = ['goods_code', 'serial_number']
        indexes = [
            models.Index(fields=['openid', 'asn_code']),
            models.Index(fields=['openid', 'serial_number']),
            models.Index(fields=['openid', 'status']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['openid', 'asn_code', 'serial_number'],
                name='asnserial_openid_asn_sn_uniq'
            )
        ]


class ExceptionQuantityMovement(models.Model):
    openid = models.CharField(max_length=255)
    asn_code = models.CharField(max_length=255)
    goods_code = models.CharField(max_length=255)
    quantity = models.PositiveIntegerField()
    action = models.CharField(max_length=64)
    bin_name = models.CharField(max_length=255)
    operator = models.CharField(max_length=255, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'exceptionquantitymovement'
        ordering = ['-created_at', '-id']
        indexes = [
            models.Index(fields=['openid', 'asn_code', 'goods_code']),
        ]


# These values are stored in the existing resolution field so old records remain
# readable while the UI can distinguish approval from hold or rejection.
LEGACY_ACCEPT_EXCEPTION = 'ACCEPT_EXCEPTION'
ACCEPT_FOR_PUTAWAY = 'ACCEPT_FOR_PUTAWAY'
HOLD_QUARANTINE = 'HOLD_QUARANTINE'
REPAIR_REWORK = 'REPAIR_REWORK'
REJECT_RETURN = 'REJECT_RETURN'

PUTAWAY_APPROVED_RESOLUTIONS = frozenset({
    '',
    LEGACY_ACCEPT_EXCEPTION,
    ACCEPT_FOR_PUTAWAY,
})
NON_PUTAWAY_RESOLUTIONS = frozenset({
    HOLD_QUARANTINE,
    REPAIR_REWORK,
    REJECT_RETURN,
})


def resolution_allows_putaway(action):
    return action in PUTAWAY_APPROVED_RESOLUTIONS
