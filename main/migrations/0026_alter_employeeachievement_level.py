# Generated by Django 4.2.10 on 2024-04-04 05:02

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0025_alter_acointransaction_amount'),
    ]

    operations = [
        migrations.AlterField(
            model_name='employeeachievement',
            name='level',
            field=models.IntegerField(default=0),
        ),
    ]