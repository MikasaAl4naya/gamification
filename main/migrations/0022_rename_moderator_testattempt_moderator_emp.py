# Generated by Django 4.2.10 on 2024-05-22 03:35

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0021_alter_testattempt_status'),
    ]

    operations = [
        migrations.RenameField(
            model_name='testattempt',
            old_name='moderator',
            new_name='moderator_emp',
        ),
    ]
