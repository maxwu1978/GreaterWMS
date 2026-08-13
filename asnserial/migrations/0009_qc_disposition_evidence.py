from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('asnserial', '0008_packlistdocument_ai_agent_source'),
    ]

    operations = [
        migrations.AddField(
            model_name='asnserialrecord',
            name='evidence_url',
            field=models.CharField(blank=True, default='', max_length=1000),
        ),
        migrations.AddField(
            model_name='asnserialrecord',
            name='exception_resolution_location',
            field=models.CharField(blank=True, default='', max_length=255),
        ),
        migrations.AddField(
            model_name='packlistimportbatch',
            name='evidence_url',
            field=models.CharField(blank=True, default='', max_length=1000),
        ),
    ]
