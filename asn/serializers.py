from rest_framework import serializers
from .models import AsnListModel, AsnDetailModel
from utils import datasolve

class ASNListGetSerializer(serializers.ModelSerializer):
    asn_code = serializers.CharField(read_only=True, required=False)
    asn_status = serializers.IntegerField(read_only=True, required=False)
    supplier = serializers.CharField(read_only=True, required=False)
    bar_code = serializers.CharField(read_only=True, required=False)
    creater = serializers.CharField(read_only=True, required=False)
    create_time = serializers.DateTimeField(read_only=True, format='%Y-%m-%d %H:%M:%S')
    update_time = serializers.DateTimeField(read_only=True, format='%Y-%m-%d %H:%M:%S')
    staging_bin = serializers.SerializerMethodField()
    staging_bins = serializers.SerializerMethodField()
    planned_qty = serializers.SerializerMethodField()
    actual_qty = serializers.SerializerMethodField()
    exception_qty = serializers.SerializerMethodField()
    sku_count = serializers.SerializerMethodField()
    pack_list_status = serializers.SerializerMethodField()
    pack_list_has_serials = serializers.SerializerMethodField()

    def _get_detail_aggregate(self, obj):
        """Cache the small summary used by the ASN work queue."""
        cache = self.context.setdefault('_asn_detail_aggregate_cache', {})
        cache_key = (obj.openid, obj.asn_code)
        if cache_key not in cache:
            details = AsnDetailModel.objects.filter(
                openid=obj.openid,
                asn_code=obj.asn_code,
                is_delete=False,
            )
            summary = {
                'planned_qty': 0,
                'actual_qty': 0,
                'exception_qty': 0,
                'sku_count': 0,
            }
            for detail in details.only(
                'goods_qty',
                'goods_actual_qty',
                'goods_shortage_qty',
                'goods_more_qty',
                'goods_damage_qty',
            ):
                summary['planned_qty'] += detail.goods_qty or 0
                summary['actual_qty'] += detail.goods_actual_qty or 0
                summary['exception_qty'] += (
                    (detail.goods_shortage_qty or 0)
                    + (detail.goods_more_qty or 0)
                    + (detail.goods_damage_qty or 0)
                )
                summary['sku_count'] += 1
            cache[cache_key] = summary
        return cache[cache_key]

    def _get_pack_list(self, obj):
        cache = self.context.setdefault('_asn_pack_list_cache', {})
        cache_key = (obj.openid, obj.asn_code)
        if cache_key in cache:
            return cache[cache_key]

        from asnserial.models import PackListDocument

        documents = PackListDocument.objects.filter(
            openid=obj.openid,
            asn_code=obj.asn_code,
        )
        document = documents.filter(
            status=PackListDocument.CONFIRMED,
        ).order_by('-version', '-id').first() or documents.filter(
            status=PackListDocument.PENDING,
        ).order_by('-version', '-id').first()
        cache[cache_key] = document
        return document

    def get_planned_qty(self, obj):
        return self._get_detail_aggregate(obj)['planned_qty']

    def get_actual_qty(self, obj):
        return self._get_detail_aggregate(obj)['actual_qty']

    def get_exception_qty(self, obj):
        return self._get_detail_aggregate(obj)['exception_qty']

    def get_sku_count(self, obj):
        return self._get_detail_aggregate(obj)['sku_count']

    def get_pack_list_status(self, obj):
        document = self._get_pack_list(obj)
        return document.status if document else 'NOT_RECEIVED'

    def get_pack_list_has_serials(self, obj):
        document = self._get_pack_list(obj)
        return bool(document and document.has_serials)

    def _get_staging_bins(self, obj):
        from staging.models import StagingAssignment
        return list(StagingAssignment.objects.filter(
            openid=obj.openid,
            flow=StagingAssignment.INBOUND,
            reference_code=obj.asn_code,
            status__in=(StagingAssignment.RESERVED, StagingAssignment.ACTIVE),
        ).order_by('id').values_list('bin_name', flat=True))

    def get_staging_bin(self, obj):
        return ', '.join(self._get_staging_bins(obj))

    def get_staging_bins(self, obj):
        return self._get_staging_bins(obj)
    class Meta:
        model = AsnListModel
        exclude = ['openid', 'is_delete', ]
        read_only_fields = ['id', 'openid', ]

