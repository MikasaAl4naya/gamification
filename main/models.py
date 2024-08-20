import logging

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractUser, Group, Permission, User
from django.contrib.sessions.models import Session
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

class SurveyQuestion(models.Model):
    question_text = models.CharField(max_length=255)

    def __str__(self):
        return self.question_text

class SurveyAnswer(models.Model):
    employee = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    question = models.ForeignKey(SurveyQuestion, on_delete=models.CASCADE)
    answer_text = models.TextField()

    def __str__(self):
        return f"{self.employee.username}: {self.answer_text[:50]}"

class Employee(AbstractUser):
    POSITION_CHOICES = [
        ('Оператор ТП', 'Оператор ТП'),
        ('Специалист ТП', 'Специалист ТП'),
        ('Консультант ТП', 'Консультант ТП'),
        ('Координатор ТП', 'Координатор ТП'),
    ]
    email = models.EmailField(validators=[EmailValidator(), validate_custom_email])
    position = models.CharField(max_length=50, choices=POSITION_CHOICES)
    level = models.IntegerField(default=1)
    experience = models.IntegerField(default=0)
    next_level_experience = models.IntegerField(default=100)
    karma = models.IntegerField(default=50)
    birth_date = models.DateField(null=True, blank=True)
    avatar = models.ImageField(upload_to='avatars/', default='default.jpg', blank=True, null=True)
    status = models.CharField(max_length=100, null=True, blank=True)
    last_karma_update = models.DateTimeField(null=True, blank=True)
    last_activity = models.DateTimeField(null=True, blank=True)


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

    @property
    def level_title(self):
        try:
            level_title = LevelTitle.objects.get(level=self.level)
            return level_title.title
        except LevelTitle.DoesNotExist:
            return "Неизвестный уровень"
    def get_survey_answers(self):
        return self.survey_answers.select_related('question').all()
    def save(self, *args, **kwargs):
        if not self.is_active and not getattr(self, 'force_save', False):
            raise ValidationError("Cannot modify a deactivated account.")
        if self.karma > 100:
            self.karma = 100
        # Проверка и обновление уровня на основе текущего опыта
        self.check_level_up()
        super().save(*args, **kwargs)

    def log_change(self, change_type, old_value, new_value, description=None):
        EmployeeLog.objects.create(
            employee=self,
            change_type=change_type,
            old_value=old_value,
            new_value=new_value,
            description=description
        )

    def set_experience(self, amount):
        if not self.is_active:
            raise ValidationError("Cannot modify a deactivated account.")
        old_experience = self.experience
        self.experience = amount
        self.log_change('experience', old_experience, self.experience, "Set experience")
        self.check_level_up()

    def increase_experience(self, amount):
        if not self.is_active:
            raise ValidationError("Cannot modify a deactivated account.")
        self.set_experience(self.experience + amount)

    def check_level_up(self):
        leveled_up = False  # Флаг для отслеживания, был ли уровень повышен

        # Максимальное количество уровней
        max_level = 50

        # Пока опыта хватает для повышения уровня и текущий уровень меньше максимального
        while self.experience >= self.next_level_experience and self.level < max_level:
            old_level = self.level
            print(
                f"Current level: {self.level}. Experience: {self.experience}. Next level at: {self.next_level_experience}")

            self.level += 1
            leveled_up = True
            self.log_change('level', old_level, self.level, "Level up")

            # Рассчитываем опыт, необходимый для следующего уровня как сумма текущего и прошлого
            previous_level_experience = self.next_level_experience
            experience_multiplier = 2.0 - (self.level * 0.1)
            if experience_multiplier < 1.0:
                experience_multiplier = 1.0
            self.next_level_experience = previous_level_experience + int(
                previous_level_experience * experience_multiplier)

            print(f"Leveled up! New level: {self.level}. Remaining experience: {self.experience}")
            print(f"New next level experience: {self.next_level_experience}")

        # Сохранение изменений только если уровень был повышен
        if leveled_up:
            self.save()

    def add_experience(self, experience):
        if not self.is_active:
            raise ValidationError("Cannot modify a deactivated account.")
        if experience is not None:
            self.increase_experience(experience)

    def set_karma(self, amount):
        if not self.is_active:
            raise ValidationError("Cannot modify a deactivated account.")
        old_karma = self.karma
        self.karma = amount
        if self.karma > 100:
            self.karma = 100
        self.log_change('karma', old_karma, self.karma, "Set karma")
        self.save()

    def add_acoins(self, acoins):
        if not self.is_active:
            raise ValidationError("Cannot modify a deactivated account.")
        if acoins is not None:
            AcoinTransaction.objects.create(employee=self, amount=acoins)
            self.log_change('acoins', self.acoin.amount, self.acoin.amount + acoins, "Add acoins")
            self.acoin.amount += acoins
            self.acoin.save()

    def add_achievement(self, achievement):
        if not self.is_active:
            raise ValidationError("Cannot modify a deactivated account.")
        self.achievements.add(achievement)

    class Meta:
        app_label = 'main'
        swappable = 'AUTH_USER_MODEL'
