from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('asn', '0003_asnevent_and_intake_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='asnlistmodel',
            name='unload_driver',
            field=models.CharField(blank=True, default='', max_length=255, verbose_name='Unloading Driver'),
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
                ],
                max_length=32,
            ),
        ),
    ]
