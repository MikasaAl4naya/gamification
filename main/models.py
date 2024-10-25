import os
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractUser, Group, Permission, User
from django.contrib.sessions.models import Session
from django.db import models, transaction
from django.core.validators import EmailValidator, MinValueValidator
from django.core.exceptions import ValidationError
import re
from django.db.models import JSONField
from django.db.models.signals import post_save, post_delete, pre_delete
from django.dispatch import receiver
from django.utils import timezone
from gamefication import settings

class Background(models.Model):
    name = models.CharField(max_length=255)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    level_required = models.IntegerField(default=0)
    karma_required = models.IntegerField(default=0)
    image = models.ImageField(upload_to='backgrounds/')

    def __str__(self):
        return self.name


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


def get_avatar_upload_path(instance, filename):
    file_path = FilePath.objects.filter(name='Avatars').first()
    if file_path:
        base_path = file_path.path  # Должно быть '/home/Shaman/media/avatars'
        # Используем os.path.join для безопасного построения пути
        return os.path.join(base_path, filename)
    else:
        raise ValueError("FilePath for 'Avatars' not found.")


class PreloadedAvatar(models.Model):
    name = models.CharField(max_length=100)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0)  # Добавлено поле "цена"
    level_required = models.IntegerField(default=0)  # Добавлено поле "требуемый уровень"
    karma_required = models.IntegerField(default=0)  # Добавлено поле "требуемая карма"
    image = models.ImageField(upload_to='avatars/', default="avatars/default.jpg")  # Обновлен путь загрузки

    def __str__(self):
        return self.name

class SurveyAnswer(models.Model):
    employee = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    question = models.ForeignKey(SurveyQuestion, on_delete=models.CASCADE)
    answer_text = models.TextField()

    def __str__(self):
        return f"{self.employee.username}: {self.answer_text[:50]}"
