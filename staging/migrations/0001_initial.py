from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name='StagingAssignment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('flow', models.CharField(choices=[('INBOUND', 'Inbound'), ('OUTBOUND', 'Outbound')], max_length=12)),
                ('reference_code', models.CharField(max_length=255, verbose_name='ASN or DN Code')),
                ('goods_code', models.CharField(blank=True, default='', max_length=255)),
                ('quantity', models.BigIntegerField(default=0)),
                ('bin_name', models.CharField(max_length=255)),
                ('status', models.CharField(choices=[('ACTIVE', 'Active'), ('RELEASED', 'Released')], default='ACTIVE', max_length=12)),
                ('creater', models.CharField(blank=True, default='', max_length=255)),
                ('openid', models.CharField(max_length=255)),
                ('create_time', models.DateTimeField(auto_now_add=True)),
                ('release_time', models.DateTimeField(blank=True, null=True)),
            ],
            options={
                'db_table': 'stagingassignment',
                'ordering': ['-id'],
            },
        ),
        migrations.AddIndex(
            model_name='stagingassignment',
            index=models.Index(fields=['openid', 'bin_name', 'status'], name='stagingassi_openid_e680a9_idx'),
        ),
        migrations.AddIndex(
            model_name='stagingassignment',
            index=models.Index(fields=['openid', 'flow', 'reference_code', 'status'], name='stagingassi_openid_c7cd9b_idx'),
        ),
    ]
