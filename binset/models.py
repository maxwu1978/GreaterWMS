from django.db import models

class ListModel(models.Model):
    bin_name = models.CharField(max_length=255, verbose_name="Bin Name")
    bin_size = models.CharField(max_length=255, verbose_name="Bin Size")
    bin_property = models.CharField(max_length=11, verbose_name="Bin Property")
    # Location metadata keeps temporary staging slots out of normal putaway.
    location_role = models.CharField(max_length=20, default='STORAGE', verbose_name="Location Role")
    staging_flow = models.CharField(max_length=20, default='NONE', verbose_name="Staging Flow")
    staging_zone = models.CharField(max_length=50, default='', blank=True, verbose_name="Staging Zone")
    staging_slot = models.PositiveIntegerField(default=0, verbose_name="Staging Slot")
    slot_capacity = models.PositiveIntegerField(default=1, verbose_name="Slot Capacity")
    empty_label = models.BooleanField(default=True, verbose_name="Empty Label")
    creater = models.CharField(max_length=255, verbose_name="Who Created")
    bar_code = models.CharField(max_length=255, verbose_name="Bar Code")
    openid = models.CharField(max_length=255, verbose_name="Openid")
    is_delete = models.BooleanField(default=False, verbose_name='Delete Label')
    create_time = models.DateTimeField(auto_now_add=True, verbose_name="Create Time")
    update_time = models.DateTimeField(auto_now=True, blank=True, null=True, verbose_name="Update Time")

    class Meta:
        db_table = 'binset'
        verbose_name = 'Bin Set'
        verbose_name_plural = "Bin Set"
        ordering = ['bin_name']
