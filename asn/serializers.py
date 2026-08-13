from rest_framework import serializers
from .models import AsnListModel, AsnDetailModel
from utils import datasolve
from supplier.shortname import generated_supplier_short_name
from asnserial.models import (
    HOLD_QUARANTINE,
    REJECT_RETURN,
)

class ASNListGetSerializer(serializers.ModelSerializer):
    asn_code = serializers.CharField(read_only=True, required=False)
    asn_status = serializers.IntegerField(read_only=True, required=False)
    expected_arrival_at = serializers.DateTimeField(read_only=True, required=False, format='%Y-%m-%d %H:%M:%S')
    actual_arrival_at = serializers.DateTimeField(read_only=True, required=False, format='%Y-%m-%d %H:%M:%S')
    eta_received_at = serializers.DateTimeField(read_only=True, required=False, format='%Y-%m-%d %H:%M:%S')
    supplier = serializers.CharField(read_only=True, required=False)
    supplier_short_name = serializers.SerializerMethodField()
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
    precheck_status = serializers.SerializerMethodField()
    package_qty = serializers.IntegerField(read_only=True)
    package_qty_source = serializers.SerializerMethodField()
    staging_reserved_qty = serializers.SerializerMethodField()
    staging_occupied_qty = serializers.SerializerMethodField()
    arrival_status = serializers.SerializerMethodField()
    serial_acceptance = serializers.SerializerMethodField()
    putaway_qty = serializers.SerializerMethodField()
    operational_status = serializers.SerializerMethodField()
    operational_status_reason = serializers.SerializerMethodField()
    next_action_code = serializers.SerializerMethodField()
    next_action_label = serializers.SerializerMethodField()
    putaway_driver = serializers.CharField(read_only=True, required=False)

    def get_supplier_short_name(self, obj):
        cache = self.context.setdefault('_asn_supplier_cache', {})
        cache_key = (obj.openid, obj.supplier)
        if cache_key not in cache:
            from supplier.models import ListModel as SupplierModel
            cache[cache_key] = SupplierModel.objects.filter(
                openid=obj.openid,
                supplier_name=obj.supplier,
                is_delete=False,
            ).only('supplier_short_name').first()
        supplier_record = cache[cache_key]
        if supplier_record and (supplier_record.supplier_short_name or '').strip():
            return supplier_record.supplier_short_name.strip()
        return generated_supplier_short_name(obj.supplier)

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
                'exception_resolved',
            ):
                summary['planned_qty'] += detail.goods_qty or 0
                summary['actual_qty'] += detail.goods_actual_qty or 0
                if not detail.exception_resolved:
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
            is_current=True,
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

    def get_package_qty_source(self, obj):
        from asn.services import inbound_package_quantity
        return inbound_package_quantity(obj)[1]

    def _get_staging_summary(self, obj):
        cache = self.context.setdefault('_asn_staging_summary_cache', {})
        cache_key = (obj.openid, obj.asn_code)
        if cache_key not in cache:
            from staging.models import StagingAssignment
            assignments = StagingAssignment.objects.filter(
                openid=obj.openid,
                flow=StagingAssignment.INBOUND,
                reference_code=obj.asn_code,
                status__in=(StagingAssignment.RESERVED, StagingAssignment.ACTIVE),
            )
            cache[cache_key] = {
                'reserved': assignments.filter(status=StagingAssignment.RESERVED).count(),
                'occupied': assignments.filter(status=StagingAssignment.ACTIVE).count(),
            }
        return cache[cache_key]

    def get_staging_reserved_qty(self, obj):
        return self._get_staging_summary(obj)['reserved']

    def get_staging_occupied_qty(self, obj):
        return self._get_staging_summary(obj)['occupied']

    def get_arrival_status(self, obj):
        if obj.actual_arrival_at:
            return 'ARRIVED'
        return 'PRE_ARRIVAL'

    def _get_serial_acceptance(self, obj):
        """Expose the receiving scan result in the ASN work queue."""
        cache = self.context.setdefault('_asn_serial_acceptance_cache', {})
        cache_key = (obj.openid, obj.asn_code)
        if cache_key in cache:
            return cache[cache_key]

        from asnserial.models import AsnSerialRecord
        from asnserial.models import PackListDocument

        records = AsnSerialRecord.objects.filter(
            openid=obj.openid,
            asn_code=obj.asn_code,
        )
        actual_received_qty = int(self._get_detail_aggregate(obj)['actual_qty'] or 0)
        expected = records.filter(is_expected=True).count()
        received = records.filter(is_received=True).count()
        accepted = records.filter(status=AsnSerialRecord.ACCEPTED).count()
        resolved = records.filter(exception_resolved=True).count()
        quantity_exceptions = sum(
            0 if detail.exception_resolved else (
                int(detail.goods_shortage_qty or 0)
                + int(detail.goods_more_qty or 0)
                + int(detail.goods_damage_qty or 0)
            )
            for detail in AsnDetailModel.objects.filter(
                openid=obj.openid,
                asn_code=obj.asn_code,
                is_delete=False,
            )
        )
        exception_statuses = {
            AsnSerialRecord.DUPLICATE,
            AsnSerialRecord.WRONG_SKU,
            AsnSerialRecord.DAMAGED,
            AsnSerialRecord.REJECTED,
        }
        if expected:
            exception_statuses.add(AsnSerialRecord.UNEXPECTED)
        exceptions = records.filter(status__in=exception_statuses, exception_resolved=False).count()
        missing = records.filter(is_expected=True, is_received=False, exception_resolved=False).count()
        resolved_for_putaway = records.filter(
            exception_resolved=True,
            exception_resolution_action__in=('', 'ACCEPT_EXCEPTION', 'ACCEPT_FOR_PUTAWAY'),
        ).count()
        accepted_for_putaway = min(accepted + resolved_for_putaway, actual_received_qty)
        held = records.filter(
            exception_resolved=True,
            exception_resolution_action=HOLD_QUARANTINE,
        ).count()
        rejected = records.filter(
            exception_resolved=True,
            exception_resolution_action=REJECT_RETURN,
        ).count()
        extra_scan_count = max(received - actual_received_qty, 0)
        current_pack_list = PackListDocument.objects.filter(
            openid=obj.openid,
            asn_code=obj.asn_code,
            is_current=True,
            status=PackListDocument.CONFIRMED,
        ).first()
        pack_list_variance = 0
        actual_by_sku = {}
        pack_by_sku = {}
        if current_pack_list:
            actual_by_sku = {
                detail.goods_code: int(detail.goods_actual_qty or 0)
                for detail in AsnDetailModel.objects.filter(
                    openid=obj.openid,
                    asn_code=obj.asn_code,
                    is_delete=False,
                )
            }
            pack_by_sku = {}
            for line in current_pack_list.lines.filter(is_current=True):
                pack_by_sku[line.goods_code] = pack_by_sku.get(line.goods_code, 0) + int(line.goods_qty or 0)
            pack_list_variance = sum(
                abs(actual_by_sku.get(goods_code, 0) - quantity)
                for goods_code, quantity in pack_by_sku.items()
            )
        pack_list_variance += sum(
            quantity for goods_code, quantity in actual_by_sku.items()
            if goods_code not in pack_by_sku
        )
        if current_pack_list and current_pack_list.has_serials:
            expected_serials = {
                record.serial_number: record.goods_code
                for record in current_pack_list.serial_records.filter(is_expected=True)
            }
            received_serials = {
                record.serial_number: record.goods_code
                for record in records.filter(is_received=True)
            }
            pack_list_variance += len(set(expected_serials) - set(received_serials))
            pack_list_variance += len(set(received_serials) - set(expected_serials))
            pack_list_variance += sum(
                1 for serial_number in set(expected_serials).intersection(received_serials)
                if expected_serials[serial_number] != received_serials[serial_number]
            )

        # Quantity-only receiving has no SN rows by design. It is complete
        # here only after all quantity exceptions have been explicitly resolved.
        quantity_only_resolved = (
            actual_received_qty > 0
            and not records.exists()
            and not expected
            and not AsnDetailModel.objects.filter(
                openid=obj.openid,
                asn_code=obj.asn_code,
                is_delete=False,
                exception_resolved=False,
            ).exists()
        )
        if quantity_only_resolved:
            accepted_for_putaway = actual_received_qty
        has_receiving_result = records.exists() or actual_received_qty == 0 or quantity_only_resolved
        qc_complete = bool(
            has_receiving_result
            and not exceptions
            and not missing
            and not quantity_exceptions
            and not pack_list_variance
        )
        if exceptions or quantity_exceptions or pack_list_variance:
            status = 'EXCEPTIONS'
        elif not records.exists():
            status = 'NOT_IMPORTED'
        elif expected and accepted_for_putaway >= expected and not missing:
            status = 'ACCEPTED'
        elif received:
            status = 'PARTIAL'
        else:
            status = 'EXPECTED'

        cache[cache_key] = {
            'status': status,
            'expected': expected,
            'received': received,
            'scan_record_count': received,
            'actual_received_qty': actual_received_qty,
            'extra_scan_count': extra_scan_count,
            'accepted': accepted,
            'accepted_for_putaway': accepted_for_putaway,
            'eligible_for_putaway': accepted_for_putaway,
            'putaway_qty': accepted_for_putaway,
            'resolved': resolved,
            'held': held,
            'rejected': rejected,
            'exceptions': exceptions,
            'quantity_exceptions': quantity_exceptions,
            'pack_list_variance': pack_list_variance,
            'qc_complete': qc_complete,
            'ready_for_putaway': bool(qc_complete and accepted_for_putaway > 0),
        }
        return cache[cache_key]

    def get_serial_acceptance(self, obj):
        return self._get_serial_acceptance(obj)

    def _get_putaway_summary(self, obj):
        cache = self.context.setdefault('_asn_putaway_summary_cache', {})
        cache_key = (obj.openid, obj.asn_code)
        if cache_key not in cache:
            details = list(AsnDetailModel.objects.filter(
                openid=obj.openid,
                asn_code=obj.asn_code,
                is_delete=False,
            ).values('goods_actual_qty', 'sorted_qty'))
            actual_qty = sum(int(detail['goods_actual_qty'] or 0) for detail in details)
            putaway_qty = sum(int(detail['sorted_qty'] or 0) for detail in details)
            cache[cache_key] = {
                'actual_qty': actual_qty,
                'putaway_qty': putaway_qty,
                'complete': bool(details) and putaway_qty >= actual_qty and actual_qty > 0,
            }
        return cache[cache_key]

    def _get_operational_summary(self, obj):
        cache = self.context.setdefault('_asn_operational_summary_cache', {})
        cache_key = (obj.openid, obj.asn_code)
        if cache_key in cache:
            return cache[cache_key]

        serial = self._get_serial_acceptance(obj)
        putaway = self._get_putaway_summary(obj)
        pack_list_status = self.get_pack_list_status(obj)
        actual_qty = int(self._get_detail_aggregate(obj)['actual_qty'] or 0)
        open_exceptions = int(serial.get('exceptions') or 0) + int(serial.get('quantity_exceptions') or 0)
        has_scan_result = serial.get('status') != 'NOT_IMPORTED'
        inspection_incomplete = not serial.get('qc_complete', False)

        if not obj.actual_arrival_at:
            result = {
                'status': 'PENDING_ARRIVAL',
                'reason': 'Physical arrival is not confirmed.',
                'action': 'SET_ETA',
                'action_label': 'Set ETA',
            }
        elif int(obj.asn_status or 0) == 1:
            result = {
                'status': 'READY_TO_UNLOAD',
                'reason': 'Arrival is confirmed; unloading has not started.',
                'action': 'START_UNLOADING',
                'action_label': 'Start Unloading',
            }
        elif int(obj.asn_status or 0) == 2:
            result = {
                'status': 'UNLOADING',
                'reason': 'Unloading is in progress.',
                'action': 'FINISH_UNLOADING',
                'action_label': 'Finish Unloading',
            }
        elif open_exceptions > 0 or serial.get('status') == 'EXCEPTIONS':
            result = {
                'status': 'QC_REVIEW_REQUIRED',
                'reason': (
                    '%s open receiving exception(s) require QC resolution.' % open_exceptions
                    if open_exceptions > 0 else
                    'Receiving or Pack List reconciliation requires QC review.'
                ),
                'action': 'REVIEW_QC',
                'action_label': 'Review QC',
            }
        elif actual_qty <= 0 or not has_scan_result or inspection_incomplete:
            result = {
                'status': 'RECEIVING_REVIEW',
                'reason': 'Arrival is confirmed but receiving inspection is not complete.',
                'action': 'REVIEW_RECEIVING',
                'action_label': 'Review Receiving',
            }
        elif pack_list_status in ('PENDING', 'LATE_PENDING'):
            result = {
                'status': 'PACK_LIST_REVIEW',
                'reason': 'Pack List is imported but not confirmed.',
                'action': 'REVIEW_PACK_LIST',
                'action_label': 'Review Pack List',
            }
        elif putaway['complete']:
            result = {
                'status': 'PUTAWAY_COMPLETE',
                'reason': 'All received quantity has been put away.',
                'action': 'VIEW',
                'action_label': 'View',
            }
        elif serial.get('qc_complete') and int(serial.get('eligible_for_putaway') or 0) <= 0:
            result = {
                'status': 'QC_REVIEW_REQUIRED',
                'reason': 'QC is complete, but no received units are eligible for putaway.',
                'action': 'REVIEW_QC',
                'action_label': 'Review QC',
            }
        elif putaway['putaway_qty'] < putaway['actual_qty'] and int(serial.get('eligible_for_putaway') or 0) > 0:
            result = {
                'status': 'READY_FOR_PUTAWAY',
                'reason': 'Receiving is accepted and quantity remains to be put away.',
                'action': 'ASSIGN_DRIVER_PUTAWAY',
                'action_label': 'Assign & Putaway',
            }
        else:
            result = {
                'status': 'RECEIVING_REVIEW',
                'reason': 'Receiving status requires review.',
                'action': 'REVIEW_RECEIVING',
                'action_label': 'Review Receiving',
            }

        cache[cache_key] = result
        return result

    def get_putaway_qty(self, obj):
        return self._get_putaway_summary(obj)['putaway_qty']

    def get_operational_status(self, obj):
        return self._get_operational_summary(obj)['status']

    def get_operational_status_reason(self, obj):
        return self._get_operational_summary(obj)['reason']

    def get_next_action_code(self, obj):
        return self._get_operational_summary(obj)['action']

    def get_next_action_label(self, obj):
        return self._get_operational_summary(obj)['action_label']

    def get_actual_qty(self, obj):
        return self._get_detail_aggregate(obj)['actual_qty']

    def get_exception_qty(self, obj):
        return self._get_detail_aggregate(obj)['exception_qty']

    def get_sku_count(self, obj):
        return self._get_detail_aggregate(obj)['sku_count']

    def get_pack_list_status(self, obj):
        document = self._get_pack_list(obj)
        if not document:
            return 'NOT_RECEIVED'
        if document.late_reference:
            return 'LATE' if document.status == 'CONFIRMED' else 'LATE_PENDING'
        return document.status

    def get_pack_list_has_serials(self, obj):
        document = self._get_pack_list(obj)
        return bool(document and document.has_serials)

    def _get_precheck(self, obj):
        """Return the receiving readiness check without calling the QC result."""
        cache = self.context.setdefault('_asn_precheck_cache', {})
        cache_key = (obj.openid, obj.asn_code)
        if cache_key in cache:
            return cache[cache_key]

        not_applicable = {'code': 'NOT_APPLICABLE'}

        details = list(AsnDetailModel.objects.filter(
            openid=obj.openid,
            asn_code=obj.asn_code,
            is_delete=False,
        ).values('goods_code', 'goods_qty'))
        planned = {}
        for detail in details:
            planned[detail['goods_code']] = planned.get(detail['goods_code'], 0) + int(detail['goods_qty'] or 0)

        document = self._get_pack_list(obj)
        # Keep an unconfirmed Pack List visible after receiving starts. It is
        # not itself a putaway block for quantity-only lists, but hiding it as
        # NOT_APPLICABLE removes an important control signal from the queue.
        if int(obj.asn_status or 0) >= 4 and not document:
            cache[cache_key] = not_applicable
            return not_applicable
        if not document:
            cache[cache_key] = {'code': 'NO_PACK_LIST'}
            return cache[cache_key]
        if document.status != 'CONFIRMED':
            cache[cache_key] = {'code': 'PACK_LIST_PENDING'}
            return cache[cache_key]

        pack_lines = document.lines.filter(is_current=True).values('goods_code', 'goods_qty')
        packed = {}
        for line in pack_lines:
            packed[line['goods_code']] = packed.get(line['goods_code'], 0) + int(line['goods_qty'] or 0)
        if planned != packed:
            cache[cache_key] = {'code': 'PACK_LIST_MISMATCH'}
            return cache[cache_key]

        if document.has_serials:
            from asnserial.models import AsnSerialRecord
            expected_serials = AsnSerialRecord.objects.filter(
                openid=obj.openid,
                asn_code=obj.asn_code,
                pack_list=document,
                is_expected=True,
            ).count()
            if expected_serials < sum(packed.values()):
                cache[cache_key] = {'code': 'SN_INCOMPLETE'}
                return cache[cache_key]

        cache[cache_key] = {'code': 'READY'}
        return cache[cache_key]

    def get_precheck_status(self, obj):
        return self._get_precheck(obj)['code']

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
    expected_arrival_at = serializers.DateTimeField(read_only=False, required=False, allow_null=True)
    package_qty = serializers.IntegerField(read_only=False, required=False, min_value=0)
    container_tracking = serializers.CharField(read_only=False, required=False, allow_blank=True)
    bar_code = serializers.CharField(read_only=False, required=True)
    creater = serializers.CharField(read_only=False, required=True, validators=[datasolve.data_validate])
    class Meta:
        model = AsnListModel
        exclude = ['is_delete', ]
        read_only_fields = ['id', 'create_time', 'update_time', 'unload_driver', 'putaway_driver', ]

