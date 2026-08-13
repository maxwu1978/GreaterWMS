from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('asnserial', '0007_late_packlist_and_inspection_batch'),
    ]

    operations = [
        migrations.AlterField(
            model_name='packlistimportbatch',
            name='source_type',
            field=models.CharField(blank=True, default='AI_AGENT', max_length=32),
        ),
        migrations.AlterField(
            model_name='packlistdocument',
            name='source_type',
            field=models.CharField(
                choices=[
                    ('AI_AGENT', 'AI Agent'),
                    ('UPLOAD', 'Uploaded file'),
                    ('EMAIL', 'Email attachment'),
                    ('GOOGLE_DRIVE', 'Google Drive'),
                    ('MANUAL', 'Manual entry'),
                ],
                default='AI_AGENT',
                max_length=32,
            ),
        ),
    ]
