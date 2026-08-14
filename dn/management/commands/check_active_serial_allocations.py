from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count

from dn.models import DnSerialAllocation


class Command(BaseCommand):
    help = 'Check for duplicate active serial allocations before applying the unique constraint migration.'

    def handle(self, *args, **options):
        conflicts = list(
            DnSerialAllocation.objects.filter(
                status__in=(
                    DnSerialAllocation.REQUESTED,
                    DnSerialAllocation.PICKED,
                    DnSerialAllocation.IN_TRANSIT,
                    DnSerialAllocation.SHIPPED,
                    DnSerialAllocation.RELEASED,
                ),
            ).values('openid', 'serial_number').annotate(
                allocation_count=Count('id'),
            ).filter(allocation_count__gt=1).order_by('openid', 'serial_number')
        )
        if conflicts:
            for conflict in conflicts:
                self.stdout.write(
                    'openid=%s serial_number=%s active_allocations=%s' % (
                        conflict['openid'],
                        conflict['serial_number'],
                        conflict['allocation_count'],
                    )
                )
            raise CommandError(
                'Duplicate active serial allocations found; resolve them before running migrations.'
            )
        self.stdout.write(self.style.SUCCESS('No duplicate active serial allocations found.'))
