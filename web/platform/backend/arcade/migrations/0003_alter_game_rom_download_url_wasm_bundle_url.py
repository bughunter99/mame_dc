from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("arcade", "0002_playsession"),
    ]

    operations = [
        migrations.AlterField(
            model_name="game",
            name="rom_download_url",
            field=models.CharField(max_length=500),
        ),
        migrations.AlterField(
            model_name="game",
            name="wasm_bundle_url",
            field=models.CharField(max_length=500),
        ),
    ]
