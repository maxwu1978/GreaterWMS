from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('asnserial', '0006_single_current_packlist_and_import_batches'),
    ]

    operations = [
        migrations.AlterField(
            model_name='packlistimportbatch',
            name='import_type',
            field=models.CharField(
                choices=[
                    ('PACK_LIST', 'Pack List'),
                    ('EXPECTED_SERIALS', 'Expected serials'),
                    ('RECEIVING_ACCEPTANCE', 'Receiving acceptance'),
                ],
                max_length=32,
            ),
        ),
        migrations.AddField(
            model_name='packlistimportbatch',
            name='accepted_count',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='packlistimportbatch',
            name='exception_count',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='packlistimportbatch',
            name='matched_count',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='packlistimportbatch',
            name='source_type',
            field=models.CharField(blank=True, default='UPLOAD', max_length=32),
        ),
        migrations.AddField(
            model_name='packlistimportbatch',
            name='status',
            field=models.CharField(
                choices=[
                    ('IMPORTED', 'Imported'),
                    ('PASSED', 'Passed'),
                    ('EXCEPTION', 'Exception'),
                    ('PARTIAL', 'Partial'),
                ],
                default='IMPORTED',
                max_length=32,
            ),
        ),
        migrations.AddField(
            model_name='packlistdocument',
            name='late_reference',
            field=models.BooleanField(default=False),
        ),
    ]
