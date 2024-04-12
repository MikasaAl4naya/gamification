import logging
from urllib.request import Request

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractUser, Group, Permission, User
from django.db import models
from django.core.validators import EmailValidator, MinValueValidator
from django.core.exceptions import ValidationError
import re

from django.db.models.signals import post_save, post_delete
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
    next_level_experience = models.IntegerField(default=100)
    karma = models.IntegerField(default=50)

    def save(self, *args, **kwargs):
        # Проверяем, чтобы значение кармы не превышало максимальное значение
        if self.karma > 100:
            self.karma = 100
        super().save(*args, **kwargs)
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

    # Метод add_experience для модели Employee
    def add_experience(self, experience):
        if experience is not None:
            self.experience += experience
            self.save()

    # Метод add_acoins для модели Employee
    def add_acoins(self, acoins):
        if acoins is not None:
            # Создаем транзакцию для начисления Акоинов
            AcoinTransaction.objects.create(employee=self, amount=acoins)

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
    def add_achievement(self, achievement):
        self.achievements.add(achievement)

class Classifications(models.Model):
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name

class Achievement(models.Model):
    TYPE_CHOICES = [
        ('Test', 'За тест'),
        ('Requests', 'За количество обращений'),
        # Другие типы достижений здесь
    ]
    name = models.CharField(max_length=100)
    description = models.TextField()
    type = models.CharField(max_length=100, choices=TYPE_CHOICES, default='Test')
    request_type = models.ForeignKey(Classifications, on_delete=models.CASCADE, null=True, blank=True)
    required_count = models.IntegerField(null=True, blank=True)
    reward_experience = models.IntegerField(null=True, blank=True)
    reward_currency = models.IntegerField(null=True, blank=True)
    image = models.ImageField(upload_to='achievements/', default='default.jpg')
    max_level = models.IntegerField(default=3)
    def __str__(self):
        return self.name


    def clean(self):
        # Если тип ачивки не Test, убедитесь, что все поля заполнены
        if self.type == 'За количество обращений':
            if not self.request_type:
                raise ValidationError('Field request_type is required for achievements based on number of requests.')
            if self.required_count is None:
                raise ValidationError('Field required_count is required for achievements based on number of requests.')
            if self.reward_experience is None:
                raise ValidationError(
                    'Field reward_experience is required for achievements based on number of requests.')
            if self.reward_currency is None:
                raise ValidationError('Field reward_currency is required for achievements based on number of requests.')

        if self.type != 'Test':
            if self.reward_experience is None:
                raise ValidationError('Field reward_experience is required for non-test achievements.')
            if self.reward_currency is None:
                raise ValidationError('Field reward_currency is required for non-test achievements.')

    def level_up(self):
        if self.level >= self.max_level:
            raise ValidationError("Maximum level reached for this achievement")
        self.required_count = int(self.required_count * 1.5)
        self.reward_experience = int(self.reward_experience * 1.5)
        self.save()

    def save(self, *args, **kwargs):
        if self.type == 'Test':
            self.max_level = 1
        else:
            self.max_level = 3
        super().save(*args, **kwargs)

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
class Acoin(models.Model):
    employee = models.OneToOneField(Employee, on_delete=models.CASCADE, blank=False, null=True)
    amount = models.IntegerField(default=0)

class AcoinTransaction(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, blank=False, null=True)
    amount = models.IntegerField(default=0)
    timestamp = models.DateTimeField(auto_now_add=True)

    @classmethod
    def create_from_achievement(cls, employee, achievement):
        transaction = cls(employee=employee, amount=achievement.reward_currency)
        transaction.save()
        return transaction
@receiver(post_save, sender=Employee)
def create_acoin(sender, instance, created, **kwargs):
    if created:
        Acoin.objects.create(employee=instance, amount=0)

@receiver(post_save, sender=AcoinTransaction)
def update_acoin_balance(sender, instance, created, **kwargs):
    if created:
        # Обновляем баланс акоинов сотрудника в таблице Acoin
        acoin, created = Acoin.objects.get_or_create(employee=instance.employee)
        acoin.amount += instance.amount
        acoin.save()

class EmployeeItem(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE)
    item = models.ForeignKey(Item, on_delete=models.CASCADE)


