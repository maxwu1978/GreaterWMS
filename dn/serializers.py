from rest_framework import serializers
from .models import DnListModel, DnDetailModel, PickingListModel
from utils import datasolve
class SannerDnDetailGetSerializer(serializers.ModelSerializer):
    dn_code = serializers.CharField(read_only=True, required=False)
    dn_status = serializers.IntegerField(read_only=True, required=False)
    customer = serializers.CharField(read_only=True, required=False)
    goods_code = serializers.CharField(read_only=True, required=False)
    goods_qty = serializers.IntegerField(read_only=True, required=False)
    pick_qty = serializers.IntegerField(read_only=True, required=False)
    picked_qty = serializers.IntegerField(read_only=True, required=False)
    intransit_qty = serializers.IntegerField(read_only=True, required=False)
    delivery_actual_qty = serializers.IntegerField(read_only=True, required=False)
    delivery_shortage_qty = serializers.IntegerField(read_only=True, required=False)
    delivery_more_qty = serializers.IntegerField(read_only=True, required=False)
    delivery_damage_qty = serializers.IntegerField(read_only=True, required=False)
    delivery_note = serializers.CharField(read_only=True, required=False)
    goods_weight = serializers.FloatField(read_only=True, required=False)
    goods_volume = serializers.FloatField(read_only=True, required=False)
    goods_cost = serializers.FloatField(read_only=True, required=False)
    creater = serializers.CharField(read_only=True, required=False)
    create_time = serializers.DateTimeField(read_only=True, format='%Y-%m-%d %H:%M:%S')
    update_time = serializers.DateTimeField(read_only=True, format='%Y-%m-%d %H:%M:%S')
    back_order_label = serializers.BooleanField(read_only=True, required=False)
    class Meta:
        model = DnDetailModel
        exclude = ['openid', 'is_delete', ]
        read_only_fields = ['id', 'openid']


class DNListGetSerializer(serializers.ModelSerializer):
    dn_code = serializers.CharField(read_only=True, required=False)
    dn_status = serializers.IntegerField(read_only=True, required=False)
    customer = serializers.CharField(read_only=True, required=False)
    creater = serializers.CharField(read_only=True, required=False)
    bar_code = serializers.CharField(read_only=True, required=False)
    create_time = serializers.DateTimeField(read_only=True, format='%Y-%m-%d %H:%M:%S')
    update_time = serializers.DateTimeField(read_only=True, format='%Y-%m-%d %H:%M:%S')
    cancellation_note = serializers.CharField(read_only=True, required=False)
    canceled_by = serializers.CharField(read_only=True, required=False)
    canceled_at = serializers.DateTimeField(read_only=True, format='%Y-%m-%d %H:%M:%S', required=False)
    staging_bin = serializers.SerializerMethodField()
    staging_status = serializers.SerializerMethodField()
    dispatch_driver = serializers.SerializerMethodField()
    sku_summary = serializers.SerializerMethodField()
    delivery_exception = serializers.SerializerMethodField()

    def get_staging_bin(self, obj):
        from staging.models import StagingAssignment
        from driver.models import DispatchListModel
        assignment = StagingAssignment.objects.filter(
            openid=obj.openid,
            flow=StagingAssignment.OUTBOUND,
            reference_code=obj.dn_code,
            status=StagingAssignment.ACTIVE,
        ).first()
        if assignment:
            return assignment.bin_name
        dispatch = DispatchListModel.objects.filter(
            openid=obj.openid,
            dn_code=obj.dn_code,
        ).order_by('-id').first()
        return dispatch.staging_bin if dispatch else ''

    def get_dispatch_driver(self, obj):
        from driver.models import DispatchListModel
        dispatch = DispatchListModel.objects.filter(
            openid=obj.openid,
            dn_code=obj.dn_code,
        ).order_by('-id').first()
        return dispatch.driver_name if dispatch else ''

    def get_staging_status(self, obj):
        from staging.models import StagingAssignment
        assignment = StagingAssignment.objects.filter(
            openid=obj.openid,
            flow=StagingAssignment.OUTBOUND,
            reference_code=obj.dn_code,
        ).order_by('-id').first()
        if assignment and assignment.status in (StagingAssignment.RESERVED, StagingAssignment.ACTIVE):
            return 'Occupied' if assignment.status == StagingAssignment.ACTIVE else 'Reserved'
        if obj.dn_status >= 6:
            return 'Released'
        return 'Not assigned'

    def get_sku_summary(self, obj):
        details = DnDetailModel.objects.filter(
            openid=obj.openid,
            dn_code=obj.dn_code,
            is_delete=False,
        ).order_by('id')
        return '; '.join('%s x %s' % (item.goods_code, item.goods_qty) for item in details)

    def get_delivery_exception(self, obj):
        details = DnDetailModel.objects.filter(
            openid=obj.openid,
            dn_code=obj.dn_code,
            is_delete=False,
        )
        exceptions = []
        if obj.dn_status == 7:
            return 'Cancelled'
        if details.filter(delivery_shortage_qty__gt=0).exists():
            exceptions.append('Shortage')
        if details.filter(delivery_more_qty__gt=0).exists():
            exceptions.append('More Qty')
        if details.filter(delivery_damage_qty__gt=0).exists():
            exceptions.append('Damage')
        return ', '.join(exceptions)
    class Meta:
        model = DnListModel
        exclude = ['openid', 'is_delete', ]
        read_only_fields = ['id', ]

