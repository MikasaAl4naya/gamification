# Generated by Django 4.2.10 on 2024-04-16 04:31

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0034_testquestion_position_alter_theory_position'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='theory',
            name='question',
        ),
    ]
