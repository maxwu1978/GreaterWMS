from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name='AsnSerialRecord',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('openid', models.CharField(max_length=255)),
                ('asn_code', models.CharField(max_length=255)),
                ('goods_code', models.CharField(max_length=255)),
                ('expected_goods_code', models.CharField(blank=True, default='', max_length=255)),
                ('scanned_goods_code', models.CharField(blank=True, default='', max_length=255)),
                ('serial_number', models.CharField(max_length=255)),
                ('double_scan_sn', models.CharField(blank=True, default='', max_length=255)),
                ('inbound_po', models.CharField(blank=True, default='', max_length=255)),
                ('inbound_date', models.DateField(blank=True, null=True)),
                ('source_location', models.CharField(blank=True, default='', max_length=255)),
                ('shipout_ref', models.CharField(blank=True, default='', max_length=255)),
                ('source_file', models.CharField(blank=True, default='', max_length=255)),
                ('source_row', models.PositiveIntegerField(default=0)),
                ('status', models.CharField(choices=[('EXPECTED', 'Expected'), ('ACCEPTED', 'Accepted'), ('UNEXPECTED', 'Unexpected'), ('DUPLICATE', 'Duplicate'), ('WRONG_SKU', 'Wrong SKU'), ('DAMAGED', 'Damaged'), ('REJECTED', 'Rejected')], default='EXPECTED', max_length=32)),
                ('is_expected', models.BooleanField(default=True)),
                ('is_received', models.BooleanField(default=False)),
                ('scan_count', models.PositiveIntegerField(default=0)),
                ('damaged', models.BooleanField(default=False)),
                ('note', models.TextField(blank=True, default='')),
                ('expected_by', models.CharField(blank=True, default='', max_length=255)),
                ('received_by', models.CharField(blank=True, default='', max_length=255)),
                ('expected_at', models.DateTimeField(blank=True, null=True)),
                ('received_at', models.DateTimeField(blank=True, null=True)),
                ('create_time', models.DateTimeField(auto_now_add=True)),
                ('update_time', models.DateTimeField(auto_now=True)),
            ],
            options={
                'db_table': 'asnserialrecord',
                'ordering': ['goods_code', 'serial_number'],
            },
        ),
        migrations.AddIndex(
            model_name='asnserialrecord',
            index=models.Index(fields=['openid', 'asn_code'], name='asnserialre_openid_b07756_idx'),
        ),
        migrations.AddIndex(
            model_name='asnserialrecord',
            index=models.Index(fields=['openid', 'serial_number'], name='asnserialre_openid_c9db70_idx'),
        ),
        migrations.AddIndex(
            model_name='asnserialrecord',
            index=models.Index(fields=['openid', 'status'], name='asnserialre_openid_d86fd9_idx'),
        ),
        migrations.AddConstraint(
            model_name='asnserialrecord',
            constraint=models.UniqueConstraint(fields=('openid', 'asn_code', 'serial_number'), name='asnserial_openid_asn_sn_uniq'),
        ),
    ]
