# Generated by Django 4.2.10 on 2024-04-26 05:38

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0009_test_retry_delay_days'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='testattempt',
            name='submitted_answers',
        ),
        migrations.RemoveField(
            model_name='testattempt',
            name='submitted_questions',
        ),
        migrations.AddField(
            model_name='testattempt',
            name='test_results',
            field=models.JSONField(blank=True, null=True),
        ),
    ]