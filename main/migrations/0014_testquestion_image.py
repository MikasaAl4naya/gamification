# Generated by Django 4.2.10 on 2024-04-02 03:36

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0013_remove_acoin_user_remove_acointransaction_user_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='testquestion',
            name='image',
            field=models.ImageField(blank=True, null=True, upload_to='question_images/'),
        ),
    ]
