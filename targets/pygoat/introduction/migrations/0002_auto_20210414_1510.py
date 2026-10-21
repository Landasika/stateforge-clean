
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('introduction', '0001_initial'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='faang',
            name='about',
        ),
        migrations.RemoveField(
            model_name='faang',
            name='ceo',
        ),
        migrations.CreateModel(
            name='info',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('ceo', models.CharField(max_length=200)),
                ('about', models.CharField(max_length=200)),
                ('faang', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='introduction.FAANG')),
            ],
        ),
    ]
