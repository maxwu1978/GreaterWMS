from django.db import models


class AsnSerialRecord(models.Model):
    EXPECTED = 'EXPECTED'
    ACCEPTED = 'ACCEPTED'
    UNEXPECTED = 'UNEXPECTED'
    DUPLICATE = 'DUPLICATE'
    WRONG_SKU = 'WRONG_SKU'
    DAMAGED = 'DAMAGED'
    REJECTED = 'REJECTED'

    STATUS_CHOICES = (
        (EXPECTED, 'Expected'),
        (ACCEPTED, 'Accepted'),
        (UNEXPECTED, 'Unexpected'),
        (DUPLICATE, 'Duplicate'),
        (WRONG_SKU, 'Wrong SKU'),
        (DAMAGED, 'Damaged'),
        (REJECTED, 'Rejected'),
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
