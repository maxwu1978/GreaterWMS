from django.db import models

class DnListModel(models.Model):
    SKU_QTY = 'SKU_QTY'
    SN = 'SN'
    PICKING_MODE_CHOICES = (
        (SKU_QTY, 'SKU and quantity'),
        (SN, 'Serial number'),
    )

    dn_code = models.CharField(max_length=255, verbose_name="DN Code")
    dn_status = models.BigIntegerField(default=1, verbose_name="DN Status")
    total_weight = models.FloatField(default=0, verbose_name="Total Weight")
    total_volume = models.FloatField(default=0, verbose_name="Total Volume")
    total_cost = models.FloatField(default=0, verbose_name="Total Cost")
    customer = models.CharField(max_length=255, verbose_name="DN Customer")
    creater = models.CharField(max_length=255, verbose_name="Who Created")
    bar_code = models.CharField(max_length=255, verbose_name="Bar Code")
    back_order_label = models.BooleanField(default=False, verbose_name='Back Order Label')
    openid = models.CharField(max_length=255, verbose_name="Openid")
    transportation_fee = models.JSONField(default=dict, verbose_name="Transportation Fee")
    picking_mode = models.CharField(
        max_length=16,
        choices=PICKING_MODE_CHOICES,
        default=SKU_QTY,
        verbose_name="Picking Mode",
    )
    transport_required = models.BooleanField(default=False, verbose_name="Transport Required")
    transport_order_no = models.CharField(max_length=255, blank=True, default='', verbose_name="Transport Order")
    ship_to = models.CharField(max_length=1000, blank=True, default='', verbose_name="Ship To")
    cancellation_note = models.TextField(default='', blank=True, verbose_name="Cancellation Note")
    canceled_by = models.CharField(default='', max_length=255, blank=True, verbose_name="Canceled By")
    canceled_at = models.DateTimeField(null=True, blank=True, verbose_name="Canceled At")
    is_delete = models.BooleanField(default=False, verbose_name='Delete Label')
    create_time = models.DateTimeField(auto_now_add=True, verbose_name="Create Time")
    update_time = models.DateTimeField(auto_now=True, blank=True, null=True, verbose_name="Update Time")

    class Meta:
        db_table = 'dnlist'
        verbose_name = 'DN List'
        verbose_name_plural = "DN List"
        ordering = ['-id']

class DnDetailModel(models.Model):
    dn_code = models.CharField(max_length=255, verbose_name="DN Code")
    dn_status = models.BigIntegerField(default=1, verbose_name="DN Status")
    customer = models.CharField(max_length=255, verbose_name="DN Customer")
    goods_code = models.CharField(max_length=255, verbose_name="Goods Code")
    goods_desc = models.CharField(max_length=255, verbose_name="Goods Description")
    goods_qty = models.BigIntegerField(default=0, verbose_name="Goods QTY")
    pick_qty = models.BigIntegerField(default=0, verbose_name="Goods Pre Pick QTY")
    picked_qty = models.BigIntegerField(default=0, verbose_name="Goods Picked QTY")
    intransit_qty = models.BigIntegerField(default=0, verbose_name="Intransit QTY")
    delivery_actual_qty = models.BigIntegerField(default=0, verbose_name="Delivery Actual QTY")
    delivery_shortage_qty = models.BigIntegerField(default=0, verbose_name="Delivery Shortage QTY")
    delivery_more_qty = models.BigIntegerField(default=0, verbose_name="Delivery More QTY")
    delivery_damage_qty = models.BigIntegerField(default=0, verbose_name="Delivery More QTY")
    cancelled_qty = models.BigIntegerField(default=0, verbose_name="Cancelled QTY")
    returned_qty = models.BigIntegerField(default=0, verbose_name="Returned QTY")
    delivery_note = models.TextField(default='', blank=True, verbose_name="Delivery Exception Note")
    requested_serials = models.JSONField(default=list, verbose_name="Requested Serial Numbers")
    picked_serials = models.JSONField(default=list, verbose_name="Picked Serial Numbers")
    shipped_serials = models.JSONField(default=list, verbose_name="Shipped Serial Numbers")
    goods_weight = models.FloatField(default=0, verbose_name="Goods Weight")
    goods_volume = models.FloatField(default=0, verbose_name="Goods Volume")
    goods_cost = models.FloatField(default=0, verbose_name="Goods Cost")
    creater = models.CharField(max_length=255, verbose_name="Who Created")
    back_order_label = models.BooleanField(default=False, verbose_name='Back Order Label')
    openid = models.CharField(max_length=255, verbose_name="Openid")
    is_delete = models.BooleanField(default=False, verbose_name='Delete Label')
    create_time = models.DateTimeField(auto_now_add=True, verbose_name="Create Time")
    update_time = models.DateTimeField(auto_now=True, blank=True, null=True, verbose_name="Update Time")

    class Meta:
        db_table = 'dndetail'
        verbose_name = 'DN Detail'
        verbose_name_plural = "DN Detail"
        ordering = ['-id']

