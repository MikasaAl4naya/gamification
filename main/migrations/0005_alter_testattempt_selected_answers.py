# Generated by Django 4.2.10 on 2024-04-23 09:13

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0004_alter_testattempt_score'),
    ]

    operations = [
        migrations.AlterField(
            model_name='testattempt',
            name='selected_answers',
            field=models.ManyToManyField(related_name='selected_answers', to='main.answeroption'),
        ),
    ]
