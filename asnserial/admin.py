from django.contrib import admin

from .models import AsnSerialRecord, PackListDocument, PackListImportBatch, PackListLine


@admin.register(AsnSerialRecord)
class AsnSerialRecordAdmin(admin.ModelAdmin):
    list_display = ('asn_code', 'goods_code', 'serial_number', 'status', 'is_expected', 'is_received')
    list_filter = ('status', 'is_expected', 'is_received', 'damaged')
    search_fields = ('asn_code', 'goods_code', 'serial_number', 'inbound_po', 'shipout_ref')


@admin.register(PackListDocument)
class PackListDocumentAdmin(admin.ModelAdmin):
    list_display = ('asn_code', 'version', 'status', 'source_type', 'has_serials', 'created_by', 'create_time')
    list_filter = ('status', 'source_type', 'has_serials')
    search_fields = ('asn_code', 'content_hash')


@admin.register(PackListLine)
class PackListLineAdmin(admin.ModelAdmin):
    list_display = ('asn_code', 'goods_code', 'customer_goods_code', 'customer_ssku', 'package_type', 'goods_qty', 'source_row')
    search_fields = ('asn_code', 'goods_code', 'customer_goods_code', 'customer_ssku', 'package_type')


@admin.register(PackListImportBatch)
class PackListImportBatchAdmin(admin.ModelAdmin):
    list_display = ('asn_code', 'import_type', 'row_count', 'imported_by', 'created_at')
    list_filter = ('import_type',)
    search_fields = ('asn_code', 'content_hash', 'imported_by')