class PickingListModel(models.Model):
    dn_code = models.CharField(max_length=255, verbose_name="DN Code")
    bin_name = models.CharField(max_length=255, verbose_name="Bin Name")
    goods_code = models.CharField(max_length=255, verbose_name="Goods Code")
    picking_status = models.SmallIntegerField(default=0, verbose_name="Picking Status")
    pick_qty = models.BigIntegerField(default=0, verbose_name="Goods Pre Pick QTY")
    picked_qty = models.BigIntegerField(default=0, verbose_name="Picked QTY")
    creater = models.CharField(max_length=255, verbose_name="Who Created")
    t_code = models.CharField(max_length=255, verbose_name="Transaction Code")
    openid = models.CharField(max_length=255, verbose_name="Openid")
    create_time = models.DateTimeField(auto_now_add=True, verbose_name="Create Time")
    update_time = models.DateTimeField(auto_now=True, blank=True, null=True, verbose_name="Update Time")

    class Meta:
        db_table = 'pickinglist'
        verbose_name = 'Picking List'
        verbose_name_plural = "Picking List"
        ordering = ['-id']


class DnSerialAllocation(models.Model):
    REQUESTED = 'REQUESTED'
    PICKED = 'PICKED'
    IN_TRANSIT = 'IN_TRANSIT'
    SHIPPED = 'SHIPPED'
    RELEASED = 'RELEASED'
    RETURNED = 'RETURNED'

    STATUS_CHOICES = (
        (REQUESTED, 'Requested'),
        (PICKED, 'Picked'),
        (IN_TRANSIT, 'In transit'),
        (SHIPPED, 'Shipped'),
        (RELEASED, 'Released'),
        (RETURNED, 'Returned'),
    )

    openid = models.CharField(max_length=255)
    dn_code = models.CharField(max_length=255)
    goods_code = models.CharField(max_length=255)
    serial_number = models.CharField(max_length=255)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=REQUESTED)
    created_by = models.CharField(max_length=255, blank=True, default='')
    create_time = models.DateTimeField(auto_now_add=True)
    update_time = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'dnserialallocation'
        ordering = ['goods_code', 'serial_number']
        constraints = [
            models.UniqueConstraint(
                fields=['openid', 'dn_code', 'serial_number'],
                name='dn_serial_allocation_uniq',
            ),
            models.UniqueConstraint(
                fields=['openid', 'serial_number'],
                condition=models.Q(status__in=['REQUESTED', 'PICKED', 'IN_TRANSIT', 'SHIPPED', 'RELEASED']),
                name='dn_serial_allocation_active_uniq',
            ),
        ]
        indexes = [
            models.Index(fields=['openid', 'serial_number', 'status']),
            models.Index(fields=['openid', 'dn_code', 'goods_code']),
        ]
