
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('introduction', '0003_password_user'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='password',
            field=models.CharField(default=0, max_length=300),
            preserve_default=False,
        ),
        migrations.DeleteModel(
            name='password',
        ),
    ]
