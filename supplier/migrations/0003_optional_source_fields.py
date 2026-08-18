from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('supplier', '0002_supplier_short_name'),
    ]

    operations = [
        migrations.AlterField(
            model_name='listmodel',
            name='supplier_city',
            field=models.CharField(blank=True, default='', max_length=255, verbose_name='Supplier City'),
        ),
        migrations.AlterField(
            model_name='listmodel',
            name='supplier_address',
            field=models.CharField(blank=True, default='', max_length=255, verbose_name='Supplier Address'),
        ),
        migrations.AlterField(
            model_name='listmodel',
            name='supplier_contact',
            field=models.CharField(blank=True, default='', max_length=255, verbose_name='Supplier Contact'),
        ),
        migrations.AlterField(
            model_name='listmodel',
            name='supplier_manager',
            field=models.CharField(blank=True, default='', max_length=255, verbose_name='Supplier Manager'),
        ),
        migrations.AlterField(
            model_name='listmodel',
            name='creater',
            field=models.CharField(blank=True, default='', max_length=255, verbose_name='Who Created'),
        ),
    ]
