from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('asnserial', '0012_exceptionquantitymovement'),
    ]

    operations = [
        migrations.CreateModel(
            name='SourceEvidence',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('openid', models.CharField(max_length=255)),
                ('source_type', models.CharField(choices=[('WEB_FORM', 'Web form'), ('EMAIL', 'Email'), ('AI_AGENT', 'AI agent'), ('CLI', 'CLI')], max_length=32)),
                ('operation', models.CharField(max_length=64)),
                ('content_hash', models.CharField(blank=True, default='', max_length=64)),
                ('status', models.CharField(choices=[('CAPTURED', 'Captured'), ('USED', 'Used'), ('EXPIRED', 'Expired')], default='CAPTURED', max_length=16)),
                ('captured_by', models.CharField(blank=True, default='', max_length=255)),
                ('captured_by_name', models.CharField(blank=True, default='', max_length=255)),
                ('ai_session_id', models.CharField(blank=True, default='', max_length=255)),
                ('metadata', models.JSONField(default=dict)),
                ('storage_uri', models.CharField(blank=True, default='', max_length=1000)),
                ('storage_size', models.PositiveBigIntegerField(default=0)),
                ('captured_at', models.DateTimeField(auto_now_add=True)),
                ('used_at', models.DateTimeField(blank=True, null=True)),
            ],
            options={
                'db_table': 'sourceevidence',
                'ordering': ['-captured_at', '-id'],
            },
        ),
        migrations.CreateModel(
            name='SourceExtraction',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('field_name', models.CharField(max_length=128)),
                ('raw_value', models.TextField(blank=True, default='')),
                ('normalized_value', models.TextField(blank=True, default='')),
                ('source_location', models.CharField(blank=True, default='', max_length=255)),
                ('confidence', models.DecimalField(blank=True, decimal_places=4, max_digits=5, null=True)),
                ('human_confirmed', models.BooleanField(default=False)),
                ('used_for_write', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('source', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='extractions', to='asnserial.sourceevidence')),
            ],
            options={
                'db_table': 'sourceextraction',
                'ordering': ['id'],
            },
        ),
        migrations.CreateModel(
            name='EntityProvenance',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('openid', models.CharField(max_length=255)),
                ('entity_type', models.CharField(max_length=64)),
                ('entity_ref', models.CharField(max_length=255)),
                ('field_name', models.CharField(max_length=128)),
                ('raw_value', models.TextField(blank=True, default='')),
                ('normalized_value', models.TextField(blank=True, default='')),
                ('used_for_write', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('source', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='provenance', to='asnserial.sourceevidence')),
                ('source_extraction', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='provenance', to='asnserial.sourceextraction')),
            ],
            options={
                'db_table': 'entityprovenance',
                'ordering': ['id'],
            },
        ),
        migrations.AddField(
            model_name='agentcommandpreview',
            name='execution_surface',
            field=models.CharField(default='CLI', max_length=16),
        ),
        migrations.AddField(
            model_name='agentcommandpreview',
            name='source_evidence',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='previews', to='asnserial.sourceevidence'),
        ),
        migrations.AlterField(
            model_name='agentcommandpreview',
            name='confirmation_token_hash',
            field=models.CharField(blank=True, default='', max_length=64),
        ),
        migrations.CreateModel(
            name='OperationAudit',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('openid', models.CharField(max_length=255)),
                ('operation', models.CharField(max_length=64)),
                ('execution_surface', models.CharField(max_length=16)),
                ('status', models.CharField(max_length=16)),
                ('operator_id', models.CharField(blank=True, default='', max_length=255)),
                ('operator_name', models.CharField(blank=True, default='', max_length=255)),
                ('operator_role', models.CharField(blank=True, default='', max_length=64)),
                ('ai_session_id', models.CharField(blank=True, default='', max_length=255)),
                ('payload_hash', models.CharField(blank=True, default='', max_length=64)),
                ('result', models.JSONField(default=dict)),
                ('failure_reason', models.TextField(blank=True, default='')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('approved_at', models.DateTimeField(blank=True, null=True)),
                ('preview', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='operation_audits', to='asnserial.agentcommandpreview')),
                ('source_evidence', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='operation_audits', to='asnserial.sourceevidence')),
            ],
            options={
                'db_table': 'operationaudit',
                'ordering': ['-created_at', '-id'],
            },
        ),
        migrations.AddIndex(
            model_name='sourceevidence',
            index=models.Index(fields=['openid', 'operation', 'captured_at'], name='sourceevide_openid_086f98_idx'),
        ),
        migrations.AddIndex(
            model_name='sourceevidence',
            index=models.Index(fields=['openid', 'content_hash'], name='sourceevide_openid_2e50e6_idx'),
        ),
        migrations.AddIndex(
            model_name='sourceextraction',
            index=models.Index(fields=['source', 'field_name'], name='sourceextra_source__4236ad_idx'),
        ),
        migrations.AddIndex(
            model_name='operationaudit',
            index=models.Index(fields=['openid', 'operation', 'created_at'], name='operationau_openid_43348e_idx'),
        ),
        migrations.AddIndex(
            model_name='operationaudit',
            index=models.Index(fields=['openid', 'execution_surface', 'status'], name='operationau_openid_e5ddf3_idx'),
        ),
    ]
