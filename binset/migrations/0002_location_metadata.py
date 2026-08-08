from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('binset', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='listmodel',
            name='location_role',
            field=models.CharField(default='STORAGE', max_length=20, verbose_name='Location Role'),
        ),
        migrations.AddField(
            model_name='listmodel',
            name='staging_flow',
            field=models.CharField(default='NONE', max_length=20, verbose_name='Staging Flow'),
        ),
        migrations.AddField(
            model_name='listmodel',
            name='staging_zone',
            field=models.CharField(blank=True, default='', max_length=50, verbose_name='Staging Zone'),
        ),
        migrations.AddField(
            model_name='listmodel',
            name='staging_slot',
            field=models.PositiveIntegerField(default=0, verbose_name='Staging Slot'),
        ),
        migrations.AddField(
            model_name='listmodel',
            name='slot_capacity',
            field=models.PositiveIntegerField(default=1, verbose_name='Slot Capacity'),
        ),
    ]
