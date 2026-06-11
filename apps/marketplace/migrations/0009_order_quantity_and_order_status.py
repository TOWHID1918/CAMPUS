from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("marketplace", "0008_listing_stock"),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name="negotiationthread",
            unique_together=set(),
        ),
        migrations.AlterUniqueTogether(
            name="purchaserequest",
            unique_together=set(),
        ),
        migrations.AddField(
            model_name="negotiationthread",
            name="quantity",
            field=models.PositiveIntegerField(default=1),
        ),
        migrations.AddField(
            model_name="negotiationthread",
            name="is_order",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="purchaserequest",
            name="quantity",
            field=models.PositiveIntegerField(default=1),
        ),
    ]
