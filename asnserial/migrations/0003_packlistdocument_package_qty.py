from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('asnserial', '0002_packlistdocument_alter_asnserialrecord_status_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='packlistdocument',
            name='package_qty',
            field=models.PositiveIntegerField(default=0),
        ),
    ]
