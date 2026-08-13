from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('asnserial', '0010_agentcommandpreview'),
    ]

    operations = [
        migrations.AddField(
            model_name='asnserialrecord',
            name='exception_moved',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='asnserialrecord',
            name='exception_move_bin',
            field=models.CharField(blank=True, default='', max_length=255),
        ),
        migrations.AddField(
            model_name='asnserialrecord',
            name='exception_moved_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
