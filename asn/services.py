from django.db.models import Sum

from .models import AsnDetailModel


def inbound_package_quantity(asn):
    """Return load-unit quantity without treating SKU quantity as a package count."""
    if int(asn.package_qty or 0) > 0:
        return int(asn.package_qty), 'ASN'

    from asnserial.models import PackListDocument

    pack_list = PackListDocument.objects.filter(
        openid=asn.openid,
        asn_code=asn.asn_code,
        status__in=(PackListDocument.CONFIRMED, PackListDocument.PENDING),
    ).order_by('-version', '-id').first()
    if pack_list and int(pack_list.package_qty or 0) > 0:
        return int(pack_list.package_qty), 'PACK_LIST'

    # Legacy ASNs did not store load-unit counts. Keep them operable, but expose
    # that the value is only a compatibility fallback and not a package count.
    quantity = AsnDetailModel.objects.filter(
        openid=asn.openid,
        asn_code=asn.asn_code,
        is_delete=False,
    ).aggregate(total=Sum('goods_qty'))['total'] or 0
    return int(quantity), 'SKU_QTY_FALLBACK'