class DNListPostSerializer(serializers.ModelSerializer):
    openid = serializers.CharField(read_only=False, required=False, validators=[datasolve.openid_validate])
    dn_code = serializers.CharField(read_only=False,  required=True, validators=[datasolve.dn_data_validate])
    customer = serializers.CharField(read_only=False, required=False)
    bar_code = serializers.CharField(read_only=False, required=True)
    creater = serializers.CharField(read_only=False, required=True, validators=[datasolve.data_validate])
    class Meta:
        model = DnListModel
        exclude = ['is_delete', ]
        read_only_fields = [
            'id', 'create_time', 'update_time',
            'cancellation_note', 'canceled_by', 'canceled_at',
        ]

class DNListPartialUpdateSerializer(serializers.ModelSerializer):
    dn_code = serializers.CharField(read_only=False,  required=True, validators=[datasolve.dn_data_validate])

    class Meta:
        model = DnListModel
        exclude = ['is_delete', ]
        read_only_fields = [
            'id', 'create_time', 'update_time',
            'cancellation_note', 'canceled_by', 'canceled_at',
        ]

class DNListUpdateSerializer(serializers.ModelSerializer):
    dn_code = serializers.CharField(read_only=False,  required=True, validators=[datasolve.dn_data_validate])

    class Meta:
        model = DnListModel
        exclude = ['is_delete', ]
        read_only_fields = [
            'id', 'create_time', 'update_time',
            'cancellation_note', 'canceled_by', 'canceled_at',
        ]

class DNDetailGetSerializer(serializers.ModelSerializer):
    dn_code = serializers.CharField(read_only=True, required=False)
    dn_status = serializers.IntegerField(read_only=True, required=False)
    customer = serializers.CharField(read_only=True, required=False)
    goods_code = serializers.CharField(read_only=True, required=False)
    goods_desc = serializers.CharField(read_only=True, required=False)
    goods_qty = serializers.IntegerField(read_only=True, required=False)
    pick_qty = serializers.IntegerField(read_only=True, required=False)
    picked_qty = serializers.IntegerField(read_only=True, required=False)
    intransit_qty = serializers.IntegerField(read_only=True, required=False)
    delivery_actual_qty = serializers.IntegerField(read_only=True, required=False)
    delivery_shortage_qty = serializers.IntegerField(read_only=True, required=False)
    delivery_more_qty = serializers.IntegerField(read_only=True, required=False)
    delivery_damage_qty = serializers.IntegerField(read_only=True, required=False)
    delivery_note = serializers.CharField(read_only=True, required=False)
    goods_weight = serializers.FloatField(read_only=True, required=False)
    goods_volume = serializers.FloatField(read_only=True, required=False)
    goods_cost = serializers.FloatField(read_only=True, required=False)
    creater = serializers.CharField(read_only=True, required=False)
    create_time = serializers.DateTimeField(read_only=True, format='%Y-%m-%d %H:%M:%S')
    update_time = serializers.DateTimeField(read_only=True, format='%Y-%m-%d %H:%M:%S')
    back_order_label = serializers.BooleanField(read_only=True, required=False)
    class Meta:
        model = DnDetailModel
        exclude = ['openid', 'is_delete', ]
        read_only_fields = ['id', 'openid']

