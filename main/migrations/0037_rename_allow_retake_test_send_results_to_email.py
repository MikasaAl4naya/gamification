# Generated by Django 4.2.10 on 2024-04-17 04:12

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0036_theory_title'),
    ]

    operations = [
        migrations.RenameField(
            model_name='test',
            old_name='allow_retake',
            new_name='send_results_to_email',
        ),
    ]