class ASNListPartialUpdateSerializer(serializers.ModelSerializer):
    asn_code = serializers.CharField(read_only=False,  required=True, validators=[datasolve.asn_data_validate])
    expected_arrival_at = serializers.DateTimeField(read_only=False, required=False, allow_null=True)
    package_qty = serializers.IntegerField(read_only=False, required=False, min_value=0)
    container_tracking = serializers.CharField(read_only=False, required=False, allow_blank=True)

    class Meta:
        model = AsnListModel
        exclude = ['is_delete', ]
        read_only_fields = ['id', 'create_time', 'update_time', 'unload_driver', 'putaway_driver', ]

class ASNListUpdateSerializer(serializers.ModelSerializer):
    asn_code = serializers.CharField(read_only=False,  required=True, validators=[datasolve.asn_data_validate])
    expected_arrival_at = serializers.DateTimeField(read_only=False, required=False, allow_null=True)
    package_qty = serializers.IntegerField(read_only=False, required=False, min_value=0)
    container_tracking = serializers.CharField(read_only=False, required=False, allow_blank=True)

    class Meta:
        model = AsnListModel
        exclude = ['is_delete', ]
        read_only_fields = ['id', 'create_time', 'update_time', 'unload_driver', 'putaway_driver', ]

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
    exception_resolved = serializers.BooleanField(read_only=True, required=False)
    exception_resolution_action = serializers.CharField(read_only=True, required=False)
    exception_resolution_note = serializers.CharField(read_only=True, required=False)
    exception_resolution_location = serializers.CharField(read_only=True, required=False)
    exception_resolved_by = serializers.CharField(read_only=True, required=False)
    exception_resolved_at = serializers.DateTimeField(read_only=True, required=False, format='%Y-%m-%d %H:%M:%S')
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
        read_only_fields = [
            'id', 'create_time', 'update_time',
            'exception_resolved', 'exception_resolution_action',
            'exception_resolution_note', 'exception_resolved_by', 'exception_resolved_at',
            'exception_resolution_location',
        ]

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
        read_only_fields = [
            'id', 'create_time', 'update_time',
            'exception_resolved', 'exception_resolution_action',
            'exception_resolution_note', 'exception_resolved_by', 'exception_resolved_at',
            'exception_resolution_location',
        ]

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
        read_only_fields = [
            'id', 'create_time', 'update_time',
            'exception_resolved', 'exception_resolution_action',
            'exception_resolution_note', 'exception_resolved_by', 'exception_resolved_at',
            'exception_resolution_location',
        ]

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
        read_only_fields = [
            'id', 'create_time', 'update_time',
            'exception_resolved', 'exception_resolution_action',
            'exception_resolution_note', 'exception_resolved_by', 'exception_resolved_at',
            'exception_resolution_location',
        ]

class MoveToBinSerializer(serializers.ModelSerializer):
    bin_name = serializers.CharField(read_only=False, required=True, validators=[datasolve.data_validate])
    qty = serializers.IntegerField(read_only=False, required=True, validators=[datasolve.qty_0_data_validate])
    driver = serializers.CharField(read_only=False, required=True, validators=[datasolve.data_validate])
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