class EmployeeActionLog(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE)
    action_type = models.CharField(max_length=50)
    model_name = models.CharField(max_length=50)
    object_id = models.CharField(max_length=50)
    description = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.employee.username} - {self.action_type} {self.model_name} at {self.timestamp}"


class UserSession(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    session = models.OneToOneField(Session, on_delete=models.CASCADE)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=255, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_activity = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Session for {self.user.username} from {self.ip_address}"

    def deactivate(self):
        self.is_active = False
        self.force_save = True
        self.save()

        # Завершение всех активных сессий пользователя
        UserSession.objects.filter(user=self).delete()
class ShiftHistory(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE)
    date = models.DateField()
    scheduled_start = models.TimeField()
    scheduled_end = models.TimeField()
    actual_start = models.TimeField()
    actual_end = models.TimeField()
    karma_change = models.IntegerField()
    experience_change = models.IntegerField()
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('employee', 'date', 'scheduled_start', 'scheduled_end')
        verbose_name = "История смен"
        verbose_name_plural = "История смен"

    def __str__(self):
        return f"{self.employee} - {self.date} - {self.scheduled_start}-{self.scheduled_end}"
class SystemSetting(models.Model):
    key = models.CharField(max_length=100, unique=True)
    value = models.CharField(max_length=255)

    def __str__(self):
        return f"{self.key}: {self.value}"
class PasswordPolicy(models.Model):
    min_length = models.PositiveIntegerField(default=8)
    max_length = models.PositiveIntegerField(default=128)
    min_uppercase = models.PositiveIntegerField(default=1)
    min_lowercase = models.PositiveIntegerField(default=1)
    min_digits = models.PositiveIntegerField(default=1)
    min_symbols = models.PositiveIntegerField(default=1)  # Добавлено новое поле
    allowed_symbols = models.CharField(max_length=255, default="~!@#$%^&*()-_=+[{]}|;:'\",<.>/?")
    arabic_only = models.BooleanField(default=True)
    no_spaces = models.BooleanField(default=True)

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
    last_updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name}: {self.path}"

class Classifications(models.Model):
    name = models.CharField(max_length=100)
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='subclassifications')
    experience_points = models.IntegerField(default=0, verbose_name="Очки опыта")

    class Meta:
        unique_together = ('name', 'parent')

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
    required_count = models.IntegerField(null=True, blank=True, default=0)
    reward_experience = models.IntegerField(null=True, blank=True, default=0)
    reward_currency = models.IntegerField(null=True, blank=True, default=0)
    image = models.ImageField(upload_to='achievements/', default='default.jpg')
    max_level = models.IntegerField(default=3)

    def clean(self):
        if self.type == 'Requests':
            if not self.request_type:
                raise ValidationError('Field request_type is required for achievements based on number of requests.')
            if self.required_count == 0:
                raise ValidationError('Field required_count must be specified for achievements based on number of requests.')
            if self.reward_experience == 0:
                raise ValidationError('Field reward_experience must be specified for achievements based on number of requests.')
            if self.reward_currency == 0:
                raise ValidationError('Field reward_currency must be specified for achievements based on number of requests.')
        elif self.type == 'Test':
            if self.request_type_id is None:
                self.request_type_id = 0
            if self.required_count is None:
                self.required_count = 0
            if self.reward_experience is None:
                self.reward_experience = 0
            if self.reward_currency is None:
                self.reward_currency = 0
        else:
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
    responsible = models.CharField(max_length=255)
    support_operator = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='registered_requests', null=True)
    initiator = models.CharField(max_length=255)
    status = models.CharField(max_length=100, choices=STATUS_CHOICES)
    description = models.TextField(null=True, blank=True)
    number = models.CharField(max_length=100)
    date = models.DateTimeField()
    is_massive = models.BooleanField(default=False)  # Новое поле для массовых обращений

    def calculate_experience(self):
        base_experience = 10  # Базовое количество опыта за обращение
        if self.is_massive:
            return base_experience * 2  # Увеличиваем опыт за массовое обращение
        return base_experience

    def __str__(self):
        return f'{self.number} - {self.get_status_display()}'


