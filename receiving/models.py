from django.db import models
from django.db.models import Q


class ReceivingRecord(models.Model):
    RECEIVING = 'RECEIVING'
    QC_PENDING = 'QC_PENDING'
    QC_EXCEPTION = 'QC_EXCEPTION'
    PUTAWAY_PENDING = 'PUTAWAY_PENDING'
    PUTAWAY_COMPLETE = 'PUTAWAY_COMPLETE'
    CLOSED = 'CLOSED'
    CANCELLED = 'CANCELLED'

    STATUS_CHOICES = (
        (RECEIVING, 'Receiving'),
        (QC_PENDING, 'QC pending'),
        (QC_EXCEPTION, 'QC exception'),
        (PUTAWAY_PENDING, 'Putaway pending'),
        (PUTAWAY_COMPLETE, 'Putaway complete'),
        (CLOSED, 'Closed'),
        (CANCELLED, 'Cancelled'),
    )

    NO_ASN = 'AWAITING_ASN'
    PENDING = 'PENDING'
    MATCHED = 'MATCHED'
    EXCEPTION = 'EXCEPTION'
    RESOLVED = 'RESOLVED'
    DISPUTED = 'DISPUTED'

    RECONCILIATION_CHOICES = (
        (NO_ASN, 'Awaiting customer ASN'),
        (PENDING, 'Reconciliation pending'),
        (MATCHED, 'Matched'),
        (EXCEPTION, 'Reconciliation exception'),
        (RESOLVED, 'Variance resolved'),
        (DISPUTED, 'Customer dispute'),
    )

    openid = models.CharField(max_length=255)
    receipt_no = models.CharField(max_length=255)
    customer = models.CharField(max_length=255)
    source_reference = models.CharField(max_length=255, blank=True, default='')
    container_tracking = models.CharField(max_length=255, blank=True, default='')
    received_at = models.DateTimeField()
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default=RECEIVING)
    reconciliation_status = models.CharField(
        max_length=32,
        choices=RECONCILIATION_CHOICES,
        default=NO_ASN,
    )
    linked_asn_code = models.CharField(max_length=255, blank=True, default='')
    source_type = models.CharField(max_length=32, default='OPERATOR')
    source_hash = models.CharField(max_length=64, blank=True, default='')
    exception_note = models.TextField(blank=True, default='')
    resolution_action = models.CharField(max_length=64, blank=True, default='')
    resolution_note = models.TextField(blank=True, default='')
    created_by = models.CharField(max_length=255, blank=True, default='')
    qc_by = models.CharField(max_length=255, blank=True, default='')
    putaway_by = models.CharField(max_length=255, blank=True, default='')
    closed_by = models.CharField(max_length=255, blank=True, default='')
    closed_at = models.DateTimeField(blank=True, null=True)
    metadata = models.JSONField(default=dict)
    create_time = models.DateTimeField(auto_now_add=True)
    update_time = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'receivingrecord'
        ordering = ['-id']
        constraints = [
            models.UniqueConstraint(
                fields=['openid', 'receipt_no'],
                name='receiving_openid_receipt_no_uniq',
            ),
        ]
        indexes = [
            models.Index(fields=['openid', 'status']),
            models.Index(fields=['openid', 'reconciliation_status']),
            models.Index(fields=['openid', 'linked_asn_code']),
        ]


class ReceivingDetail(models.Model):
    receipt = models.ForeignKey(
        ReceivingRecord,
        related_name='details',
        on_delete=models.CASCADE,
    )
    openid = models.CharField(max_length=255)
    goods_code = models.CharField(max_length=255)
    customer_goods_code = models.CharField(max_length=255, blank=True, default='')
    goods_desc = models.CharField(max_length=1000, blank=True, default='')
    expected_qty = models.PositiveIntegerField(default=0)
    actual_qty = models.PositiveIntegerField(default=0)
    accepted_qty = models.PositiveIntegerField(default=0)
    damage_qty = models.PositiveIntegerField(default=0)
    hold_qty = models.PositiveIntegerField(default=0)
    rejected_qty = models.PositiveIntegerField(default=0)
    putaway_qty = models.PositiveIntegerField(default=0)
    bin_name = models.CharField(max_length=255, blank=True, default='')
    exception_note = models.TextField(blank=True, default='')
    resolution_action = models.CharField(max_length=64, blank=True, default='')
    resolution_note = models.TextField(blank=True, default='')
    create_time = models.DateTimeField(auto_now_add=True)
    update_time = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'receivingdetail'
        ordering = ['id']
        constraints = [
            models.UniqueConstraint(
                fields=['receipt', 'goods_code'],
                name='receiving_receipt_goods_uniq',
            ),
        ]
        indexes = [
            models.Index(fields=['openid', 'goods_code']),
            models.Index(fields=['receipt', 'goods_code']),
        ]


