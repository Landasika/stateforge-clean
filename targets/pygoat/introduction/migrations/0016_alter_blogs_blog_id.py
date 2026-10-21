
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('introduction', '0015_blogs'),
    ]

    operations = [
        migrations.AlterField(
            model_name='blogs',
            name='blog_id',
            field=models.CharField(max_length=15, unique=True),
        ),
    ]
