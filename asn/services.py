from django.db.models import Sum

from .models import AsnDetailModel, AsnListModel


def asn_detail_reference_errors(openid, asn_code, supplier_name, goods_codes):
    """Return client errors before ASN detail creation touches inventory."""
    from goods.models import ListModel as Goods
    from supplier.models import ListModel as Supplier

    errors = {}
    if not AsnListModel.objects.filter(
        openid=openid,
        asn_code=str(asn_code or '').strip(),
        is_delete=False,
    ).exists():
        errors['asn_code'] = ['ASN Code does not exist.']
    if not Supplier.objects.filter(
        openid=openid,
        supplier_name=str(supplier_name or '').strip(),
        is_delete=False,
    ).exists():
        errors['supplier'] = ['Supplier does not exist.']

    normalized_codes = [str(code or '').strip() for code in goods_codes]
    existing_codes = set(Goods.objects.filter(
        openid=openid,
        goods_code__in=normalized_codes,
        is_delete=False,
    ).values_list('goods_code', flat=True))
    missing_codes = [code for code in normalized_codes if code not in existing_codes]
    if missing_codes:
        errors['goods_code'] = [
            'SKU does not exist: %s.' % ', '.join(dict.fromkeys(missing_codes))
        ]
    return errors


def inbound_package_quantity(asn):
    """Return load-unit quantity without treating SKU quantity as a package count."""
    if int(asn.package_qty or 0) > 0:
        return int(asn.package_qty), 'ASN'

    from asnserial.models import PackListDocument

    pack_list = PackListDocument.objects.filter(
        openid=asn.openid,
        asn_code=asn.asn_code,
        is_current=True,
        status__in=(PackListDocument.CONFIRMED, PackListDocument.PENDING),
    ).first()
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