class DNDetailPostSerializer(serializers.ModelSerializer):
    openid = serializers.CharField(read_only=False, required=False, validators=[datasolve.openid_validate])
    dn_code = serializers.CharField(read_only=False,  required=True, validators=[datasolve.data_validate])
    customer = serializers.CharField(read_only=False,  required=True, validators=[datasolve.data_validate])
    goods_code = serializers.CharField(read_only=False, required=True, validators=[datasolve.data_validate])
    goods_desc = serializers.CharField(read_only=False, required=False)
    goods_qty = serializers.IntegerField(read_only=False, required=True, validators=[datasolve.qty_0_data_validate])
    creater = serializers.CharField(read_only=False, required=True, validators=[datasolve.data_validate])
    class Meta:
        model = DnDetailModel
        exclude = ['is_delete', ]
        read_only_fields = ['id', 'create_time', 'update_time', ]

class DNDetailUpdateSerializer(serializers.ModelSerializer):
    dn_code = serializers.CharField(read_only=False, required=True, validators=[datasolve.data_validate])
    customer = serializers.CharField(read_only=False,  required=True, validators=[datasolve.data_validate])
    goods_code = serializers.CharField(read_only=False, required=True, validators=[datasolve.data_validate])
    goods_desc = serializers.CharField(read_only=False, required=False)
    goods_qty = serializers.IntegerField(read_only=False, required=True, validators=[datasolve.qty_0_data_validate])
    creater = serializers.CharField(read_only=False, required=True, validators=[datasolve.data_validate])
    class Meta:
        model = DnDetailModel
        exclude = ['openid', 'is_delete', ]
        read_only_fields = ['id', 'create_time', 'update_time', ]

class DNDetailPartialUpdateSerializer(serializers.ModelSerializer):
    dn_code = serializers.CharField(read_only=False, required=False, validators=[datasolve.data_validate])
    customer = serializers.CharField(read_only=False,  required=False, validators=[datasolve.data_validate])
    goods_code = serializers.CharField(read_only=False, required=False, validators=[datasolve.data_validate])
    goods_desc = serializers.CharField(read_only=False, required=False)
    goods_qty = serializers.IntegerField(read_only=False, required=False, validators=[datasolve.qty_0_data_validate])
    creater = serializers.CharField(read_only=False, required=False, validators=[datasolve.data_validate])
    class Meta:
        model = DnDetailModel
        exclude = ['openid', 'is_delete', ]
        read_only_fields = ['id', 'create_time', 'update_time', ]

class DNPickingListGetSerializer(serializers.ModelSerializer):
    dn_code = serializers.CharField(read_only=True, required=False)
    bin_name = serializers.CharField(read_only=True, required=False)
    goods_code = serializers.CharField(read_only=True, required=False)
    picking_status = serializers.IntegerField(read_only=True, required=False)
    pick_qty = serializers.IntegerField(read_only=True, required=False)
    picked_qty = serializers.IntegerField(read_only=True, required=False)
    creater = serializers.CharField(read_only=True, required=False)
    t_code = serializers.CharField(read_only=True, required=False)
    create_time = serializers.DateTimeField(read_only=True, format='%Y-%m-%d %H:%M:%S')
    update_time = serializers.DateTimeField(read_only=True, format='%Y-%m-%d %H:%M:%S')
    class Meta:
        model = PickingListModel
        exclude = ['openid', ]
        read_only_fields = ['id', ]

