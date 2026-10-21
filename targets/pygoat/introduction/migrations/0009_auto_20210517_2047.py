
import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('introduction', '0008_otp'),
    ]

    operations = [
        migrations.AlterField(
            model_name='otp',
            name='otp',
            field=models.IntegerField(validators=[django.core.validators.MaxValueValidator(300)]),
        ),
    ]