def get_default_profile_settings():
    return {
        "show_avatar": True,
        "show_level": True,
        "show_experience": True,
        "show_karma": True,
        "show_total_requests": True,
        "show_achievements_count": True,
        "show_total_experience_earned": True,
        "show_completed_tests_count": True,
        "show_total_lates": True,
        "show_worked_days": True
    }
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
    avatar = models.ForeignKey(PreloadedAvatar,on_delete=models.SET_NULL,null=True,related_name='equipped_by')  # Изменение: внешний ключ вместо ImageField
    status = models.CharField(max_length=100, null=True, blank=True)
    last_karma_update = models.DateTimeField(null=True, blank=True)
    last_activity = models.DateTimeField(null=True, blank=True)
    remaining_experience = models.IntegerField(blank=True, default=100)
    experience_progress = models.IntegerField(blank=True)
    profile_settings = models.JSONField(default=get_default_profile_settings, blank=True, null=False)
    selected_background = models.ForeignKey(Background, on_delete=models.SET_NULL, null=True, blank=True)
    owned_backgrounds = models.ManyToManyField(Background, related_name='owned_by', blank=True)
    owned_avatars = models.ManyToManyField(PreloadedAvatar, related_name='owned_by', blank=True)

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
        # Разрешаем изменения только поля is_active для деактивированных аккаунтов
        if not self.is_active and not getattr(self, 'force_save', False):
            # Проверяем, обновляется ли только поле is_active
            if 'update_fields' in kwargs and len(kwargs['update_fields']) == 1 and 'is_active' in kwargs[
                'update_fields']:
                pass  # Разрешаем изменение поля is_active
            else:
                raise ValidationError("Cannot modify a deactivated account.")
        if self.karma > 100:
            self.karma = 100
        if self.karma<0:
            self.karma = 100
        # Признак, что поле is_active меняется через admin
        if 'is_active' in kwargs.get('update_fields', []):
            self.force_save = True
        super().save(*args, **kwargs)

    def log_change(self, change_type, old_value, new_value, source=None, description=None):

        # Если описание не передано, создаём его на основе типа изменения
        if description is None:
            if change_type == 'experience':
                if new_value > old_value:
                    description = f"Сотрудник {self.get_full_name()} получил {new_value - old_value} очков опыта."
                else:
                    description = f"У сотрудника {self.get_full_name()} было отнято {old_value - new_value} очков опыта."
            elif change_type == 'karma':
                if new_value > old_value:
                    description = f"Сотрудник {self.get_full_name()} получил {new_value - old_value} кармы."
                else:
                    description = f"У сотрудника {self.get_full_name()} было отнято {old_value - new_value} кармы."
            elif change_type == 'acoins':
                if new_value > old_value:
                    description = f"Сотрудник {self.get_full_name()} получил {new_value - old_value} акоинов."
                else:
                    description = f"У сотрудника {self.get_full_name()} было отнято {old_value - new_value} акоинов."
            else:
                description = f"Сотрудник {self.get_full_name()} изменил {change_type}: {old_value} -> {new_value}."

        # Создаём запись лога с изменениями
        EmployeeLog.objects.create(
            employee=self,
            change_type=change_type,
            old_value=old_value,
            new_value=new_value,
            source=source,
            description=description  # Описание всегда заполняется
        )
        print(
            f"Logging change: {change_type}, {old_value} -> {new_value}, source: {source}, description: {description}")
    def add_karma(self, amount, source="Изменили вручную"):
        """ Увеличивает карму на указанное количество и логирует изменение """
        if not self.is_active:
            raise ValidationError("Cannot modify a deactivated account.")

        old_karma = self.karma
        new_karma = old_karma + amount

        if new_karma < 0:
            raise ValidationError("Karma cannot be negative.")

        self.karma = new_karma
        self.log_change('karma', old_karma, self.karma, source=source)
        self.save()

    # Уже существующие методы для experience
    def set_experience(self, amount, source="Изменили вручную"):
        """ Устанавливает опыт напрямую """
        if not self.is_active:
            raise ValidationError("Cannot modify a deactivated account.")

        if amount < 0:
            raise ValidationError("Experience cannot be negative.")

        old_experience = self.experience
        self.experience = amount
        print(f"Setting experience: {old_experience} -> {self.experience}")
        self.log_change('experience', old_experience, self.experience, source=source)
        self.check_level_up()
        self.save()

    def set_karma(self, amount, source="Изменили вручную"):
        """ Устанавливает карму напрямую """
        if not self.is_active:
            raise ValidationError("Cannot modify a deactivated account.")

        if amount < 0:
            raise ValidationError("Karma cannot be negative.")

        old_karma = self.karma
        self.karma = amount
        print(f"Setting karma: {old_karma} -> {self.karma}")
        self.log_change('karma', old_karma, self.karma, source=source)
        self.save()

    def check_level_up(self):
        leveled_up_or_down = False  # Флаг для отслеживания, был ли уровень изменен
        max_level = 50
        min_level = 1

        # Проверка на повышение уровня
        while self.experience >= self.next_level_experience and self.level < max_level:
            old_level = self.level
            self.level += 1
            leveled_up_or_down = True
            self.next_level_experience = self.calculate_experience_for_level(self.level)
            self.log_change('level', old_level, self.level)

        # Проверка на понижение уровня
        while self.level > min_level and self.experience < self.calculate_experience_for_level(self.level - 1):
            old_level = self.level
            self.level -= 1
            leveled_up_or_down = True
            self.next_level_experience = self.calculate_experience_for_level(self.level)
            self.log_change('level', old_level, self.level)

        # Обновление оставшегося опыта
        previous_level_experience = self.calculate_experience_for_level(self.level - 1)
        self.remaining_experience = self.next_level_experience - self.experience

        # Корректный расчет прогресса опыта (в процентах)
        experience_for_current_level = self.next_level_experience - previous_level_experience
        if experience_for_current_level > 0:
            self.experience_progress = int(
                ((self.experience - previous_level_experience) / experience_for_current_level) * 100
            )
        else:
            self.experience_progress = 0

        # Сохранение изменений только если уровень был изменен
        if leveled_up_or_down:
            print(f"Level changed: {self.level}, recalculating experience.")
            super(Employee, self).save(
                update_fields=['level', 'experience', 'next_level_experience', 'remaining_experience',
                               'experience_progress'])
        else:
            super(Employee, self).save(
                update_fields=['experience', 'next_level_experience', 'remaining_experience', 'experience_progress'])

    def calculate_experience_for_level(self, level):
        base_experience = 100  # базовый опыт для первого уровня
        experience_required = base_experience

        for i in range(2, level + 1):
            # Увеличение опыта на каждый следующий уровень
            experience_required += int(base_experience * (i - 1) * 0.2)  # Плавный рост сложности

        return experience_required

    def add_experience(self, experience, source="Изменили вручную"):
        """ Увеличивает опыт на указанное количество и логирует изменение. """
        if not self.is_active:
            raise ValidationError("Cannot modify a deactivated account.")

        if experience is not None:
            old_experience = self.experience
            new_experience = old_experience + experience

            if new_experience < 0:
                raise ValidationError("Experience cannot be negative.")

            self.experience = new_experience
            self.log_change('experience', old_experience, self.experience, source=source)
            self.check_level_up()
            self.save()
    def add_acoins(self, acoins):
        if not self.is_active:
            raise ValidationError("Cannot modify a deactivated account.")
        if acoins is not None:
            AcoinTransaction.objects.create(employee=self, amount=acoins)
            self.log_change('acoins', self.acoin.amount, self.acoin.amount + acoins, )
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
        return f"{self.employee.username} - {self.action_type} {self.model_name} at {self.created_at}"


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
    late = models.BooleanField(default=False)  # Добавляем поле для опозданий

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
class ComplexityThresholds(models.Model):
    simple = models.IntegerField(default=10)
    medium = models.IntegerField(default=20)
    hard = models.IntegerField(default=30)
    updated_at = models.DateTimeField(auto_now=True)

    @classmethod
    def get_current_thresholds(cls):
        # Получаем текущие пороги или создаем новые, если они отсутствуют
        thresholds = cls.objects.first()
        if not thresholds:
            thresholds = cls.objects.create()
        return thresholds

    def __str__(self):
        return f"Simple: {self.simple}, Medium: {self.medium}, Hard: {self.hard}"


