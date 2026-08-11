from django.db import models


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
        ('UPLOAD', 'Uploaded file'),
        ('EMAIL', 'Email attachment'),
        ('GOOGLE_DRIVE', 'Google Drive'),
        ('MANUAL', 'Manual entry'),
    )

    openid = models.CharField(max_length=255)
    asn_code = models.CharField(max_length=255)
    version = models.PositiveIntegerField(default=1)
    source_type = models.CharField(max_length=32, choices=SOURCE_TYPES, default='UPLOAD')
    source_file = models.CharField(max_length=255, blank=True, default='')
    source_sha256 = models.CharField(max_length=64, blank=True, default='')
    source_url = models.CharField(max_length=1000, blank=True, default='')
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default=PENDING)
    has_serials = models.BooleanField(default=False)
    package_qty = models.PositiveIntegerField(default=0)
    note = models.TextField(blank=True, default='')
    raw_payload = models.JSONField(default=dict, blank=True)
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
            models.Index(fields=['openid', 'asn_code', 'source_sha256']),
            models.Index(fields=['openid', 'source_type']),
        ]


class PackListLine(models.Model):
    pack_list = models.ForeignKey(PackListDocument, related_name='lines', on_delete=models.CASCADE)
    openid = models.CharField(max_length=255)
    asn_code = models.CharField(max_length=255)
    goods_code = models.CharField(max_length=255)
    customer_goods_code = models.CharField(max_length=255, blank=True, default='')
    goods_qty = models.PositiveIntegerField(default=0)
    goods_desc = models.CharField(max_length=1000, blank=True, default='')
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
    source_file = models.CharField(max_length=255, blank=True, default='')
    source_row = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default=EXPECTED)
    is_expected = models.BooleanField(default=True)
    is_received = models.BooleanField(default=False)
    scan_count = models.PositiveIntegerField(default=0)
    damaged = models.BooleanField(default=False)
    note = models.TextField(blank=True, default='')
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
