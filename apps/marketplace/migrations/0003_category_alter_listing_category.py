import django.db.models.deletion
from django.db import migrations, models


def clear_bad_category_data(apps, schema_editor):
    # Use raw SQL to bypass Django's ORM constraint checks
    schema_editor.execute(
        "ALTER TABLE marketplace_listing ALTER COLUMN category DROP NOT NULL"
    )
    schema_editor.execute(
        "UPDATE marketplace_listing SET category = NULL"
    )


class Migration(migrations.Migration):

    dependencies = [
        ('marketplace', '0002_listing_category'),
    ]

    operations = [
        migrations.CreateModel(
            name='Category',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100, unique=True)),
            ],
            options={
                'verbose_name_plural': 'Categories',
                'ordering': ['name'],
            },
        ),
        migrations.RunPython(clear_bad_category_data, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='listing',
            name='category',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='listings', to='marketplace.category'),
        ),
    ]