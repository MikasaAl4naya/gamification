import logging
from django.contrib.auth.models import AbstractUser, Group, Permission, User
from django.db import models, transaction
from django.core.validators import EmailValidator, MinValueValidator
from django.core.exceptions import ValidationError
import re

from django.db.models.signals import post_save, post_delete, pre_delete
from django.dispatch import receiver
from django.utils import timezone

from gamefication import settings

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
    birth_date = models.DateField(null=True, blank=True)
    about_me = models.TextField(null=True, blank=True)
    avatar = models.ImageField(upload_to='avatars/', null=True, blank=True)
    status = models.CharField(max_length=100, null=True, blank=True)
    last_karma_update = models.DateTimeField(null=True, blank=True)

    def deactivate(self):
        self.is_active = False
        self.force_save = True
        self.save()

    def delete_employee(self):
        self.delete()

    def activate(self):
        self.is_active = True
        self.force_save = True
        self.save()

    def save(self, *args, **kwargs):
        if not self.is_active and not getattr(self, 'force_save', False):
            raise ValidationError("Cannot modify a deactivated account.")
        if self.karma > 100:
            self.karma = 100
        super().save(*args, **kwargs)

    def increase_experience(self, amount):
        if not self.is_active:
            raise ValidationError("Cannot modify a deactivated account.")
        self.experience += amount
        if self.experience >= self.next_level_experience:
            self.level_up()

    def level_up(self):
        if not self.is_active:
            raise ValidationError("Cannot modify a deactivated account.")
        self.level += 1
        experience_multiplier = 2.0 - (self.level * 0.1)
        if experience_multiplier < 1.0:
            experience_multiplier = 1.0
        self.next_level_experience = int(self.next_level_experience * experience_multiplier)
        while self.experience >= self.next_level_experience:
            self.level += 1
            experience_multiplier = 2.0 - (self.level * 0.1)
            if experience_multiplier < 1.0:
                experience_multiplier = 1.0
            self.next_level_experience = int(self.next_level_experience * experience_multiplier)
        self.save()

    def add_experience(self, experience):
        if not self.is_active:
            raise ValidationError("Cannot modify a deactivated account.")
        if experience is not None:
            self.experience += experience
            self.save()

    def add_acoins(self, acoins):
        if not self.is_active:
            raise ValidationError("Cannot modify a deactivated account.")
        if acoins is not None:
            AcoinTransaction.objects.create(employee=self, amount=acoins)

    def add_achievement(self, achievement):
        if not self.is_active:
            raise ValidationError("Cannot modify a deactivated account.")
        self.achievements.add(achievement)

    class Meta:
        app_label = 'main'
        swappable = 'AUTH_USER_MODEL'

class KarmaHistory(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='karma_history')
    change_date = models.DateTimeField(auto_now_add=True)
    karma_change = models.IntegerField()
    reason = models.CharField(max_length=255, blank=True, null=True)

    def __str__(self):
        return f"{self.employee.username} - {self.karma_change} on {self.change_date}"

class FilePath(models.Model):
    name = models.CharField(max_length=100)
    path = models.CharField(max_length=255, default='')

    def __str__(self):
        return f"{self.name}: {self.path}"

class Classifications(models.Model):
    name = models.CharField(max_length=100, unique=True)

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
    request_type = models.ForeignKey(Classifications, on_delete=models.CASCADE, default=1, blank=True)
    required_count = models.IntegerField(null=True, blank=True,default=0)
    reward_experience = models.IntegerField(null=True, blank=True,default=0)
    reward_currency = models.IntegerField(null=True, blank=True, default=0)
    image = models.ImageField(upload_to='achievements/', default='default.jpg')
    max_level = models.IntegerField(default=3)

    def clean(self):
        if self.type == 'Requests':
            if not self.request_type:
                raise ValidationError('Field request_type is required for achievements based on number of requests.')
            if self.required_count == 0:
                raise ValidationError(
                    'Field required_count must be specified for achievements based on number of requests.')
            if self.reward_experience == 0:
                raise ValidationError(
                    'Field reward_experience must be specified for achievements based on number of requests.')
            if self.reward_currency == 0:
                raise ValidationError(
                    'Field reward_currency must be specified for achievements based on number of requests.')
        elif self.type == 'Test':
            # Устанавливаем дефолтные значения только для полей, которые имеют значение None
            if self.request_type_id is None:
                self.request_type_id = 0
            if self.required_count is None:
                self.required_count = 0
            if self.reward_experience is None:
                self.reward_experience = 0
            if self.reward_currency is None:
                self.reward_currency = 0
        else:
            # Дополнительная логика для других типов ачивок
            pass

    def __str__(self):
        return self.name

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



class Theme(models.Model):
    name = models.CharField(max_length=255)

