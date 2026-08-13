from django.db import models
from django.db.models import Q


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
    EXECUTED = 'EXECUTED'

    openid = models.CharField(max_length=255)
    operation = models.CharField(max_length=64)
    resource_id = models.CharField(max_length=255, blank=True, default='')
    asn_code = models.CharField(max_length=255, blank=True, default='')
    payload_hash = models.CharField(max_length=64)
    confirmation_token_hash = models.CharField(max_length=64)
    idempotency_key = models.CharField(max_length=255, blank=True, default='')
    preview_payload = models.JSONField(default=dict)
    result = models.JSONField(blank=True, null=True)
    status = models.CharField(max_length=16, default=PENDING)
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
