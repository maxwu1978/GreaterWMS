from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('asnserial', '0011_exception_movement'),
    ]

    operations = [
        migrations.CreateModel(
            name='ExceptionQuantityMovement',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('openid', models.CharField(max_length=255)),
                ('asn_code', models.CharField(max_length=255)),
                ('goods_code', models.CharField(max_length=255)),
                ('quantity', models.PositiveIntegerField()),
                ('action', models.CharField(max_length=64)),
                ('bin_name', models.CharField(max_length=255)),
                ('operator', models.CharField(blank=True, default='', max_length=255)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'db_table': 'exceptionquantitymovement',
                'ordering': ['-created_at', '-id'],
            },
        ),
        migrations.AddIndex(
            model_name='exceptionquantitymovement',
            index=models.Index(fields=['openid', 'asn_code', 'goods_code'], name='exceptionqu_openid_0edd95_idx'),
        ),
    ]
