from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('driver', '0002_dispatchlist_contact_char'),
    ]

    operations = [
        migrations.AddField(
            model_name='dispatchlistmodel',
            name='staging_bin',
            field=models.CharField(blank=True, default='', max_length=255, verbose_name='Staging Location'),
        ),
    ]
