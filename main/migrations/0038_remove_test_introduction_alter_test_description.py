# Generated by Django 4.2.10 on 2024-04-17 05:15

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0037_rename_allow_retake_test_send_results_to_email'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='test',
            name='introduction',
        ),
        migrations.AlterField(
            model_name='test',
            name='description',
            field=models.TextField(blank=True, null=True),
        ),
    ]