class Classifications(models.Model):
    SIMPLE = 'simple'
    MEDIUM = 'medium'
    HARD = 'hard'

    COMPLEXITY_CHOICES = [
        (SIMPLE, 'Простое'),
        (MEDIUM, 'Среднее'),
        (HARD, 'Сложное'),
    ]

    name = models.CharField(max_length=100)
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='subclassifications')
    experience_points = models.IntegerField(default=10, verbose_name="Очки опыта")
    complexity = models.CharField(max_length=10, choices=COMPLEXITY_CHOICES, default=SIMPLE, editable=False)

    class Meta:
        unique_together = ('name', 'parent')

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        # Устанавливаем сложность в зависимости от очков опыта и текущих порогов
        thresholds = ComplexityThresholds.get_current_thresholds()
        if self.experience_points < thresholds.simple:
            self.complexity = self.SIMPLE
        elif self.experience_points < thresholds.medium:
            self.complexity = self.MEDIUM
        else:
            self.complexity = self.HARD

        # Проверка на наличие существующей классификации с таким же именем и родителем
        existing_classification = Classifications.objects.filter(name=self.name, parent=self.parent).first()
        if existing_classification and existing_classification.id != self.id:
            existing_classification.experience_points = self.experience_points
            super(Classifications, existing_classification).save(*args, **kwargs)  # сохраняем изменения
        else:
            super(Classifications, self).save(*args, **kwargs)

class Template(models.Model):
    name = models.CharField(max_length=255)
    image = models.ImageField(upload_to='templates/')
    is_background = models.BooleanField(default=False)
    back_image = models.ImageField(upload_to='templates/back_images/', null = True)

    class Meta:
        verbose_name = "Шаблоны"
        verbose_name_plural = "Шаблоны"

    def __str__(self):
        return self.name

class Achievement(models.Model):
    TYPE_CHOICES = [
        (1, 'Appeals'),
        (2, 'Tasks'),
        (3, 'NewLvl'),
        (4, 'Chart'),
        (5, 'Tests'),
        (6, 'Indicators'),
        (7, 'Avations'),
        (8, 'Profile'),
        (9, 'Store'),
        (10, 'Background'),
        (11, 'Rating'),
        (12, 'News'),
        (13, 'KPI'),
        (14, 'Other'),
    ]

    DIFFICULTY_CHOICES = [
        ('Easy', 'Легкая'),
        ('Medium', 'Средняя'),
        ('Hard', 'Сложная'),
        ('Expert', 'Эксперт'),
    ]

    name = models.CharField(max_length=100)
    description = models.TextField(null=True, blank=True)
    type = models.IntegerField(choices=TYPE_CHOICES)
    reward_experience = models.IntegerField(null=True, blank=True, default=0)
    reward_currency = models.IntegerField(null=True, blank=True, default=0)
    template_background = models.ForeignKey(Template, related_name='background_achievements', on_delete=models.SET_NULL, null=True, blank=True)
    template_foreground = models.ForeignKey(Template, related_name='foreground_achievements', on_delete=models.SET_NULL, null=True, blank=True)
    difficulty = models.CharField(max_length=20, choices=DIFFICULTY_CHOICES, default='Medium')
    is_award = models.BooleanField(default=False)
    border_style = models.CharField(max_length=20, default='solid')
    border_width = models.IntegerField(null=True, blank=True, default=0)
    border_color = models.CharField(max_length=255, default='#000000')
    background_image = models.ImageField(upload_to='achievement_backgrounds/', null=True, blank=True)  # Файл фона
    foreground_image = models.ImageField(upload_to='achievement_foregrounds/', null=True,
                                         blank=True)  # Файл основной части
    use_border = models.BooleanField(default=False)
    type_specific_data = JSONField(null=True, blank=True)
    textColor = models.CharField(default='#000000', max_length=255)
    back_image = models.ImageField(upload_to='achievement_back_images/', null=True, blank=True)
    can_be_repeated = models.BooleanField(default=False)
    show_name = models.BooleanField(default=True)

    class Meta:
        app_label = 'main'

    def __str__(self):
        return self.name

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
            if self.request_type_id is None:
                self.request_type_id = 0
            if self.required_count is None:
                self.required_count = 0
            if self.reward_experience is None:
                self.reward_experience = 0
            if self.reward_currency is None:
                self.reward_currency = 0
        elif self.type == 'Unique':
            if self.is_award:
                # Обработка логики для наград
                if not self.name or not self.description or not self.image:
                    raise ValidationError('For an award, name, description, and image are required.')

