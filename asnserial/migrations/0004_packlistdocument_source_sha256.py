from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('asnserial', '0003_packlistdocument_package_qty'),
    ]

    operations = [
        migrations.AddField(
            model_name='packlistdocument',
            name='source_sha256',
            field=models.CharField(blank=True, default='', max_length=64),
        ),
        migrations.AddIndex(
            model_name='packlistdocument',
            index=models.Index(
                fields=['openid', 'asn_code', 'source_sha256'],
                name='packlistdoc_openid_3f1a68_idx',
            ),
        ),
    ]
