from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('goods', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='listmodel',
            name='goods_desc',
            field=models.CharField(blank=True, default='', max_length=255, verbose_name='Goods Description'),
        ),
        migrations.AlterField(
            model_name='listmodel',
            name='goods_supplier',
            field=models.CharField(blank=True, default='', max_length=255, verbose_name='Goods Supplier'),
        ),
        migrations.AlterField(
            model_name='listmodel',
            name='goods_weight',
            field=models.FloatField(blank=True, default=0, null=True, verbose_name='Goods Weight'),
        ),
        migrations.AlterField(
            model_name='listmodel',
            name='goods_w',
            field=models.FloatField(blank=True, default=0, null=True, verbose_name='Goods Width'),
        ),
        migrations.AlterField(
            model_name='listmodel',
            name='goods_d',
            field=models.FloatField(blank=True, default=0, null=True, verbose_name='Goods Depth'),
        ),
        migrations.AlterField(
            model_name='listmodel',
            name='goods_h',
            field=models.FloatField(blank=True, default=0, null=True, verbose_name='Goods Height'),
        ),
        migrations.AlterField(
            model_name='listmodel',
            name='unit_volume',
            field=models.FloatField(blank=True, default=0, null=True, verbose_name='Unit Volume'),
        ),
        migrations.AlterField(
            model_name='listmodel',
            name='goods_unit',
            field=models.CharField(blank=True, default='', max_length=255, verbose_name='Goods Unit'),
        ),
        migrations.AlterField(
            model_name='listmodel',
            name='goods_class',
            field=models.CharField(blank=True, default='', max_length=255, verbose_name='Goods Class'),
        ),
        migrations.AlterField(
            model_name='listmodel',
            name='goods_brand',
            field=models.CharField(blank=True, default='', max_length=255, verbose_name='Goods Brand'),
        ),
        migrations.AlterField(
            model_name='listmodel',
            name='goods_color',
            field=models.CharField(blank=True, default='', max_length=255, verbose_name='Goods Color'),
        ),
        migrations.AlterField(
            model_name='listmodel',
            name='goods_shape',
            field=models.CharField(blank=True, default='', max_length=255, verbose_name='Goods Shape'),
        ),
        migrations.AlterField(
            model_name='listmodel',
            name='goods_specs',
            field=models.CharField(blank=True, default='', max_length=255, verbose_name='Goods Specs'),
        ),
        migrations.AlterField(
            model_name='listmodel',
            name='goods_origin',
            field=models.CharField(blank=True, default='', max_length=255, verbose_name='Goods Origin'),
        ),
        migrations.AlterField(
            model_name='listmodel',
            name='goods_cost',
            field=models.FloatField(blank=True, default=0, null=True, verbose_name='Goods Cost'),
        ),
        migrations.AlterField(
            model_name='listmodel',
            name='goods_price',
            field=models.FloatField(blank=True, default=0, null=True, verbose_name='Goods Price'),
        ),
        migrations.AlterField(
            model_name='listmodel',
            name='creater',
            field=models.CharField(blank=True, default='', max_length=255, verbose_name='Who created'),
        ),
        migrations.AlterField(
            model_name='listmodel',
            name='bar_code',
            field=models.CharField(blank=True, default='', max_length=255, verbose_name='Bar Code'),
        ),
        migrations.AddField(
            model_name='listmodel',
            name='measurement_unit',
            field=models.CharField(blank=True, default='', max_length=32, verbose_name='Measurement Unit'),
        ),
        migrations.AddField(
            model_name='listmodel',
            name='customer_sku',
            field=models.CharField(blank=True, default='', max_length=255, verbose_name='Customer SKU'),
        ),
        migrations.AddField(
            model_name='listmodel',
            name='source_evidence_id',
            field=models.PositiveBigIntegerField(blank=True, null=True, verbose_name='Source Evidence ID'),
        ),
        migrations.AddField(
            model_name='listmodel',
            name='source_note',
            field=models.TextField(blank=True, default='', verbose_name='Source Note'),
        ),
    ]
