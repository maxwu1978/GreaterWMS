from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('asn', '0004_unloading_driver'),
    ]

    operations = [
        migrations.AddField(
            model_name='asnlistmodel',
            name='putaway_driver',
            field=models.CharField(blank=True, default='', max_length=255, verbose_name='Putaway Driver'),
        ),
        migrations.AlterField(
            model_name='asneventmodel',
            name='event_type',
            field=models.CharField(
                choices=[
                    ('ETA_UPDATED', 'ETA Updated'),
                    ('ARRIVAL_CONFIRMED', 'Arrival Confirmed'),
                    ('STAGING_RESERVED', 'Staging Reserved'),
                    ('UNLOADING_STARTED', 'Unloading Started'),
                    ('PUTAWAY_STARTED', 'Putaway Started'),
                ],
                max_length=32,
            ),
        ),
        migrations.AddField(
            model_name='asndetailmodel',
            name='exception_resolved',
            field=models.BooleanField(default=False, verbose_name='Receiving Exception Resolved'),
        ),
        migrations.AddField(
            model_name='asndetailmodel',
            name='exception_resolution_action',
            field=models.CharField(blank=True, default='', max_length=64, verbose_name='Exception Resolution Action'),
        ),
        migrations.AddField(
            model_name='asndetailmodel',
            name='exception_resolution_note',
            field=models.TextField(blank=True, default='', verbose_name='Exception Resolution Note'),
        ),
        migrations.AddField(
            model_name='asndetailmodel',
            name='exception_resolved_by',
            field=models.CharField(blank=True, default='', max_length=255, verbose_name='Exception Resolved By'),
        ),
        migrations.AddField(
            model_name='asndetailmodel',
            name='exception_resolved_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Exception Resolved Time'),
        ),
    ]
