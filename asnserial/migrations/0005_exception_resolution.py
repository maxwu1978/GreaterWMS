from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('asnserial', '0004_packlistdocument_source_sha256'),
    ]

    operations = [
        migrations.AddField(
            model_name='asnserialrecord',
            name='exception_resolved',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='asnserialrecord',
            name='exception_resolution_action',
            field=models.CharField(blank=True, default='', max_length=64),
        ),
        migrations.AddField(
            model_name='asnserialrecord',
            name='exception_resolution_note',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AddField(
            model_name='asnserialrecord',
            name='exception_resolved_by',
            field=models.CharField(blank=True, default='', max_length=255),
        ),
        migrations.AddField(
            model_name='asnserialrecord',
            name='exception_resolved_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