class EmployeeLog(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE)
    timestamp = models.DateTimeField(auto_now_add=True)
    change_type = models.CharField(max_length=50)
    old_value = models.IntegerField()
    new_value = models.IntegerField()
    description = models.TextField(null=True, blank=True)

    def __str__(self):
        return f"{self.employee} - {self.change_type} at {self.timestamp}"

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
        employee.log_change('acoins', employee.acoin.amount, employee.acoin.amount + achievement.reward_currency, "Achievement reward")
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
        if self.level >= self.achievement.max_level:
            return
        else:
            self.level += 1
            if self.achievement.required_count is not None:
                self.achievement.required_count = int(self.achievement.required_count * 1.5)
            if self.achievement.reward_experience is not None:
                self.achievement.reward_experience = int(self.achievement.reward_experience * 1.5)
            self.achievement.save()
            self.reward_employee()

    def reward_employee(self):
        employee = self.employee
        reward_currency = self.achievement.reward_currency
        reward_experience = self.achievement.reward_experience
        employee.add_experience(reward_experience)
        employee.add_acoins(reward_currency)
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
    image = models.ImageField(upload_to='test/', null=True, blank=True )

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
    image = models.ImageField(max_length=255, blank=True, null=True)  # Поле для хранения пути к изображению
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

class LevelTitle(models.Model):
    level = models.PositiveIntegerField(unique=True)
    title = models.CharField(max_length=255)

    def __str__(self):
        return f"Level {self.level}: {self.title}"
class Feedback(models.Model):
    FEEDBACK_TYPE_CHOICES = [
        ('complaint', 'Жалоба'),
        ('praise', 'Похвала'),
    ]

    STATUS_CHOICES = [
        ('pending', 'На модерации'),
        ('approved', 'Одобрено'),
        ('rejected', 'Отклонено'),
    ]

    LEVEL_CHOICES = [
        (1, 'Низкий'),
        (2, 'Средний'),
        (3, 'Высокий'),
    ]

    type = models.CharField(max_length=10, choices=FEEDBACK_TYPE_CHOICES, verbose_name='Тип отзыва')
    text = models.TextField(verbose_name='Текст')
    level = models.PositiveSmallIntegerField(choices=LEVEL_CHOICES, verbose_name='Уровень', null=True, blank=True)
    karma_change = models.IntegerField(verbose_name='Изменение кармы', default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name='Статус')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата создания')
    moderator = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True, blank=True, related_name='moderated_feedbacks', verbose_name='Модератор')
    target_employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='received_feedbacks', verbose_name='Целевой сотрудник')
    moderator_comment = models.TextField(verbose_name='Комментарий модератора', null=True, blank=True)
    moderation_date = models.DateTimeField(verbose_name='Дата модерации', null=True, blank=True)

    def __str__(self):
        return f'{self.get_type_display()} на {self.target_employee} (Уровень: {self.level})'

class ExperienceMultiplier(models.Model):
    name = models.CharField(max_length=255, unique=True)  # Название условия (например, operator_responsible_multiplier)
    multiplier = models.FloatField(default=1.0)  # Показатель множителя

    def __str__(self):
        return f"{self.name}: {self.multiplier}"
class KarmaSettings(models.Model):
    # Типы операций
    PRAISE = 'praise'
    COMPLAINT = 'complaint'
    TEST_MODERATION = 'test_moderation'
    SHIFT_COMPLETION = 'shift_completion'
    FEEDBACK_MODERATION = 'feedback_moderation'
    OTHER = 'other'  # Можно добавить больше типов операций

    OPERATION_TYPE_CHOICES = [
        (PRAISE, 'Praise'),
        (COMPLAINT, 'Complaint'),
        (TEST_MODERATION, 'Test Moderation'),
        (SHIFT_COMPLETION, 'Shift Completion'),
        (FEEDBACK_MODERATION, 'Feedback Moderation'),
        (OTHER, 'Other'),
    ]

    LEVEL_CHOICES = [
        (1, 'Низкий'),
        (2, 'Средний'),
        (3, 'Высокий'),
    ]

    operation_type = models.CharField(max_length=50, choices=OPERATION_TYPE_CHOICES, null=True)
    level = models.PositiveSmallIntegerField(choices=LEVEL_CHOICES, verbose_name='Уровень', null=True, blank=True)
    karma_change = models.IntegerField(null=True, blank=True, help_text="Изменение кармы")
    experience_change = models.IntegerField(null=True, blank=True, help_text="Изменение опыта")

    class Meta:
        verbose_name = "Настройка операции"
        verbose_name_plural = "Настройки операций"

    def __str__(self):
        # Определите строковое представление объекта
        level_str = f" - {self.get_level_display()}" if self.level else ""
        operation_type_str = self.get_operation_type_display() if self.operation_type else "Неизвестный тип операции"
        return f'{operation_type_str}{level_str}'



