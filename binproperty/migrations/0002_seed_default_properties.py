from django.db import migrations


DEFAULT_PROPERTIES = ('Normal', 'Holding', 'Damage', 'Inspection')


def seed_default_properties(apps, schema_editor):
    BinProperty = apps.get_model('binproperty', 'ListModel')
    for property_name in DEFAULT_PROPERTIES:
        BinProperty.objects.get_or_create(
            openid='init_data',
            bin_property=property_name,
            defaults={'creater': 'System'},
        )


class Migration(migrations.Migration):
    dependencies = [
        ('binproperty', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(seed_default_properties, migrations.RunPython.noop),
    ]
