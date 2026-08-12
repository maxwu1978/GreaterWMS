from django.db import migrations, models
from django.db.models import Q
import django.db.models.deletion


def mark_one_current_pack_list(apps, schema_editor):
    document_model = apps.get_model('asnserial', 'PackListDocument')
    line_model = apps.get_model('asnserial', 'PackListLine')
    keys = document_model.objects.values('openid', 'asn_code').distinct()
    for key in keys:
        documents = document_model.objects.filter(
            openid=key['openid'],
            asn_code=key['asn_code'],
        )
        current = documents.filter(status='CONFIRMED').order_by('-version', '-id').first()
        if current is None:
            current = documents.order_by('id').first()
        if current is None:
            continue
        archived = documents.exclude(id=current.id)
        archived.update(is_current=False, status='ARCHIVED')
        line_model.objects.filter(pack_list__in=archived).update(is_current=False)
        if not current.is_current:
            current.is_current = True
            current.save(update_fields=['is_current'])


class Migration(migrations.Migration):
    dependencies = [
        ('asnserial', '0005_exception_resolution'),
    ]

    operations = [
        migrations.CreateModel(
            name='PackListImportBatch',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('openid', models.CharField(max_length=255)),
                ('asn_code', models.CharField(max_length=255)),
                ('import_type', models.CharField(choices=[('PACK_LIST', 'Pack List'), ('RECEIVING_ACCEPTANCE', 'Receiving acceptance')], max_length=32)),
                ('content_hash', models.CharField(blank=True, default='', max_length=64)),
                ('row_count', models.PositiveIntegerField(default=0)),
                ('imported_by', models.CharField(blank=True, default='', max_length=255)),
                ('note', models.TextField(blank=True, default='')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'db_table': 'packlistimportbatch',
                'ordering': ['-created_at', '-id'],
            },
        ),
        migrations.RemoveIndex(
            model_name='packlistdocument',
            name='packlistdoc_openid_3f1a68_idx',
        ),
        migrations.RenameField(
            model_name='packlistdocument',
            old_name='source_sha256',
            new_name='content_hash',
        ),
        migrations.RemoveField(
            model_name='packlistdocument',
            name='source_file',
        ),
        migrations.RemoveField(
            model_name='packlistdocument',
            name='source_url',
        ),
        migrations.RemoveField(
            model_name='packlistdocument',
            name='raw_payload',
        ),
        migrations.RemoveField(
            model_name='asnserialrecord',
            name='source_file',
        ),
        migrations.AddField(
            model_name='packlistdocument',
            name='is_current',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='packlistdocument',
            name='import_batch',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='pack_lists', to='asnserial.packlistimportbatch'),
        ),
        migrations.AddField(
            model_name='asnserialrecord',
            name='import_batch',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='serial_records', to='asnserial.packlistimportbatch'),
        ),
        migrations.AddField(
            model_name='packlistline',
            name='is_current',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='packlistline',
            name='customer_ssku',
            field=models.CharField(blank=True, default='', max_length=255),
        ),
        migrations.AddField(
            model_name='packlistline',
            name='package_type',
            field=models.CharField(blank=True, default='', max_length=255),
        ),
        migrations.AddField(
            model_name='packlistline',
            name='total_qty',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddIndex(
            model_name='packlistimportbatch',
            index=models.Index(fields=['openid', 'asn_code', 'import_type'], name='packlistimp_openid_e820b7_idx'),
        ),
        migrations.AddIndex(
            model_name='packlistimportbatch',
            index=models.Index(fields=['openid', 'import_type', 'content_hash'], name='packlistimp_openid_5f01ee_idx'),
        ),
        migrations.AddIndex(
            model_name='packlistdocument',
            index=models.Index(fields=['openid', 'asn_code', 'content_hash'], name='packlistdoc_openid_e6021e_idx'),
        ),
        migrations.RunPython(mark_one_current_pack_list, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name='packlistdocument',
            constraint=models.UniqueConstraint(condition=Q(is_current=True), fields=('openid', 'asn_code'), name='packlistdocument_one_current_per_asn'),
        ),
    ]
