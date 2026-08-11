from django.contrib import admin

from .models import AsnSerialRecord, PackListDocument, PackListLine


@admin.register(AsnSerialRecord)
class AsnSerialRecordAdmin(admin.ModelAdmin):
    list_display = ('asn_code', 'goods_code', 'serial_number', 'status', 'is_expected', 'is_received')
    list_filter = ('status', 'is_expected', 'is_received', 'damaged')
    search_fields = ('asn_code', 'goods_code', 'serial_number', 'inbound_po', 'shipout_ref')


@admin.register(PackListDocument)
class PackListDocumentAdmin(admin.ModelAdmin):
    list_display = ('asn_code', 'version', 'status', 'source_type', 'has_serials', 'created_by', 'create_time')
    list_filter = ('status', 'source_type', 'has_serials')
    search_fields = ('asn_code', 'source_file', 'source_url')


@admin.register(PackListLine)
class PackListLineAdmin(admin.ModelAdmin):
    list_display = ('asn_code', 'goods_code', 'customer_goods_code', 'goods_qty', 'source_row')
    search_fields = ('asn_code', 'goods_code', 'customer_goods_code')