class EmployeeAchievement(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE)
    achievement = models.ForeignKey(Achievement, on_delete=models.CASCADE)
    progress = models.IntegerField(default=0)
    level = models.IntegerField(default=0)

    def increment_progress(self):
        self.progress += 1
        if self.achievement.required_count is not None and self.progress >= self.achievement.required_count:
            self.level_up()

    def level_up(self):
        # Повышаем уровень ачивки
        if self.level >= self.achievement.max_level:
            return
        else:
            self.level += 1
            # Проверяем, что required_count и reward_experience не являются None
            if self.achievement.required_count is not None:
                self.achievement.required_count = int(self.achievement.required_count * 1.5)
            if self.achievement.reward_experience is not None:
                self.achievement.reward_experience = int(self.achievement.reward_experience * 1.5)
            # Сохраняем изменения в модели ачивки
            self.achievement.save()
            # Начисляем награды сотруднику
            self.reward_employee()

    def reward_employee(self):
        # Получаем сотрудника
        employee = self.employee
        # Получаем награды за текущий уровень ачивки
        reward_currency = self.achievement.reward_currency
        reward_experience = self.achievement.reward_experience
        # Начисляем награды сотруднику
        # Например, добавляем опыт и акоины
        employee.add_experience(reward_experience)
        employee.add_acoins(reward_currency)

        # Сбрасываем прогресс
        self.progress = 0
        self.save()




class EmployeeMedal(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE)
    medal = models.ForeignKey(Medal, on_delete=models.CASCADE)

    class Meta:
        unique_together = ('employee', 'medal')




