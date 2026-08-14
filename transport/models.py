from django.db import models


class TransportOrder(models.Model):
    INBOUND = 'INBOUND'
    OUTBOUND = 'OUTBOUND'

    DIRECTION_CHOICES = (
        (INBOUND, 'Inbound'),
        (OUTBOUND, 'Outbound'),
    )

    REQUESTED = 'REQUESTED'
    SCHEDULED = 'SCHEDULED'
    DRIVER_ASSIGNED = 'DRIVER_ASSIGNED'
    IN_TRANSIT = 'IN_TRANSIT'
    ARRIVED = 'ARRIVED'
    COMPLETED = 'COMPLETED'
    CANCELLED = 'CANCELLED'

    STATUS_CHOICES = (
        (REQUESTED, 'Requested'),
        (SCHEDULED, 'Scheduled'),
        (DRIVER_ASSIGNED, 'Driver assigned'),
        (IN_TRANSIT, 'In transit'),
        (ARRIVED, 'Arrived'),
        (COMPLETED, 'Completed'),
        (CANCELLED, 'Cancelled'),
    )

    openid = models.CharField(max_length=255)
    transport_no = models.CharField(max_length=255)
    direction = models.CharField(max_length=16, choices=DIRECTION_CHOICES)
    reference_type = models.CharField(max_length=32, blank=True, default='')
    reference_no = models.CharField(max_length=255, blank=True, default='')
    customer = models.CharField(max_length=255, blank=True, default='')
    pickup_location = models.CharField(max_length=1000, blank=True, default='')
    delivery_location = models.CharField(max_length=1000, blank=True, default='')
    carrier = models.CharField(max_length=255, blank=True, default='')
    truck_plate = models.CharField(max_length=64, blank=True, default='')
    driver_name = models.CharField(max_length=255, blank=True, default='')
    logistics_coordinator = models.CharField(max_length=255, blank=True, default='')
    eta = models.DateTimeField(blank=True, null=True)
    appointment_at = models.DateTimeField(blank=True, null=True)
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default=REQUESTED)
    note = models.TextField(blank=True, default='')
    pod_reference = models.CharField(max_length=255, blank=True, default='')
    pod_note = models.TextField(blank=True, default='')
    created_by = models.CharField(max_length=255, blank=True, default='')
    completed_by = models.CharField(max_length=255, blank=True, default='')
    completed_at = models.DateTimeField(blank=True, null=True)
    create_time = models.DateTimeField(auto_now_add=True)
    update_time = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'transportorder'
        ordering = ['-id']
        constraints = [
            models.UniqueConstraint(
                fields=['openid', 'transport_no'],
                name='transport_openid_no_uniq',
            ),
        ]
        indexes = [
            models.Index(fields=['openid', 'status']),
            models.Index(fields=['openid', 'reference_type', 'reference_no']),
            models.Index(fields=['openid', 'driver_name']),
        ]
