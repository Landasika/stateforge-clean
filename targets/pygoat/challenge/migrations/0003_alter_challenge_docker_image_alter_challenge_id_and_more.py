
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('challenge', '0002_challenge_docker_port'),
    ]

    operations = [
        migrations.AlterField(
            model_name='challenge',
            name='docker_image',
            field=models.CharField(max_length=100, unique=True),
        ),
        migrations.AlterField(
            model_name='challenge',
            name='id',
            field=models.AutoField(primary_key=True, serialize=False, unique=True),
        ),
        migrations.AlterField(
            model_name='challenge',
            name='name',
            field=models.CharField(max_length=100, unique=True),
        ),
    ]