class Test(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField()
    introduction = models.TextField(blank=True, null=True)  # Введение в тест
    duration_seconds = models.PositiveIntegerField(default=3600)  # Время в секундах
    passing_score = models.PositiveIntegerField(default=70)
    unlimited_time = models.BooleanField(default=False)  # Флаг для неограниченного времени
    show_correct_answers = models.BooleanField(default=False)  # Показывать правильные ответы
    allow_retake = models.BooleanField(default=False)  # Разрешить повторное прохождение
    theme = models.CharField(max_length=255, blank=True)  # Тема теста
    can_attempt_twice= models.BooleanField(default=False)
    required_karma = models.IntegerField(default=0)  # Необходимое количество кармы для прохождения
    score = models.PositiveIntegerField(default=0)  # Количество баллов за прохождение
    experience_points = models.PositiveIntegerField(default=0)  # Количество опыта за прохождение
    acoin_reward = models.PositiveIntegerField(default=0)  # Количество акоинов за прохождение
    min_level = models.PositiveIntegerField(default=1)  # Минимальный уровень для прохождения теста
    achievement = models.ForeignKey(Achievement, on_delete=models.SET_NULL, null=True, blank=True)
    total_questions = models.PositiveIntegerField(default=0)

    def clean(self):
        # Убеждаемся, что тип ачивки всегда "Test"
        if self.achievement:
            if self.achievement.type != 'Test':
                raise ValidationError('Achievement type must be "Test".')

    def save(self, *args, **kwargs):
        # Убеждаемся, что тип ачивки всегда "Test"
        if self.achievement:
            if self.achievement.type != 'Test':
                raise ValidationError('Achievement type must be "Test".')
        super().save(*args, **kwargs)


class TestQuestion(models.Model):
    TEXT = 'text'
    SINGLE = 'single'
    MULTIPLE = 'multiple'
    QUESTION_TYPE_CHOICES = [
        (TEXT, 'Text'),
        (SINGLE, 'Single Choice'),
        (MULTIPLE, 'Multiple Choice'),
    ]
    test = models.ForeignKey(Test, on_delete=models.CASCADE)
    question_text = models.TextField()
    question_type = models.CharField(max_length=10, choices=QUESTION_TYPE_CHOICES)
    points = models.PositiveIntegerField(default=1)  # Количество баллов за правильный ответ на вопрос
    explanation = models.TextField(blank=True, null=True)  # Пояснение к вопросу
    image = models.CharField(max_length=255, blank=True, null=True)  # Поле для хранения пути к изображению
    duration_seconds = models.PositiveIntegerField(default=0)  # Ограничение по времени в секундах
@receiver(post_save, sender=TestQuestion)
@receiver(post_delete, sender=TestQuestion)
def update_total_questions(sender, instance, **kwargs):
    # Получаем тест, к которому привязан вопрос
    test = instance.test

    # Получаем общее количество вопросов для этого теста
    total_questions = TestQuestion.objects.filter(test=test).count()

    # Обновляем поле total_questions в модели Test
    Test.objects.filter(pk=test.pk).update(total_questions=total_questions)
class Theory(models.Model):
    BEFORE = 'before'
    AFTER = 'after'
    POSITION_CHOICES = [
        (BEFORE, 'Before questions'),
        (AFTER, 'After questions'),
    ]

    text = models.TextField()
    image= models.CharField( max_length=255, blank=True, null=True)  # Поле для хранения пути к изображению
    test = models.ForeignKey(Test, on_delete=models.CASCADE)
    question = models.ForeignKey(TestQuestion, on_delete=models.CASCADE, null=True, blank=True)
    position = models.CharField(max_length=10, choices=POSITION_CHOICES, default=BEFORE)

class AnswerOption(models.Model):
    question = models.ForeignKey(TestQuestion, on_delete=models.CASCADE, related_name='answer_options')
    option_text = models.CharField(max_length=255)
    is_correct = models.BooleanField(default=False)
    file = models.FileField(upload_to='answer_files/', null=True, blank=True)

    def clean(self):
        # Проверяем тип вопроса
        question_type = self.question.question_type

        # Если тип вопроса SINGLE, то должен быть ровно 1 правильный ответ
        if question_type == TestQuestion.SINGLE:
            correct_answers = self.question.answer_options.filter(is_correct=True).count()
            if correct_answers > 1:
                raise ValidationError("For single choice question, only one correct answer is allowed.")

        # Если тип вопроса MULTIPLE, то должно быть больше 1 правильного ответа
        elif question_type == TestQuestion.MULTIPLE:
            correct_answers = self.question.answer_options.filter(is_correct=True).count()
            if correct_answers < 2:
                raise ValidationError("For multiple choice question, at least two correct answers are required.")

        # Если тип вопроса TEXT, то вариантов ответа быть не должно
        elif question_type == TestQuestion.TEXT:
            if self.option_text.strip() != "":
                raise ValidationError("For text-based question, no answer options should be provided.")


class TestAttempt(models.Model):
    # Константы для статусов прохождения теста
    PASSED = 'Passed'
    NOT_STARTED = 'Not Started'
    IN_PROGRESS = 'In Progress'
    FAILED = 'Failed'
    STATUS_CHOICES = [
        (PASSED, 'Пройден'),
        (NOT_STARTED, 'Не начат'),
        (IN_PROGRESS, 'В процессе'),
        (FAILED, 'Не пройден')
    ]

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE)
    test = models.ForeignKey(Test, on_delete=models.CASCADE)
    start_time = models.DateTimeField(default=timezone.now)
    end_time = models.DateTimeField(null=True, blank=True)
    attempts = models.IntegerField(default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=NOT_STARTED)
    selected_answers = models.ManyToManyField(AnswerOption)
    free_response = models.TextField(null=True, blank=True)
    is_correct = models.BooleanField(default=False)


    def save(self, *args, **kwargs):
        # Проверяем, существует ли уже попытка прохождения этого теста этим сотрудником
        existing_attempt = TestAttempt.objects.filter(employee=self.employee, test=self.test).last()
        if existing_attempt:
            if existing_attempt.attempts > 0:
                self.attempts = existing_attempt.attempts - 1
            else:
                raise ValidationError("No attempts left for this test")
        else:
            self.attempts = 1 if self.test.can_attempt_twice else 0
        super().save(*args, **kwargs)

    def submit_test(self):
        if self.status != self.PASSED and self.status != self.FAILED:
            self.status = self.IN_PROGRESS
        self.is_completed = True
        self.save()

        # Создаем транзакцию для начисления акоинов, если тест пройден успешно
        if self.status == self.PASSED:
            acoin_reward = self.test.acoin_reward
            AcoinTransaction.objects.create(employee=self.employee, amount=acoin_reward)


class TestAttemptQuestionExplanation(models.Model):
    test_attempt = models.ForeignKey(TestAttempt, on_delete=models.CASCADE)
    test_question = models.ForeignKey(TestQuestion, on_delete=models.CASCADE)
    explanation = models.TextField()

    class Meta:
        unique_together = ('test_attempt', 'test_question')
@receiver(post_save, sender=TestAttempt)
def create_acoin_transaction(sender, instance, created, **kwargs):
    if created and instance.status == TestAttempt.PASSED:
        # Получаем количество акоинов за прохождение теста
        acoin_reward = instance.test.acoin_reward
        # Создаем транзакцию для сотрудника, который получил ачивку за тест
        AcoinTransaction.objects.create(employee=instance.employee, amount=acoin_reward)
        # Получаем количество опыта за прохождение теста
        experience_reward = instance.test.experience_points
        # Начисляем опыт сотруднику
        instance.employee.add_experience(experience_reward)



