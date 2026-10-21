
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('introduction', '0019_af_admin'),
    ]

    operations = [
        migrations.CreateModel(
            name='AF_session_id',
            fields=[
                ('id', models.AutoField(primary_key=True, serialize=False)),
                ('session_id', models.CharField(max_length=200)),
                ('user', models.CharField(max_length=200)),
            ],
        ),
        migrations.AlterField(
            model_name='af_admin',
            name='lockout_cooldown',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
