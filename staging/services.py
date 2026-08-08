from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from binproperty.models import ListModel as BinProperty
from binsize.models import ListModel as BinSize
from binset.models import ListModel as Bin
from scanner.models import ListModel as Scanner
from stock.models import StockBinModel
from utils.md5 import Md5

from .models import StagingAssignment


class StagingError(Exception):
    pass


STAGING_ZONES = ('STAGE-LEFT', 'STAGE-RIGHT')


def _default_reference(model, openid, field_name, fallback):
    item = model.objects.filter(
        Q(openid=openid, is_delete=False) | Q(openid='init_data', is_delete=False),
    ).order_by('openid').first()
    return getattr(item, field_name, fallback)


def ensure_staging_slots(openid, creater='system'):
    """Create the tenant's 40 one-load-unit staging slots on first use."""
    bin_size = _default_reference(BinSize, openid, 'bin_size', 'Big')
    bin_property = _default_reference(BinProperty, openid, 'bin_property', 'Inspection')

    # The former two parent bins are no longer selectable storage locations.
    for zone in STAGING_ZONES:
        old_bin = Bin.objects.filter(openid=openid, bin_name=zone, is_delete=False).first()
        if old_bin and not StockBinModel.objects.filter(
            openid=openid, bin_name=zone, goods_qty__gt=0
        ).exists():
            old_bin.is_delete = True
            old_bin.save(update_fields=['is_delete', 'update_time'])

    for zone in STAGING_ZONES:
        for slot in range(1, 21):
            bin_name = '%s-%02d' % (zone, slot)
            values = {
                'bin_size': bin_size,
                'bin_property': bin_property,
                'location_role': 'STAGING',
                'staging_flow': 'BOTH',
                'staging_zone': zone,
                'staging_slot': slot,
                'slot_capacity': 1,
                'empty_label': True,
                'creater': creater,
                'bar_code': Md5.md5(bin_name),
            }
            item = Bin.objects.filter(openid=openid, bin_name=bin_name).first()
            if item is None:
                Bin.objects.create(openid=openid, bin_name=bin_name, **values)
            elif item.is_delete or item.location_role != 'STAGING' or item.staging_flow != 'BOTH':
                for key, value in values.items():
                    setattr(item, key, value)
                item.is_delete = False
                item.save()
            Scanner.objects.get_or_create(
                openid=openid,
                mode='BINSET',
                code=bin_name,
                defaults={'bar_code': Md5.md5(bin_name)},
            )


def staging_slots(openid, flow=None):
    ensure_staging_slots(openid)
    slots = Bin.objects.filter(
        openid=openid,
        is_delete=False,
        location_role='STAGING',
        staging_slot__gt=0,
    )
    if flow:
        slots = slots.filter(Q(staging_flow=flow) | Q(staging_flow='BOTH'))
    assignments = {
        item.bin_name: item
        for item in StagingAssignment.objects.filter(
            openid=openid, status=StagingAssignment.ACTIVE
        )
    }
    result = []
    for slot in slots.order_by('staging_zone', 'staging_slot'):
        assignment = assignments.get(slot.bin_name)
        result.append({
            'bin_name': slot.bin_name,
            'zone': slot.staging_zone,
            'slot': slot.staging_slot,
            'capacity': slot.slot_capacity,
            'occupied': assignment is not None,
            'available': assignment is None,
            'assignment': None if assignment is None else {
                'flow': assignment.flow,
                'reference_code': assignment.reference_code,
                'goods_code': assignment.goods_code,
                'quantity': assignment.quantity,
                'status': assignment.status,
            },
        })
    return result


@transaction.atomic
def reserve_staging_slot(openid, flow, reference_code, bin_name, quantity=0,
                         goods_code='', creater=''):
    if flow not in (StagingAssignment.INBOUND, StagingAssignment.OUTBOUND):
        raise StagingError('Invalid staging flow')
    if not reference_code or not bin_name:
        raise StagingError('Reference code and staging location are required')
    ensure_staging_slots(openid, creater=creater or 'system')
    slot = Bin.objects.select_for_update().filter(
        openid=openid,
        bin_name=str(bin_name),
        location_role='STAGING',
        staging_slot__gt=0,
        is_delete=False,
    ).filter(Q(staging_flow=flow) | Q(staging_flow='BOTH')).first()
    if slot is None:
        raise StagingError('Selected location is not a valid staging slot')

    existing_reference = StagingAssignment.objects.select_for_update().filter(
        openid=openid,
        flow=flow,
        reference_code=str(reference_code),
        status=StagingAssignment.ACTIVE,
    ).first()
    if existing_reference:
        if existing_reference.bin_name != slot.bin_name:
            raise StagingError('This order already has an active staging location')
        return existing_reference

    if StagingAssignment.objects.select_for_update().filter(
        openid=openid, bin_name=slot.bin_name, status=StagingAssignment.ACTIVE
    ).exists():
        raise StagingError('Selected staging location is occupied')

    return StagingAssignment.objects.create(
        openid=openid,
        flow=flow,
        reference_code=str(reference_code),
        goods_code=str(goods_code or ''),
        quantity=int(quantity or 0),
        bin_name=slot.bin_name,
        creater=str(creater or ''),
    )


def release_staging_slot(openid, flow, reference_code):
    return StagingAssignment.objects.filter(
        openid=openid,
        flow=flow,
        reference_code=str(reference_code),
        status=StagingAssignment.ACTIVE,
    ).update(status=StagingAssignment.RELEASED, release_time=timezone.now())
