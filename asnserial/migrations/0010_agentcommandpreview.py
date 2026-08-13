from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('asnserial', '0009_qc_disposition_evidence'),
    ]

    operations = [
        migrations.CreateModel(
            name='AgentCommandPreview',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('openid', models.CharField(max_length=255)),
                ('operation', models.CharField(max_length=64)),
                ('resource_id', models.CharField(blank=True, default='', max_length=255)),
                ('asn_code', models.CharField(blank=True, default='', max_length=255)),
                ('payload_hash', models.CharField(max_length=64)),
                ('confirmation_token_hash', models.CharField(max_length=64)),
                ('idempotency_key', models.CharField(blank=True, default='', max_length=255)),
                ('preview_payload', models.JSONField(default=dict)),
                ('result', models.JSONField(blank=True, null=True)),
                ('status', models.CharField(default='PENDING', max_length=16)),
                ('created_by', models.CharField(blank=True, default='', max_length=255)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('expires_at', models.DateTimeField()),
                ('used_at', models.DateTimeField(blank=True, null=True)),
            ],
            options={
                'db_table': 'agentcommandpreview',
                'ordering': ['-created_at', '-id'],
            },
        ),
        migrations.AddIndex(
            model_name='agentcommandpreview',
            index=models.Index(fields=['openid', 'operation', 'created_at'], name='agentcomman_openid_11b9f7_idx'),
        ),
        migrations.AddIndex(
            model_name='agentcommandpreview',
            index=models.Index(fields=['openid', 'confirmation_token_hash'], name='agentcomman_openid_0c190b_idx'),
        ),
        migrations.AddIndex(
            model_name='agentcommandpreview',
            index=models.Index(fields=['openid', 'idempotency_key'], name='agentcomman_openid_96833d_idx'),
        ),
    ]
