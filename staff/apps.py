from django.apps import AppConfig
from django.db.models.signals import post_migrate

class StaffConfig(AppConfig):
    name = 'staff'
    def ready(self):
        post_migrate.connect(do_init_data, sender=self)


DEFAULT_STAFF_TYPES = (
    'Manager', 'Supplier', 'Customer', 'Supervisor', 'Inbound',
    'Outbound', 'StockControl', 'Warehouse', 'QC', 'Driver',
)


def do_init_data(sender, **kwargs):
    init_category()

def init_category():
    """
        :return:None
    """
    try:
        from .models import TypeListModel as ls
        for staff_type in DEFAULT_STAFF_TYPES:
            ls.objects.get_or_create(
                openid='init_data',
                staff_type=staff_type,
                defaults={'creater': 'GreaterWMS'},
            )
    except:
        pass