# Модель предмета в магазине
class Item(models.Model):
    description = models.CharField(max_length=100)
    price = models.IntegerField()
    karma_bonus = models.IntegerField(default=0)  # Бонус к карме
    experience_bonus = models.IntegerField(default=0)  # Бонус к опыту
    duration_days = models.IntegerField(default=0)  # Срок действия предмета в днях (если есть)

    def save(self, *args, **kwargs):
        # Валидация значений
        if self.price < 0 or self.karma_bonus < 0 or self.experience_bonus < 0 or self.duration_days < 0:
            raise ValueError("Значения цены, бонусов и срока действия не могут быть отрицательными")
        super(Item, self).save(*args, **kwargs)


class Request(models.Model):
    STATUS_CHOICES = [
        ('Registered', 'Зарегистрировано'),
        ('In Progress', 'В работе'),
        ('Returned', 'Возвращено'),
        ('Forwarded to Second Line', 'Передано на вторую линию'),
        ('Forwarded to Third Line', 'Передано на третью линию'),
        ('Completed', 'Завершено'),
    ]

    number = models.CharField(max_length=100, primary_key=True, unique=True)  # Сделать первичным ключом
    classification = models.ForeignKey(Classifications, on_delete=models.CASCADE)
    responsible = models.CharField(max_length=255)
    support_operator = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='registered_requests', null=True)
    initiator = models.CharField(max_length=255)
    status = models.CharField(max_length=100, choices=STATUS_CHOICES)
    description = models.TextField(null=True, blank=True)
    date = models.DateTimeField()
    is_massive = models.BooleanField(default=False)  # Новое поле для массовых обращений

    def __str__(self):
        return f'{self.number} - {self.get_status_display()}'

CHANGE_TYPE_CHOICES = [
    ('experience', 'Опыт'),
    ('karma', 'Карма'),
    ('acoins', 'Acoins'),
    ('other', 'Другое'),
]


class EmployeeLog(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE)
    timestamp = models.DateTimeField(auto_now_add=True)
    change_type = models.CharField(max_length=50)
    old_value = models.IntegerField()
    new_value = models.IntegerField()
    description = models.TextField(null=True, blank=True)

    # Новое поле для хранения источника изменения
    source = models.CharField(max_length=100, null=True, blank=True)

    def __str__(self):
        source_info = f" - {self.source}" if self.source else ""
        return f"{self.employee} - {self.change_type} at {self.timestamp}{source_info}"

    def value_change(self):
        """Возвращает разницу между новым и старым значением."""
        return self.new_value - self.old_value


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
        employee.log_change('acoins', employee.acoin.amount, employee.acoin.amount + achievement.reward_currency)
        return transaction

# Модель для связки сотрудника и предмета
class EmployeeItem(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE)
    item = models.ForeignKey(Item, on_delete=models.CASCADE)
    acquired_at = models.DateTimeField(auto_now_add=True)  # Когда предмет был куплен
    is_active = models.BooleanField(default=True)  # Предмет активен или его срок действия закончился

    def apply_bonus(self):
        """Применяет бонусы от предмета к сотруднику."""
        if self.is_active:
            self.employee.karma += self.item.karma_bonus
            self.employee.experience += self.item.experience_bonus
            self.employee.save()

    def check_expiration(self):
        """Проверка срока действия предмета."""
        if self.item.duration_days > 0:
            expiration_date = self.acquired_at + timezone.timedelta(days=self.item.duration_days)
            if timezone.now() > expiration_date:
                self.is_active = False
                self.save()


