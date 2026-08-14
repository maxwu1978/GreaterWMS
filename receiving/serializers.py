from rest_framework import serializers

from .models import ReceivingDetail, ReceivingRecord, ReceivingSerial


class ReceivingSerialSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReceivingSerial
        exclude = ['openid', 'receipt', 'detail']
        read_only_fields = ['id', 'scanned_at']


class ReceivingDetailSerializer(serializers.ModelSerializer):
    serials = ReceivingSerialSerializer(many=True, read_only=True)

    class Meta:
        model = ReceivingDetail
        exclude = ['openid', 'receipt']
        read_only_fields = ['id', 'create_time', 'update_time']


class ReceivingRecordSerializer(serializers.ModelSerializer):
    details = ReceivingDetailSerializer(many=True, read_only=True)
    serial_count = serializers.SerializerMethodField()
    open_exception_count = serializers.SerializerMethodField()

    class Meta:
        model = ReceivingRecord
        exclude = ['openid']
        read_only_fields = ['id', 'create_time', 'update_time']

    def get_serial_count(self, obj):
        return obj.serials.count()

    def get_open_exception_count(self, obj):
        return sum(
            1 for detail in obj.details.all()
            if detail.exception_note and detail.resolution_action not in (
                'ACCEPT_FOR_PUTAWAY', 'REJECT_RETURN',
            )
        )