class ASNListPostSerializer(serializers.ModelSerializer):
    openid = serializers.CharField(read_only=False, required=False, validators=[datasolve.openid_validate])
    asn_code = serializers.CharField(read_only=False,  required=True, validators=[datasolve.asn_data_validate])
    supplier = serializers.CharField(read_only=False, required=False)
    bar_code = serializers.CharField(read_only=False, required=True)
    creater = serializers.CharField(read_only=False, required=True, validators=[datasolve.data_validate])
    class Meta:
        model = AsnListModel
        exclude = ['is_delete', ]
        read_only_fields = ['id', 'create_time', 'update_time', ]

class ASNListPartialUpdateSerializer(serializers.ModelSerializer):
    asn_code = serializers.CharField(read_only=False,  required=True, validators=[datasolve.asn_data_validate])

    class Meta:
        model = AsnListModel
        exclude = ['is_delete', ]
        read_only_fields = ['id', 'create_time', 'update_time', ]

class ASNListUpdateSerializer(serializers.ModelSerializer):
    asn_code = serializers.CharField(read_only=False,  required=True, validators=[datasolve.asn_data_validate])

    class Meta:
        model = AsnListModel
        exclude = ['is_delete', ]
        read_only_fields = ['id', 'create_time', 'update_time', ]

class ASNDetailGetSerializer(serializers.ModelSerializer):
    asn_code = serializers.CharField(read_only=True, required=False)
    supplier = serializers.CharField(read_only=True, required=False)
    goods_code = serializers.CharField(read_only=True, required=False)
    goods_desc = serializers.CharField(read_only=True, required=False)
    goods_qty = serializers.IntegerField(read_only=True, required=False)
    goods_actual_qty = serializers.IntegerField(read_only=True, required=False)
    sorted_qty = serializers.IntegerField(read_only=True, required=False)
    goods_shortage_qty = serializers.IntegerField(read_only=True, required=False)
    goods_more_qty = serializers.IntegerField(read_only=True, required=False)
    goods_damage_qty = serializers.IntegerField(read_only=True, required=False)
    creater = serializers.CharField(read_only=True, required=False)
    create_time = serializers.DateTimeField(read_only=True, format='%Y-%m-%d %H:%M:%S')
    update_time = serializers.DateTimeField(read_only=True, format='%Y-%m-%d %H:%M:%S')
    staging_bin = serializers.SerializerMethodField()
    staging_bins = serializers.SerializerMethodField()

    def _get_staging_bins(self, obj):
        from staging.models import StagingAssignment
        return list(StagingAssignment.objects.filter(
            openid=obj.openid,
            flow=StagingAssignment.INBOUND,
            reference_code=obj.asn_code,
            status__in=(StagingAssignment.RESERVED, StagingAssignment.ACTIVE),
        ).order_by('id').values_list('bin_name', flat=True))

    def get_staging_bin(self, obj):
        return ', '.join(self._get_staging_bins(obj))

    def get_staging_bins(self, obj):
        return self._get_staging_bins(obj)
    class Meta:
        model = AsnDetailModel
        exclude = ['openid', 'is_delete', ]
        read_only_fields = ['id', 'openid']

class ASNDetailPostSerializer(serializers.ModelSerializer):
    openid = serializers.CharField(read_only=False, required=False, validators=[datasolve.openid_validate])
    asn_code = serializers.CharField(read_only=False,  required=True, validators=[datasolve.data_validate])
    supplier = serializers.CharField(read_only=False,  required=True, validators=[datasolve.data_validate])
    goods_code = serializers.CharField(read_only=False, required=True, validators=[datasolve.data_validate])
    goods_desc = serializers.CharField(read_only=False, required=False)
    goods_qty = serializers.IntegerField(read_only=False, required=True, validators=[datasolve.qty_0_data_validate])
    creater = serializers.CharField(read_only=False, required=True, validators=[datasolve.data_validate])
    class Meta:
        model = AsnDetailModel
        exclude = ['is_delete', ]
        read_only_fields = ['id', 'create_time', 'update_time', ]

class ASNSortedPostSerializer(serializers.ModelSerializer):
    openid = serializers.CharField(read_only=False, required=False, validators=[datasolve.openid_validate])
    asn_code = serializers.CharField(read_only=False,  required=True, validators=[datasolve.data_validate])
    supplier = serializers.CharField(read_only=False,  required=True, validators=[datasolve.data_validate])
    goods_code = serializers.CharField(read_only=False, required=True, validators=[datasolve.data_validate])
    goods_desc = serializers.CharField(read_only=False, required=False)
    goods_qty = serializers.IntegerField(read_only=False, required=True, validators=[datasolve.qty_data_validate])
    creater = serializers.CharField(read_only=False, required=True, validators=[datasolve.data_validate])
    class Meta:
        model = AsnDetailModel
        exclude = ['is_delete', ]
        read_only_fields = ['id', 'create_time', 'update_time', ]