class Test(models.Model):
    author = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True)  # Автор создания теста
    created_at = models.DateTimeField(auto_now_add=True)  # Дата создания теста
    name = models.CharField(max_length=255)
    description = models.TextField(null=True, blank=True)
    duration_seconds = models.PositiveIntegerField(default=10000)  # Время в секундах
    passing_score = models.PositiveIntegerField(default=70)
    unlimited_time = models.BooleanField(default=False)  # Флаг для неограниченного времени
    show_correct_answers = models.BooleanField(default=False)  # Показывать правильные ответы
    theme = models.ForeignKey(Theme,on_delete=models.PROTECT, default=1) # Ссылка на модель Theme
    can_attempt_twice = models.BooleanField(default=False)
    required_karma = models.IntegerField(default=0)  # Необходимое количество кармы для прохождения
    experience_points = models.PositiveIntegerField(default=0)  # Количество опыта за прохождение
    acoin_reward = models.PositiveIntegerField(default=0)  # Количество акоинов за прохождение
    min_experience = models.PositiveIntegerField(default=0)  # Минимальный опыт для прохождения теста
    achievement = models.ForeignKey(Achievement, on_delete=models.SET_NULL, null=True, blank=True)
    retry_delay_days = models.PositiveIntegerField(null=True, blank=True)
    total_questions = models.PositiveIntegerField(default=0)
    send_results_to_email = models.BooleanField(default=False)  # Отправлять результаты на почту руководителю
    # Новое поле для обозначения максимального количества баллов
    max_score = models.PositiveIntegerField(default=0)
    required_test = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True)
    image = models.ImageField(upload_to='test/', default='default.jpg')

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
    points = models.PositiveIntegerField(default=1)
    explanation = models.TextField(blank=True, null=True)
    image = models.ImageField(upload_to='questions/', blank=True, null=True)  # Изменено на ImageField
    duration_seconds = models.IntegerField(default=0)
    position = models.PositiveIntegerField(default=0)

class Theory(models.Model):
    title = models.CharField(max_length=255)  # Добавленный заголовок
    text = models.TextField()
    image = models.CharField(max_length=255, blank=True, null=True)  # Поле для хранения пути к изображению
    test = models.ForeignKey(Test, on_delete=models.CASCADE)
    position = models.PositiveIntegerField(default=0)

    def __str__(self):
        return self.title

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
        # elif question_type == TestQuestion.MULTIPLE:
        #     correct_answers = self.question.answer_options.filter(is_correct=True).count()
        #     if correct_answers <= 1:
        #         raise ValidationError("For multiple choice question, at least two correct answers are required.")

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
    MODERATION = 'На модерации'
    TEST = 'ТЕСТ'
    STATUS_CHOICES = [
        (PASSED, 'Пройден'),
        (NOT_STARTED, 'Не начат'),
        (IN_PROGRESS, 'В процессе'),
        (FAILED, 'Не пройден'),
        (MODERATION, 'На модерации'),
        (TEST, 'ТЕСТ')
    ]
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE)
    test = models.ForeignKey(Test, on_delete=models.CASCADE)
    start_time = models.DateTimeField(default=timezone.now)
    score = models.FloatField(null=True, blank=True)
    end_time = models.DateTimeField(null=True, blank=True)
    attempts = models.IntegerField(default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=NOT_STARTED)
    test_results = models.JSONField(null=True, blank=True, default=dict)
    free_response = models.TextField(null=True, blank=True)
    def __str__(self):
        return f'{self.test.name} - {self.employee.username}'

    def save(self, *args, **kwargs):
        if not self.pk:  # Проверяем, что это новая запись
            # Ищем последнюю попытку прохождения этого теста этим сотрудником
            last_attempt = TestAttempt.objects.filter(employee=self.employee, test=self.test).order_by(
                '-end_time').first()
            if last_attempt:
                if self.test.retry_delay_days != 0:
                    # Рассчитываем разницу в днях между окончанием последней попытки и текущим временем
                    days_since_last_attempt = (timezone.now() - last_attempt.end_time).days
                    # Проверяем, прошло ли достаточно дней для повторной попытки
                    if days_since_last_attempt < self.test.retry_delay_days:
                        raise ValidationError("Not enough days since last attempt")
                else:
                    # Если retry_delay_days равно 0, количество дней не учитывается
                    days_since_last_attempt = 0
            else:
                # Если это первая попытка прохождения теста этим сотрудником
                self.attempts = 1 if self.test.can_attempt_twice else 0

        # Установка текущего времени в качестве времени начала теста
        if not self.end_time:
            self.end_time = timezone.now()

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
            achievement = self.test.achievement
            if achievement:
                if self.score == self.test.max_score:
                    # Начинаем транзакцию для обеспечения целостности данных
                    with transaction.atomic():
                        # Создаем запись об ачивке для сотрудника
                        EmployeeAchievement.objects.create(employee=self.employee, achievement=achievement)
                        self.employee.save()

def create_acoin_transaction(test_attempt):
    if test_attempt.status == TestAttempt.PASSED:
        # Получаем количество акоинов за прохождение теста
        acoin_reward = test_attempt.test.acoin_reward
        # Создаем транзакцию для сотрудника, который получил акоины за тест
        AcoinTransaction.objects.create(employee=test_attempt.employee, amount=acoin_reward)
        # Получаем количество опыта за прохождение теста
        experience_reward = test_attempt.test.experience_points
        # Начисляем опыт сотруднику
        test_attempt.employee.increase_experience(experience_reward)


