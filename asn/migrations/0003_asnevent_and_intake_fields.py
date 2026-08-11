from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('asn', '0002_asnlistmodel_expected_arrival_at'),
    ]

    operations = [
        migrations.AddField(
            model_name='asnlistmodel',
            name='actual_arrival_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Actual Arrival Time'),
        ),
        migrations.AddField(
            model_name='asnlistmodel',
            name='arrival_confirmed_by',
            field=models.CharField(blank=True, default='', max_length=255, verbose_name='Arrival Confirmed By'),
        ),
        migrations.AddField(
            model_name='asnlistmodel',
            name='container_tracking',
            field=models.CharField(blank=True, default='', max_length=255, verbose_name='Container / Tracking'),
        ),
        migrations.AddField(
            model_name='asnlistmodel',
            name='eta_received_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='ETA Received Time'),
        ),
        migrations.AddField(
            model_name='asnlistmodel',
            name='eta_received_by',
            field=models.CharField(blank=True, default='', max_length=255, verbose_name='ETA Received By'),
        ),
        migrations.AddField(
            model_name='asnlistmodel',
            name='eta_source',
            field=models.CharField(blank=True, default='', max_length=64, verbose_name='ETA Source'),
        ),
        migrations.AddField(
            model_name='asnlistmodel',
            name='package_qty',
            field=models.PositiveIntegerField(default=0, verbose_name='Package / Load Unit Quantity'),
        ),
        migrations.CreateModel(
            name='AsnEventModel',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('openid', models.CharField(max_length=255)),
                ('asn_code', models.CharField(max_length=255)),
                ('event_type', models.CharField(choices=[('ETA_UPDATED', 'ETA Updated'), ('ARRIVAL_CONFIRMED', 'Arrival Confirmed'), ('STAGING_RESERVED', 'Staging Reserved')], max_length=32)),
                ('old_expected_arrival_at', models.DateTimeField(blank=True, null=True)),
                ('new_expected_arrival_at', models.DateTimeField(blank=True, null=True)),
                ('actual_arrival_at', models.DateTimeField(blank=True, null=True)),
                ('operator', models.CharField(blank=True, default='', max_length=255)),
                ('source', models.CharField(blank=True, default='', max_length=64)),
                ('note', models.TextField(blank=True, default='')),
                ('event_time', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'db_table': 'asnevent',
                'ordering': ['-event_time', '-id'],
            },
        ),
        migrations.AddIndex(
            model_name='asneventmodel',
            index=models.Index(fields=['openid', 'asn_code', 'event_type'], name='asnevent_openid_8ac84c_idx'),
        ),
        migrations.AddIndex(
            model_name='asneventmodel',
            index=models.Index(fields=['openid', 'event_time'], name='asnevent_openid_bad58e_idx'),
        ),
    ]
