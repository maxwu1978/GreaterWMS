from rest_framework import serializers

from .models import TransportOrder


class TransportOrderSerializer(serializers.ModelSerializer):
    class Meta:
        model = TransportOrder
        exclude = ['openid']
        read_only_fields = [
            'id', 'create_time', 'update_time', 'completed_at',
            'completed_by',
        ]