class DNPickingCheckGetSerializer(serializers.ModelSerializer):
    dn_code = serializers.CharField(read_only=True, required=False)
    bin_name = serializers.CharField(read_only=True, required=False)
    goods_code = serializers.CharField(read_only=True, required=False)
    picking_status = serializers.IntegerField(read_only=False, required=False)
    pick_qty = serializers.IntegerField(read_only=True, required=False)
    picked_qty = serializers.IntegerField(read_only=True, required=False)
    creater = serializers.CharField(read_only=True, required=False)
    create_time = serializers.DateTimeField(read_only=True, format='%Y-%m-%d %H:%M:%S')
    update_time = serializers.DateTimeField(read_only=True, format='%Y-%m-%d %H:%M:%S')
    class Meta:
        model = PickingListModel
        exclude = ['openid', ]
        read_only_fields = ['id', ]

class FileListRenderSerializer(serializers.ModelSerializer):
    dn_code = serializers.CharField(read_only=False, required=False)
    dn_status = serializers.IntegerField(read_only=False, required=False)
    total_weight = serializers.FloatField(read_only=False, required=False)
    total_volume = serializers.FloatField(read_only=False, required=False)
    total_cost = serializers.FloatField(read_only=False, required=False)
    customer = serializers.CharField(read_only=False, required=False)
    creater = serializers.CharField(read_only=False, required=False)
    back_order_label = serializers.BooleanField(read_only=False, required=False)
    create_time = serializers.DateTimeField(read_only=True, format='%Y-%m-%d %H:%M:%S')
    update_time = serializers.DateTimeField(read_only=True, format='%Y-%m-%d %H:%M:%S')

    class Meta:
        model = DnListModel
        ref_name = 'DNFileListRenderSerializer'
        exclude = ['openid', 'is_delete', ]

class FileDetailRenderSerializer(serializers.ModelSerializer):
    dn_code = serializers.CharField(read_only=False, required=False)
    dn_status = serializers.IntegerField(read_only=False, required=False)
    customer = serializers.CharField(read_only=False, required=False)
    goods_code = serializers.CharField(read_only=False, required=False)
    goods_desc = serializers.CharField(read_only=False, required=False)
    goods_qty = serializers.IntegerField(read_only=False, required=False)
    pick_qty = serializers.IntegerField(read_only=False, required=False)
    picked_qty = serializers.IntegerField(read_only=False, required=False)
    intransit_qty = serializers.IntegerField(read_only=False, required=False)
    delivery_actual_qty = serializers.IntegerField(read_only=False, required=False)
    delivery_shortage_qty = serializers.IntegerField(read_only=False, required=False)
    delivery_more_qty = serializers.IntegerField(read_only=False, required=False)
    delivery_damage_qty = serializers.IntegerField(read_only=False, required=False)
    delivery_note = serializers.CharField(read_only=False, required=False)
    goods_weight = serializers.FloatField(read_only=False, required=False)
    goods_volume = serializers.FloatField(read_only=False, required=False)
    goods_cost = serializers.FloatField(read_only=False, required=False)
    creater = serializers.CharField(read_only=False, required=False)
    create_time = serializers.DateTimeField(read_only=True, format='%Y-%m-%d %H:%M:%S')
    update_time = serializers.DateTimeField(read_only=True, format='%Y-%m-%d %H:%M:%S')
    back_order_label = serializers.BooleanField(read_only=False, required=False)

    class Meta:
        model = DnDetailModel
        ref_name = 'DNFileDetailRenderSerializer'
        exclude = ['openid', 'is_delete', ]
