from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('driver', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='dispatchlistmodel',
            name='contact',
            field=models.CharField(
                blank=True,
                default='',
                max_length=255,
                verbose_name='Contact Number',
            ),
        ),
    ]
