# Generated by Django 4.2.10 on 2024-03-15 04:27

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0004_remove_testattempt_explanation_employee_karma_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='testquestion',
            name='question_type',
            field=models.CharField(choices=[('MC', 'Multiple Choice'), ('SC', 'Single Choice'), ('FR', 'Free Response')], default='SC', max_length=2),
        ),
        migrations.CreateModel(
            name='AnswerOption',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('option_text', models.TextField()),
                ('is_correct', models.BooleanField(default=False)),
                ('question', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='main.testquestion')),
            ],
        ),
    ]
