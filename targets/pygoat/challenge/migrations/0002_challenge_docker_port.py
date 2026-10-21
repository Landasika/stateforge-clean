
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('challenge', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='challenge',
            name='docker_port',
            field=models.IntegerField(default=8000),
            preserve_default=False,
        ),
    ]