class EmployeeAchievement(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE)
    achievement = models.ForeignKey(Achievement, on_delete=models.CASCADE)
    progress = models.IntegerField(default=0)  # Абсолютное значение прогресса
    progress_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0.0)  # Прогресс в процентах
    level = models.IntegerField(default=0)
    count = models.IntegerField(default=1)  # Количество раз, когда достижение было получено
    assigned_manually = models.BooleanField(default=False)  # Флаг для вручную назначенных наград
    date_awarded = models.DateTimeField(null=True, blank=True)  # Дата последнего получения достижения

    class Meta:
        unique_together = ('employee', 'achievement')  # Гарантирует уникальность для каждого сочетания сотрудник-достижение

    def increment_progress(self):
        """
        Увеличивает прогресс достижения. Если достижение уже выдано и можно получить его снова,
        прогресс сбрасывается, а `count` увеличивается.
        """
        if self.assigned_manually:
            # Не увеличиваем прогресс для вручную назначенных достижений
            return

        self.progress += 1

        if self.achievement.type_specific_data:
            required_count = self.achievement.type_specific_data.get("required_count")

            if required_count and self.progress >= required_count:
                # Выдаем награду и увеличиваем количество раз получения достижения
                self.reward_employee()
                self.date_awarded = timezone.now()
                self.count += 1
                self.progress = 0  # Сбрасываем прогресс после получения достижения

        self.save()

    def reward_employee(self):
        """
        Награждает сотрудника за достижение, добавляет опыт и валюту, устанавливает дату получения.
        """
        employee = self.employee
        reward_currency = self.achievement.reward_currency
        reward_experience = self.achievement.reward_experience

        # Добавление опыта и валюты сотруднику
        employee.add_experience(reward_experience)
        employee.add_acoins(reward_currency)

        # Устанавливаем дату получения достижения
        self.date_awarded = timezone.now()

        # Сохраняем изменения
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
        # Убеждаемся, что тип ачивки всегда соответствует числовому значению для "Test"
        if self.achievement:
            if self.achievement.type != 5:  # Убедитесь, что сравниваете с числовым значением
                raise ValidationError('Achievement type must be "Test" (type=5).')

    def save(self, *args, **kwargs):
        # Убеждаемся, что тип ачивки всегда соответствует числовому значению для "Test"
        if self.achievement:
            if self.achievement.type != 5:  # Убедитесь, что сравниваете с числовым значением
                raise ValidationError('Achievement type must be "Test" (type=5).')
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
    description = models.TextField(null=True, blank=True)  # Добавляем поле description
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
    moderation_comment = models.TextField(verbose_name='Комментарий модератора', null=True, blank=True)
    moderation_date = models.DateTimeField(verbose_name='Дата модерации', null=True, blank=True)

    def __str__(self):
        return f'{self.get_type_display()} на {self.target_employee} (Уровень: {self.level})'

class ExperienceMultiplier(models.Model):
    name = models.CharField(max_length=255, unique=True)  # Название условия (например, operator_responsible_multiplier)
    multiplier = models.FloatField(default=1.0)  # Показатель множителя

    def __str__(self):
        return f"{self.name}: {self.multiplier}"
class KarmaSettings(models.Model):
    PRAISE = 'praise'
    COMPLAINT = 'complaint'
    TEST_MODERATION = 'test_moderation'
    SHIFT_COMPLETION = 'shift_completion'
    LATE_PENALTY = 'late_penalty'
    OTHER = 'other'

    OPERATION_TYPE_CHOICES = [
        (PRAISE, 'Praise'),
        (COMPLAINT, 'Complaint'),
        (TEST_MODERATION, 'Test Moderation'),
        (SHIFT_COMPLETION, 'Shift Completion'),
        (LATE_PENALTY, 'Late Penalty'),
        (OTHER, 'Other'),
    ]

    LEVEL_CHOICES = [
        (1, 'Уровень 1'),
        (2, 'Уровень 2'),
        (3, 'Уровень 3'),
        (4, 'Уровень 4'),
        (5, 'Уровень 5'),
    ]

    operation_type = models.CharField(max_length=50, choices=OPERATION_TYPE_CHOICES, null=True)
    level = models.PositiveSmallIntegerField(choices=LEVEL_CHOICES, verbose_name='Уровень', null=True, blank=True)
    karma_change = models.IntegerField(null=True, blank=True, help_text="Изменение кармы")
    experience_change = models.IntegerField(null=True, blank=True, help_text="Изменение опыта")

    class Meta:
        verbose_name = "Настройка операции"
        verbose_name_plural = "Настройки операций"

    def __str__(self):
        level_str = f" - {self.get_level_display()}" if self.level else ""
        operation_type_str = self.get_operation_type_display() if self.operation_type else "Неизвестный тип операции"
        return f'{operation_type_str}{level_str}'
