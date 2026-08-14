from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dn', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='dndetailmodel',
            name='delivery_note',
            field=models.TextField(blank=True, default='', verbose_name='Delivery Exception Note'),
        ),
    ]
