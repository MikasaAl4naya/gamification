# Generated by Django 4.2.10 on 2024-04-05 03:03

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0028_test_can_attempt_twice'),
    ]

    operations = [
        migrations.AlterField(
            model_name='testattempt',
            name='attempts',
            field=models.IntegerField(default=0),
        ),
    ]
