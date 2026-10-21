
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('introduction', '0004_auto_20210415_1722'),
    ]

    operations = [
        migrations.RenameModel(
            old_name='user',
            new_name='login',
        ),
    ]
