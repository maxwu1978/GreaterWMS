from django.contrib import admin

from .models import AsnSerialRecord


@admin.register(AsnSerialRecord)
class AsnSerialRecordAdmin(admin.ModelAdmin):
    list_display = ('asn_code', 'goods_code', 'serial_number', 'status', 'is_expected', 'is_received')
    list_filter = ('status', 'is_expected', 'is_received', 'damaged')
    search_fields = ('asn_code', 'goods_code', 'serial_number', 'inbound_po', 'shipout_ref')