class ASNDetailUpdateSerializer(serializers.ModelSerializer):
    asn_code = serializers.CharField(read_only=False, required=True, validators=[datasolve.data_validate])
    supplier = serializers.CharField(read_only=False,  required=True, validators=[datasolve.data_validate])
    goods_code = serializers.CharField(read_only=False, required=True, validators=[datasolve.data_validate])
    goods_desc = serializers.CharField(read_only=False, required=False)
    goods_qty = serializers.IntegerField(read_only=False, required=True, validators=[datasolve.qty_0_data_validate])
    creater = serializers.CharField(read_only=False, required=True, validators=[datasolve.data_validate])
    class Meta:
        model = AsnDetailModel
        exclude = ['openid', 'is_delete', ]
        read_only_fields = ['id', 'create_time', 'update_time', ]

class ASNDetailPartialUpdateSerializer(serializers.ModelSerializer):
    asn_code = serializers.CharField(read_only=False, required=False, validators=[datasolve.data_validate])
    supplier = serializers.CharField(read_only=False,  required=False, validators=[datasolve.data_validate])
    goods_code = serializers.CharField(read_only=False, required=False, validators=[datasolve.data_validate])
    goods_desc = serializers.CharField(read_only=False, required=False)
    goods_qty = serializers.IntegerField(read_only=False, required=False, validators=[datasolve.qty_0_data_validate])
    creater = serializers.CharField(read_only=False, required=False, validators=[datasolve.data_validate])
    class Meta:
        model = AsnDetailModel
        exclude = ['openid', 'is_delete', ]
        read_only_fields = ['id', 'create_time', 'update_time', ]

class MoveToBinSerializer(serializers.ModelSerializer):
    bin_name = serializers.CharField(read_only=False, required=True, validators=[datasolve.data_validate])
    qty = serializers.IntegerField(read_only=False, required=True, validators=[datasolve.qty_0_data_validate])
    class Meta:
        model = AsnDetailModel
        ref_name = 'AsnMoveToBin'
        exclude = ['openid', 'is_delete', ]
        read_only_fields = ['id', 'create_time', 'update_time', ]

class FileListRenderSerializer(serializers.ModelSerializer):
    asn_code = serializers.CharField(read_only=False, required=False)
    asn_status = serializers.IntegerField(read_only=False, required=False)
    total_weight = serializers.FloatField(read_only=False, required=False)
    total_volume = serializers.FloatField(read_only=False, required=False)
    total_cost = serializers.FloatField(read_only=False, required=False)
    supplier = serializers.CharField(read_only=False, required=False)
    creater = serializers.CharField(read_only=False, required=False)
    transportation_fee = serializers.JSONField(read_only=False, required=False)
    create_time = serializers.DateTimeField(read_only=True, format='%Y-%m-%d %H:%M:%S')
    update_time = serializers.DateTimeField(read_only=True, format='%Y-%m-%d %H:%M:%S')

    class Meta:
        model = AsnListModel
        ref_name = 'ASNFileListRenderSerializer'
        exclude = ['openid', 'is_delete', ]

class FileDetailRenderSerializer(serializers.ModelSerializer):
    asn_code = serializers.CharField(read_only=False, required=False)
    asn_status = serializers.IntegerField(read_only=False, required=False)
    goods_code = serializers.CharField(read_only=False, required=False)
    goods_desc = serializers.CharField(read_only=False, required=False)
    goods_qty = serializers.IntegerField(read_only=False, required=False)
    goods_actual_qty = serializers.IntegerField(read_only=False, required=False)
    sorted_qty = serializers.IntegerField(read_only=False, required=False)
    goods_shortage_qty = serializers.IntegerField(read_only=False, required=False)
    goods_more_qty = serializers.IntegerField(read_only=False, required=False)
    goods_damage_qty = serializers.IntegerField(read_only=False, required=False)
    goods_weight = serializers.FloatField(read_only=False, required=False)
    goods_volume = serializers.FloatField(read_only=False, required=False)
    goods_cost = serializers.FloatField(read_only=False, required=False)
    supplier = serializers.CharField(read_only=False, required=False)
    creater = serializers.CharField(read_only=False, required=False)
    create_time = serializers.DateTimeField(read_only=True, format='%Y-%m-%d %H:%M:%S')
    update_time = serializers.DateTimeField(read_only=True, format='%Y-%m-%d %H:%M:%S')

    class Meta:
        model = AsnDetailModel
        ref_name = 'ASNFileDetailRenderSerializer'
        exclude = ['openid', 'is_delete', ]
