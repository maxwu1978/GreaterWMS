from rest_framework.exceptions import APIException

from asn.models import AsnDetailModel, AsnListModel

from .models import ReceivingRecord


def assert_legacy_asn_putaway_allowed(openid, asn_code, goods_code):
    """Prevent the legacy ASN path from posting stock already owned by Receiving."""
    asn = AsnListModel.objects.select_for_update().filter(
        openid=openid,
        asn_code=asn_code,
        is_delete=False,
    ).first()
    if asn is None:
        return

    receiving_query = ReceivingRecord.objects.filter(
        openid=openid,
        linked_asn_code=asn_code,
    ).exclude(status=ReceivingRecord.CANCELLED)
    if receiving_query.exists():
        raise APIException({
            'detail': 'This ASN is controlled by Receiving; complete stock putaway there instead',
        })

    if ReceivingRecord.objects.filter(
        openid=openid,
        customer=asn.supplier,
        source_type__isnull=False,
        status__in=(
            ReceivingRecord.RECEIVING,
            ReceivingRecord.QC_PENDING,
            ReceivingRecord.QC_EXCEPTION,
            ReceivingRecord.PUTAWAY_PENDING,
            ReceivingRecord.PUTAWAY_COMPLETE,
            ReceivingRecord.CLOSED,
        ),
        details__goods_code=goods_code,
    ).exclude(source_type='OUTBOUND_RETURN').exists():
        raise APIException({
            'detail': 'A Receiving record exists for this customer and SKU; complete it instead of using ASN putaway',
        })


def assert_receiving_can_claim_asn(openid, customer, goods_codes, linked_asn_code='', exclude_receipt_no=''):
    """Lock and validate the ASN/Receiving ownership boundary before receipt creation."""
    goods_codes = {str(value).strip() for value in goods_codes if str(value).strip()}
    if not goods_codes:
        return None

    if linked_asn_code:
        asn = AsnListModel.objects.select_for_update().filter(
            openid=openid,
            asn_code=linked_asn_code,
            is_delete=False,
        ).first()
        if asn is None:
            raise APIException({'detail': 'Linked ASN does not exist'})
        details = list(AsnDetailModel.objects.select_for_update().filter(
            openid=openid,
            asn_code=linked_asn_code,
            goods_code__in=goods_codes,
            is_delete=False,
        ))
        asn_goods_codes = set(AsnDetailModel.objects.filter(
            openid=openid,
            asn_code=linked_asn_code,
            is_delete=False,
        ).values_list('goods_code', flat=True))
        unknown_goods_codes = goods_codes - asn_goods_codes
        if unknown_goods_codes:
            raise APIException({
                'detail': 'Receiving SKU does not belong to the linked ASN: %s' % sorted(unknown_goods_codes)[0],
            })
        if asn.asn_status >= 2 or any(int(detail.asn_status or 0) >= 2 or int(detail.sorted_qty or 0) > 0 for detail in details):
            raise APIException({
                'detail': 'This ASN has started the legacy inbound flow; do not mix it with Receiving',
            })
        receiving_query = ReceivingRecord.objects.select_for_update().filter(
            openid=openid,
            linked_asn_code=linked_asn_code,
        ).exclude(status=ReceivingRecord.CANCELLED)
        if exclude_receipt_no:
            receiving_query = receiving_query.exclude(receipt_no=exclude_receipt_no)
        if receiving_query.exists():
            raise APIException({'detail': 'A Receiving record already claims this ASN'})
        return asn

    candidate_asn_codes = AsnDetailModel.objects.filter(
        openid=openid,
        goods_code__in=goods_codes,
        is_delete=False,
    ).values_list('asn_code', flat=True)
    candidate_asns = list(AsnListModel.objects.select_for_update().filter(
        openid=openid,
        asn_code__in=candidate_asn_codes,
        supplier=customer,
        is_delete=False,
    ))
    for candidate_asn in candidate_asns:
        candidate_details = AsnDetailModel.objects.select_for_update().filter(
            openid=openid,
            asn_code=candidate_asn.asn_code,
            goods_code__in=goods_codes,
            is_delete=False,
        )
        if candidate_asn.asn_status >= 2 or any(
            int(detail.asn_status or 0) >= 2 or int(detail.sorted_qty or 0) > 0
            for detail in candidate_details
        ):
            raise APIException({
                'detail': 'An ASN has already started the legacy inbound flow for this customer and SKU; use that flow or reconcile before creating Receiving',
            })
    return None
