# Generated by Django 4.2.10 on 2024-04-25 04:31

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0008_remove_testattempt_selected_answers_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='test',
            name='retry_delay_days',
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
    ]