class ReceivingSerial(models.Model):
    ACCEPTED = 'ACCEPTED'
    DAMAGED = 'DAMAGED'
    WRONG_SKU = 'WRONG_SKU'
    DUPLICATE = 'DUPLICATE'
    UNEXPECTED = 'UNEXPECTED'
    HOLD = 'HOLD'
    REJECTED = 'REJECTED'

    STATUS_CHOICES = (
        (ACCEPTED, 'Accepted'),
        (DAMAGED, 'Damaged'),
        (WRONG_SKU, 'Wrong SKU'),
        (DUPLICATE, 'Duplicate'),
        (UNEXPECTED, 'Unexpected'),
        (HOLD, 'Hold'),
        (REJECTED, 'Rejected'),
    )

    detail = models.ForeignKey(
        ReceivingDetail,
        related_name='serials',
        on_delete=models.CASCADE,
    )
    receipt = models.ForeignKey(
        ReceivingRecord,
        related_name='serials',
        on_delete=models.CASCADE,
    )
    openid = models.CharField(max_length=255)
    goods_code = models.CharField(max_length=255)
    serial_number = models.CharField(max_length=255)
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default=ACCEPTED)
    scanned_goods_code = models.CharField(max_length=255, blank=True, default='')
    note = models.TextField(blank=True, default='')
    evidence_url = models.CharField(max_length=1000, blank=True, default='')
    scanned_by = models.CharField(max_length=255, blank=True, default='')
    scanned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'receivingserial'
        ordering = ['goods_code', 'serial_number']
        constraints = [
            models.UniqueConstraint(
                fields=['receipt', 'serial_number'],
                name='receiving_receipt_serial_uniq',
            ),
        ]
        indexes = [
            models.Index(fields=['openid', 'serial_number']),
            models.Index(fields=['receipt', 'goods_code']),
        ]


class ReceivingPutaway(models.Model):
    receipt = models.ForeignKey(
        ReceivingRecord,
        related_name='putaways',
        on_delete=models.PROTECT,
    )
    detail = models.ForeignKey(
        ReceivingDetail,
        related_name='putaways',
        on_delete=models.PROTECT,
    )
    openid = models.CharField(max_length=255)
    goods_code = models.CharField(max_length=255)
    bin_name = models.CharField(max_length=255)
    quantity = models.PositiveIntegerField()
    driver_name = models.CharField(max_length=255, blank=True, default='')
    operator = models.CharField(max_length=255, blank=True, default='')
    idempotency_key = models.CharField(max_length=255, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'receivingputaway'
        ordering = ['-created_at', '-id']
        constraints = [
            models.UniqueConstraint(
                fields=['openid', 'idempotency_key'],
                condition=~Q(idempotency_key=''),
                name='receiving_putaway_idempotency_uniq',
            ),
        ]
        indexes = [
            models.Index(fields=['openid', 'receipt']),
            models.Index(fields=['openid', 'bin_name']),
        ]


class ReceivingReconciliationEvent(models.Model):
    receipt = models.ForeignKey(
        ReceivingRecord,
        related_name='reconciliation_events',
        on_delete=models.CASCADE,
    )
    openid = models.CharField(max_length=255)
    event_type = models.CharField(max_length=64)
    operator = models.CharField(max_length=255, blank=True, default='')
    note = models.TextField(blank=True, default='')
    payload = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'receivingreconciliationevent'
        ordering = ['-created_at', '-id']
        indexes = [
            models.Index(fields=['openid', 'receipt', 'event_type']),
        ]
