
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('introduction', '0002_auto_20210414_1510'),
    ]

    operations = [
        migrations.CreateModel(
            name='user',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('user', models.CharField(max_length=200)),
            ],
        ),
        migrations.CreateModel(
            name='password',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('password', models.CharField(max_length=300)),
                ('username', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='introduction.user')),
            ],
        ),
    ]
