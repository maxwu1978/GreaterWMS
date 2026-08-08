from django.db import models


class StagingAssignment(models.Model):
    INBOUND = 'INBOUND'
    OUTBOUND = 'OUTBOUND'
    RESERVED = 'RESERVED'
    ACTIVE = 'ACTIVE'
    RELEASED = 'RELEASED'

    flow = models.CharField(max_length=12, choices=[(INBOUND, 'Inbound'), (OUTBOUND, 'Outbound')])
    reference_code = models.CharField(max_length=255, verbose_name='ASN or DN Code')
    goods_code = models.CharField(max_length=255, default='', blank=True)
    quantity = models.BigIntegerField(default=0)
    bin_name = models.CharField(max_length=255)
    status = models.CharField(
        max_length=12,
        default=RESERVED,
        choices=[
            (RESERVED, 'Reserved'),
            (ACTIVE, 'Occupied'),
            (RELEASED, 'Released'),
        ],
    )
    creater = models.CharField(max_length=255, default='', blank=True)
    openid = models.CharField(max_length=255)
    create_time = models.DateTimeField(auto_now_add=True)
    release_time = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'stagingassignment'
        ordering = ['-id']
        indexes = [
            models.Index(fields=['openid', 'bin_name', 'status']),
            models.Index(fields=['openid', 'flow', 'reference_code', 'status']),
        ]
