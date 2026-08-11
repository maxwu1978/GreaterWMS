from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('asn', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='asnlistmodel',
            name='expected_arrival_at',
            field=models.DateTimeField(
                blank=True,
                null=True,
                verbose_name='Expected Arrival Time',
            ),
        ),
    ]
