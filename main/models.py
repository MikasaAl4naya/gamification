import logging
from urllib.request import Request

from django.contrib.auth.models import AbstractUser, Group, Permission
from django.db import models
from django.core.validators import EmailValidator, MinValueValidator
from django.core.exceptions import ValidationError
import re

from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

logger = logging.getLogger(__name__)

def validate_custom_email(value):
    email_regex = r"^[a-z]+\.[a-z]+@autotrade\.su$"
    if not re.match(email_regex, value):
        raise ValidationError("Email должен быть в формате 'имя.фамилия@autotrade.su'")

class Medal(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField()

class Employee(AbstractUser):
    email = models.EmailField(validators=[EmailValidator(), validate_custom_email])
    position = models.CharField(max_length=100)
    level = models.IntegerField(default=1)
    experience = models.IntegerField(default=0)
    balance = models.IntegerField(default=0)
    next_level_experience = models.IntegerField(default=100)  # Опыт, необходимый для перехода на следующий уровень

    def increase_experience(self, amount):
        self.experience += amount
        if self.experience >= self.next_level_experience:
            self.level_up()

    def level_up(self):
        self.level += 1
        self.experience -= self.next_level_experience
        self.next_level_experience *= 2
        while self.experience >= self.next_level_experience:
            self.level += 1
            self.experience -= self.next_level_experience
            self.next_level_experience *= 2
        self.save()

    class Meta:
        # Указываем пространство имен для связи
        # Это позволит Django различать обратные связи
        # между моделями Employee и User
        app_label = 'main'

    # Решаем конфликт имен для связи с моделью Group
    groups = models.ManyToManyField(
        Group,
        verbose_name='groups',
        blank=True,
        related_name='employee_groups',
        related_query_name='employee_group',
    )

    # Решаем конфликт имен для связи с моделью Permission
    user_permissions = models.ManyToManyField(
        Permission,
        verbose_name='user permissions',
        blank=True,
        related_name='employee_permissions',
        related_query_name='employee_permission',
    )


class Classifications(models.Model):
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name

class Achievement(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField()
    request_type = models.ForeignKey(Classifications, on_delete=models.CASCADE)
    required_count = models.IntegerField()
    reward_experience = models.IntegerField()
    reward_currency = models.IntegerField()
    image = models.ImageField(upload_to='achievements/', default='default.jpg')

    def __str__(self):
        return self.name


    def level_up(self):
        # Повышаем уровень ачивки и обновляем требуемое количество и награду
        self.required_count = int(self.required_count * 1.5)
        self.reward_experience = int(self.reward_experience * 1.5)
        self.save()

class Item(models.Model):
    description = models.CharField(max_length=100)
    price = models.IntegerField()


class Request(models.Model):
    STATUS_CHOICES = [
        ('Registered', 'Зарегистрировано'),
        ('In Progress', 'В работе'),
        ('Returned', 'Возвращено'),
        ('Forwarded to Second Line', 'Передано на вторую линию'),
        ('Forwarded to Third Line', 'Передано на третью линию'),
        ('Completed', 'Завершено'),
    ]

    classification = models.ForeignKey(Classifications, on_delete=models.CASCADE)
    responsible = models.ForeignKey(Employee, on_delete=models.CASCADE)
    status = models.CharField(max_length=100, choices=STATUS_CHOICES)


@receiver(post_save, sender=Request)
def update_achievement_progress(sender, instance, **kwargs):
    if instance.status == 'Completed':
        try:
            achievement = Achievement.objects.get(request_type=instance.classification)
        except Achievement.DoesNotExist:
            return

        employee_achievement, created = EmployeeAchievement.objects.get_or_create(
            employee=instance.responsible,
            achievement=achievement
        )
        employee_achievement.increment_progress()
        employee_achievement.save()
        print(employee_achievement)


class EmployeeItem(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE)
    item = models.ForeignKey(Item, on_delete=models.CASCADE)

class EmployeeAchievement(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE)
    achievement = models.ForeignKey(Achievement, on_delete=models.CASCADE)
    progress = models.IntegerField(default=0)  # Прогресс выполнения ачивки для сотрудника

    # Метод increment_progress модели EmployeeAchievement
    def increment_progress(self):
        self.progress += 1
        if self.progress >= self.achievement.required_count:
            # Если достигнут требуемый прогресс, обновляем ачивку
            self.achievement.level_up()  # Повышаем уровень ачивки
            self.progress = 0  # Сбрасываем прогресс

            # Прибавляем опыт и валюту сотруднику
            self.employee.increase_experience(self.achievement.reward_experience)
            self.employee.balance += self.achievement.reward_currency
            self.employee.save()
class EmployeeMedal(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE)
    medal = models.ForeignKey(Medal, on_delete=models.CASCADE)

    class Meta:
        unique_together = ('employee', 'medal')


class Test(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField()
    required_experience = models.IntegerField()
    required_karma_percentage = models.IntegerField()

class TestQuestion(models.Model):
    test = models.ForeignKey(Test, on_delete=models.CASCADE)
    question_text = models.TextField()
    question_type = models.CharField(max_length=50, choices=[("Multiple Choice", "Multiple Choice"), ("Free Response", "Free Response")])
    explanation = models.TextField(null=True, blank=True)

class TestAttempt(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE)
    test = models.ForeignKey(Test, on_delete=models.CASCADE)
    start_time = models.DateTimeField(default=timezone.now)
    end_time = models.DateTimeField(null=True, blank=True)
    is_completed = models.BooleanField(default=False)
    selected_answer = models.CharField(max_length=255, null=True, blank=True)
    free_response = models.TextField(null=True, blank=True)
    is_correct = models.BooleanField(default=False)
    explanation = models.TextField(null=True, blank=True)