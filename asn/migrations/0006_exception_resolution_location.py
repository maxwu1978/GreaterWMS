from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('asn', '0005_putaway_driver_and_exception_resolution'),
    ]

    operations = [
        migrations.AddField(
            model_name='asndetailmodel',
            name='exception_resolution_location',
            field=models.CharField(blank=True, default='', max_length=255, verbose_name='Exception Resolution Location'),
        ),
    ]
