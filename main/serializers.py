import json
import re

from django.contrib.auth.models import User, Permission, Group
from django.utils.crypto import get_random_string
from rest_framework import serializers, viewsets
from rest_framework.permissions import IsAdminUser

from gamefication import settings
from main.models import Employee, AcoinTransaction, Acoin, Test, TestQuestion, AnswerOption, Theory, Achievement, \
    Request, Theme, Classifications, TestAttempt, Feedback, SurveyAnswer, SurveyQuestion, EmployeeActionLog, \
    KarmaSettings, \
    FilePath, ExperienceMultiplier, SystemSetting, PasswordPolicy, PreloadedAvatar, EmployeeAchievement, EmployeeLog, \
    Item, EmployeeItem, Template, ComplexityThresholds
from main.names_translations import translate_permission_name


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    password = serializers.CharField(max_length=128,
                                     write_only=True)  # write_only=True означает, что поле не будет включено в сериализацию

    def validate(self, data):
        """
        Проверка данных.
        """
        username = data.get('username')
        password = data.get('password')

        # Здесь вы можете добавить пользовательскую логику проверки учетных данных,
        # например, проверку имени пользователя и пароля в базе данных

        # Вернуть данные, если они валидны
        return data
class MicroEmployeeSerializer(serializers.ModelSerializer):
    avatar_url = serializers.SerializerMethodField()

    class Meta:
        model = Employee
        fields = ['first_name', 'avatar_url']
    def get_avatar_url(self, obj):
        if obj.avatar:
            return f"http://shaman.pythonanywhere.com{obj.avatar.url}"
        return "http://shaman.pythonanywhere.com/media/default.jpg"
class ClassificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Classifications
        fields = '__all__'
class PreloadedAvatarSerializer(serializers.ModelSerializer):
    class Meta:
        model = PreloadedAvatar
        fields = ['id', 'name', 'image']
class PlayersSerializer(serializers.ModelSerializer):
    acoin_amount = serializers.IntegerField(source='acoin.amount', read_only=True)
    avatar_url = serializers.SerializerMethodField()

    class Meta:
        model = Employee
        fields = [
            'id', 'first_name', 'last_name', 'level','karma', 'experience',
            'next_level_experience', 'avatar_url', 'acoin_amount', 'level_title'
        ]
        read_only_fields = ['first_name', 'last_name', 'level', 'experience', 'next_level_experience']

    def get_avatar_url(self, obj):
        if obj.avatar:
            return f"http://shaman.pythonanywhere.com{obj.avatar.url}"
        return "http://shaman.pythonanywhere.com/media/default.jpg"

class SurveyQuestionSerializer(serializers.ModelSerializer):
    class Meta:
        model = SurveyQuestion
        fields = '__all__'

class SurveyAnswerSerializer(serializers.ModelSerializer):
    class Meta:
        model = SurveyAnswer
        fields = '__all__'
        read_only_fields = ['employee']
class RecursiveField(serializers.Serializer):
    def to_representation(self, value):
        serializer = self.parent.parent.__class__(value, context=self.context)
        return serializer.data
class SystemSettingSerializer(serializers.ModelSerializer):
    class Meta:
        model = SystemSetting
        fields = '__all__'

class SurveyAnswerSerializer(serializers.ModelSerializer):
    class Meta:
        model = SurveyAnswer
        fields = ['question', 'answer']

class SurveyQuestionSerializer(serializers.ModelSerializer):
    class Meta:
        model = SurveyQuestion
        fields = ['id', 'question_text']

class EmployeeProfileSerializer(serializers.ModelSerializer):
    survey_answers = SurveyAnswerSerializer(many=True, read_only=True)
    birth_date = serializers.DateField(source='employee.birth_date', read_only=True)

    class Meta:
        model = Employee
        fields = ['first_name', 'last_name', 'email', 'position', 'birth_date', 'survey_answers']


class ClassificationsSerializer(serializers.ModelSerializer):
    parentName = serializers.SerializerMethodField()

    class Meta:
        model = Classifications
        fields = ['id', 'name', 'experience_points', 'parent', 'parentName']

    def get_parentName(self, obj):
        # Вызываем вспомогательный метод для построения полного имени цепочки без последнего элемента
        return self.build_full_parent_name(obj)

    def build_full_parent_name(self, obj):
        # Если у объекта нет родителя, возвращаем пустую строку
        if not obj.parent:
            return None

        # Рекурсивно строим полное имя цепочки родительских элементов
        parent_name = self.build_full_parent_name(obj.parent)
        if parent_name:
            return f"{parent_name}->{obj.parent.name}"
        else:
            return obj.parent.name
class PasswordPolicySerializer(serializers.ModelSerializer):

    class Meta:
        model = PasswordPolicy
        fields = '__all__'

class ComplexityThresholdsSerializer(serializers.ModelSerializer):
    class Meta:
        model = ComplexityThresholds
        fields = ['simple', 'medium', 'hard']

class ExperienceMultiplierSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExperienceMultiplier
        fields = ['name', 'multiplier']
class EmployeeLogSerializer(serializers.ModelSerializer):
    readable_description = serializers.SerializerMethodField()

    class Meta:
        model = EmployeeLog
        fields = [
            'employee',
            'change_type',
            'old_value',
            'new_value',
            'description',
            'source',
            'timestamp',
            'readable_description'
        ]

    def get_readable_description(self, obj):
        """
        Генерирует более читаемое описание изменений.
        """
        employee_name = f"{obj.employee.first_name} {obj.employee.last_name}"
        change = obj.new_value - obj.old_value  # Вычисляем изменение напрямую

        if obj.change_type == 'experience':
            if change > 0:
                return f"{employee_name} получил {change} очков опыта."
            else:
                return f"{employee_name} потерял {abs(change)} очков опыта."
        elif obj.change_type == 'karma':
            if change > 0:
                return f"{employee_name} получил {change} кармы."
            else:
                return f"{employee_name} потерял {abs(change)} кармы."
        elif obj.change_type == 'acoins':
            if change > 0:
                return f"{employee_name} получил {change} акоинов."
            else:
                return f"{employee_name} потерял {abs(change)} акоинов."
        else:
            # Обработка других типов изменений
            return obj.description if obj.description else f"{employee_name} изменил {obj.change_type}: {obj.old_value} -> {obj.new_value}."

class FileUploadSerializer(serializers.Serializer):
    file = serializers.FileField()
class FilePathSerializer(serializers.ModelSerializer):
    class Meta:
        model = FilePath
        fields = '__all__'

class EmployeeSerializer(serializers.ModelSerializer):
    acoin_amount = serializers.IntegerField(source='acoin.amount', read_only=True)
    avatar_url = serializers.SerializerMethodField()
    remaining_experience = serializers.SerializerMethodField()
    experience_progress = serializers.SerializerMethodField()

    class Meta:
        model = Employee
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name', 'position', 'level', 'experience',
            'next_level_experience', 'remaining_experience', 'experience_progress', 'karma', 'birth_date',
            'avatar_url', 'status', 'acoin_amount', 'is_active', 'groups', 'is_active'
        ]
        read_only_fields = ['username', 'email', 'position', 'level', 'experience', 'next_level_experience', 'karma']

    def get_avatar_url(self, obj):
        if obj.avatar and hasattr(obj.avatar, 'url'):
            return f"http://shaman.pythonanywhere.com{obj.avatar.url}"
        return "http://shaman.pythonanywhere.com/media/default.jpg"
    def get_remaining_experience(self, obj):
        """Возвращает количество опыта, необходимое для достижения следующего уровня."""
        return obj.next_level_experience - obj.experience

    def get_experience_progress(self, obj):
        """Возвращает прогресс опыта в процентах внутри текущего уровня."""
        if obj.next_level_experience > 0:
            progress = (obj.experience / obj.next_level_experience) * 100
            return max(0, min(int(progress), 100))
        return 0
    def get_role(self, obj):
        roles = [group.name[:-1] if group.name.endswith('Ы') else group.name for group in obj.groups.all()]
        return roles

    def update(self, instance, validated_data):
        # Обновляем группы сотрудника, если они предоставлены в запросе
        groups = validated_data.pop('groups', None)
        if groups is not None:
            instance.groups.set(groups)

        # Обновляем количество акоинов сотрудника, если оно предоставлено в запросе
        acoin_amount = validated_data.pop('acoin_amount', None)
        if acoin_amount is not None:
            instance.acoin.amount = acoin_amount
            instance.acoin.save()
        return super().update(instance, validated_data)

class AdminEmployeeSerializer(serializers.ModelSerializer):
    acoin_amount = serializers.IntegerField(source='acoin.amount', required=False)

    class Meta:
        model = Employee
        fields = [
            'username', 'first_name', 'last_name', 'email', 'position',
            'level', 'experience', 'next_level_experience', 'karma', 'birth_date',
            'avatar', 'status', 'is_active', 'acoin_amount', 'groups'
        ]

    def update(self, instance, validated_data):
        print(f"Serializer updating Employee: {instance.pk}")
        acoin_data = validated_data.pop('acoin', None)
        groups_data = validated_data.pop('groups', None)

        # Обновляем поля experience и karma через методы модели
        experience = validated_data.pop('experience', None)
        karma = validated_data.pop('karma', None)

        if experience is not None:
            print(f"Updating experience to {experience}")
            instance.set_experience(experience, source="Обновлено через сериализатор")

        if karma is not None:
            print(f"Updating karma to {karma}")
            instance.set_karma(karma, source="Обновлено через сериализатор")

        # Обновляем остальные поля
        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        instance.save()

        # Обновляем Acoin amount, если предоставлено
        if acoin_data:
            acoin_instance, created = Acoin.objects.get_or_create(employee=instance)
            acoin_instance.amount = acoin_data['amount']
            acoin_instance.save()

        # Обновляем группы, если предоставлено
        if groups_data:
            instance.groups.set(groups_data)

        print(f"Employee updated: {instance.pk}")
        return instance
class StatusUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Employee
        fields = ['status']
class ProfileUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Employee
        fields = ['first_name', 'last_name', 'birth_date', 'avatar']
class KarmaSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = KarmaSettings
        fields = '__all__'


class KarmaLevelSettingsSerializer(serializers.Serializer):
    level = serializers.IntegerField()
    karma_change = serializers.IntegerField()


class KarmaUpdateSerializer(serializers.Serializer):
    praise_settings = KarmaLevelSettingsSerializer(many=True, required=False)  # Поле становится опциональным
    complaint_settings = KarmaLevelSettingsSerializer(many=True, required=False)  # Поле становится опциональным

    def update_settings(self, operation_type, settings):
        for setting_data in settings:
            level = setting_data['level']
            karma_change = setting_data['karma_change']

            # Находим существующую настройку кармы по типу операции и уровню
            karma_setting = KarmaSettings.objects.filter(operation_type=operation_type, level=level).first()
            if karma_setting:
                karma_setting.karma_change = karma_change
                karma_setting.save()
            else:
                # Если запись не найдена, создаем новую
                KarmaSettings.objects.create(
                    operation_type=operation_type,
                    level=level,
                    karma_change=karma_change
                )

    def save(self):
        # Обновляем настройки для praise, если они есть
        if 'praise_settings' in self.validated_data:
            self.update_settings('praise', self.validated_data['praise_settings'])

        # Обновляем настройки для complaint, если они есть
        if 'complaint_settings' in self.validated_data:
            self.update_settings('complaint', self.validated_data['complaint_settings'])


class FeedbackSerializer(serializers.ModelSerializer):
    target_employee = serializers.PrimaryKeyRelatedField(queryset=Employee.objects.all())
    moderation_comment = serializers.CharField(required=False, allow_blank=True, allow_null=True)  # Добавлено allow_null=True

    class Meta:
        model = Feedback
        fields = [
            'id',
            'target_employee',
            'type',
            'text',
            'status',
            'created_at',
            'moderation_date',
            'moderation_comment',  # Явно включаем поле
            'moderator'
        ]

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation.pop('level', None)
        representation.pop('karma_change', None)
        representation.pop('moderator', None)
        representation.pop('moderator_comment', None)
        representation['target_employee'] = {
            "id": instance.target_employee.id,
            "full_name": f"{instance.target_employee.first_name} {instance.target_employee.last_name}"
        }
        representation['type'] = instance.get_type_display()
        return representation


class TestAttemptModerationSerializer(serializers.ModelSerializer):
    employee_name = serializers.SerializerMethodField()
    test_name = serializers.CharField(source='test.name', read_only=True)

    class Meta:
        model = TestAttempt
        fields = ['id', 'employee_name', 'test_name']

    def get_employee_name(self, obj):
        return f"{obj.employee.first_name} {obj.employee.last_name}"

from rest_framework import serializers
from django.contrib.auth.models import Group, Permission

class PermissionSerializer(serializers.ModelSerializer):
    translated_name = serializers.SerializerMethodField()

    class Meta:
        model = Permission
        fields = ['id', 'name', 'codename', 'translated_name']

    def get_translated_name(self, obj):
        return translate_permission_name(obj.name)


class GroupSerializer(serializers.ModelSerializer):
    permissions = serializers.PrimaryKeyRelatedField(queryset=Permission.objects.all(), many=True, write_only=True)
    permissions_info = PermissionSerializer(many=True, read_only=True, source='permissions')

    class Meta:
        model = Group
        fields = ['id', 'name', 'permissions', 'permissions_info']


class EmployeeActionLogSerializer(serializers.ModelSerializer):
    readable_description = serializers.SerializerMethodField()

    class Meta:
        model = EmployeeActionLog
        fields = [
            'employee',
            'action_type',
            'model_name',
            'object_id',
            'description',
            'created_at',
            'readable_description'
        ]

    def get_readable_description(self, obj):
        """
        Преобразует лог в более читабельный вид.
        """
        # Получаем полное имя сотрудника
        employee_name = f"{obj.employee.first_name} {obj.employee.last_name}"

        # Определяем шаблоны для различных моделей и типов действий
        if obj.model_name == 'TestAttempt':
            return self._handle_test_attempt(obj, employee_name)
        elif obj.model_name == 'Test':
            return self._handle_test(obj, employee_name)
        elif obj.model_name == 'EmployeeAchievement':
            return self._handle_employee_achievement(obj, employee_name)
        elif obj.model_name == 'Classifications':
            return self._handle_classifications(obj, employee_name)
        else:
            return self._handle_general(obj, employee_name)

    def _handle_classifications(self, obj, employee_name):
        """
        Обрабатывает логи для модели Classifications.
        """
        if obj.action_type == 'создано':
            # Извлекаем название и родителя из описания
            pattern = r"создал классификацию '(.+)' с родителем '(.+)'"
            match = re.search(pattern, obj.description)
            if match:
                classification_name, parent_name = match.groups()
                return f"{employee_name} создал классификацию '{classification_name}' с родителем '{parent_name}'."
            else:
                return f"{employee_name} создал классификацию."
        elif obj.action_type == 'обновлено':
            # Извлекаем изменения из описания
            return f"{employee_name} обновил классификацию: {obj.description}"
        else:
            return f"{employee_name} {obj.action_type} классификацию (ID: {obj.object_id}). {obj.description}"

    def _handle_test_attempt(self, obj, employee_name):
        """
        Обрабатывает логи для модели TestAttempt.
        """
        test_name = self._extract_field_from_description(obj.description, "тест '", "'")
        if "провалил тест" in obj.description.lower():
            return f"{employee_name} провалил тест '{test_name}'."
        elif "успешно прошёл тест" in obj.description.lower():
            return f"{employee_name} успешно прошёл тест '{test_name}'."
        elif "отправлен на модерацию" in obj.description.lower():
            return f"{employee_name} завершил тест '{test_name}', и он отправлен на модерацию."
        elif "начал прохождение теста" in obj.description.lower():
            return f"{employee_name} начал прохождение теста '{test_name}'."
        else:
            return f"{employee_name} обновил TestAttempt (ID: {obj.object_id}). {obj.description}"

    def _handle_test(self, obj, employee_name):
        """
        Обрабатывает логи для модели Test.
        """
        test_name = self._extract_field_from_description(obj.description, "тест '", "'")
        if obj.action_type == 'создано':
            return f"{employee_name} создал тест '{test_name}'."
        else:
            return f"{employee_name} обновил тест '{test_name}'."

    def _handle_employee_achievement(self, obj, employee_name):
        """
        Обрабатывает логи для модели EmployeeAchievement.
        """
        # Предполагаем, что описание содержит информацию о прогрессе и уровне
        # Пример описания:
        # "Прогресс по достижению 'Мастер обращений' изменён с 10 до 20; Уровень по достижению 'Мастер обращений' изменён с 1 до 2"

        # Разделяем описание на части
        parts = obj.description.split('; ')
        readable_parts = []

        for part in parts:
            if "Прогресс по достижению" in part:
                # Извлекаем название достижения и значения прогресса
                achievement_name, from_val, to_val = self._parse_progress_change(part)
                readable_parts.append(
                    f"Прогресс по достижению '{achievement_name}' изменён с {from_val} до {to_val}"
                )
            elif "Уровень по достижению" in part:
                # Извлекаем название достижения и значения уровня
                achievement_name, from_val, to_val = self._parse_level_change(part)
                readable_parts.append(
                    f"Уровень по достижению '{achievement_name}' изменён с {from_val} до {to_val}"
                )
            else:
                # Другие изменения, если есть
                readable_parts.append(part)

        # Объединяем все изменения в одно предложение
        change_description = "; ".join(readable_parts)
        return f"{employee_name} обновил EmployeeAchievement (ID: {obj.object_id}). {change_description}"

    def _handle_general(self, obj, employee_name):
        """
        Обрабатывает логи для всех остальных моделей.
        """
        if obj.action_type == 'deleted':
            return f"{employee_name} удалил {obj.model_name} (ID: {obj.object_id}). {obj.description}"
        elif obj.action_type == 'создано':
            return f"{employee_name} создал {obj.model_name} (ID: {obj.object_id}). {obj.description}"
        elif obj.action_type == 'обновлено':
            return f"{employee_name} обновил {obj.model_name} (ID: {obj.object_id}). {obj.description}"
        else:
            return f"{employee_name} {obj.action_type} {obj.model_name} (ID: {obj.object_id}). {obj.description}"

    def _extract_field_from_description(self, description, start_marker, end_marker):
        """
        Вспомогательная функция для извлечения подстроки между двумя маркерами.
        """
        try:
            start = description.index(start_marker) + len(start_marker)
            end = description.index(end_marker, start)
            return description[start:end]
        except ValueError:
            return "Неизвестный"

    def _parse_progress_change(self, description):
        """
        Парсит изменение прогресса из описания.
        Пример: "Прогресс по достижению 'Мастер обращений' изменён с 10 до 20"
        Возвращает (achievement_name, from_val, to_val)
        """
        pattern = r"Прогресс по достижению '(.+)' изменён с (\d+) до (\d+)"
        match = re.match(pattern, description)
        if match:
            achievement_name, from_val, to_val = match.groups()
            return achievement_name, from_val, to_val
        return "Неизвестное достижение", "0", "0"

    def _parse_level_change(self, description):
        """
        Парсит изменение уровня из описания.
        Пример: "Уровень по достижению 'Мастер обращений' изменён с 1 до 2"
        Возвращает (achievement_name, from_val, to_val)
        """
        pattern = r"Уровень по достижению '(.+)' изменён с (\d+) до (\d+)"
        match = re.match(pattern, description)
        if match:
            achievement_name, from_val, to_val = match.groups()
            return achievement_name, from_val, to_val
        return "Неизвестное достижение", "0", "0"

class GroupViewSet(viewsets.ModelViewSet):
    queryset = Group.objects.all()
    serializer_class = GroupSerializer
    permission_classes = [IsAdminUser]

class PermissionViewSet(viewsets.ModelViewSet):
    queryset = Permission.objects.all()
    serializer_class = PermissionSerializer
    permission_classes = [IsAdminUser]

class TestAttemptSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source='employee.username', read_only=True)
    test_name = serializers.CharField(source='test.name', read_only=True)
    theme_name = serializers.CharField(source='test.theme.name', read_only=True)  # Предполагаем, что есть поле theme в модели Test
    test_id = serializers.CharField(source='test.id', read_only=True)
    class Meta:
        model = TestAttempt
        fields = ['id', 'employee_name', 'test_name', 'theme_name', 'status','test_results', 'test_id' ]
class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['username', 'password']

class PermissionsSerializer(serializers.ModelSerializer):
    class Meta:
        model = Permission
        fields = ['Name', 'Content_type','Codename']

class ExperienceIncreaseSerializer(serializers.Serializer):
    employee_id = serializers.IntegerField()
    experience_points = serializers.IntegerField()
class EmployeeRegSerializer(serializers.ModelSerializer):
    class Meta:
        model = Employee
        fields = ['first_name', 'last_name', 'email', 'position', 'birth_date']

    def create(self, validated_data):
        # Извлекаем email из валидированных данных
        email = validated_data.get('email', '')
        # Используем часть email до символа '@' в качестве имени пользователя
        username = email.split('@')[0]
        # Генерируем случайный пароль
        password = get_random_string(length=10)
        # Создаем сотрудника, указывая валидированные данные и сгенерированный пароль
        employee = Employee.objects.create(password=password, username=username, **validated_data)
        return employee

class AcoinSerializer(serializers.ModelSerializer):
    class Meta:
        model = Acoin
        fields = ['employee', 'amount']

class AcoinTransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = AcoinTransaction
        fields = ['employee', 'amount', 'timestamp']


class AnswerOptionSerializer(serializers.ModelSerializer):
    question = serializers.PrimaryKeyRelatedField(queryset=TestQuestion.objects.all(), required=False)
    option_text = serializers.CharField(required=True)  # Поле option_text объявлено как обязательное

    class Meta:
        model = AnswerOption
        fields = ['id', 'question', 'option_text', 'is_correct', 'file']

    def create(self, validated_data):
        question_instance = validated_data.pop('question', None)
        instance = AnswerOption.objects.create(question=question_instance, **validated_data)
        instance.clean()  # Вызываем метод clean перед сохранением
        return instance

    def update(self, instance, validated_data):
        # Логика обновления
        instance.option_text = validated_data.get('option_text', instance.option_text)
        instance.is_correct = validated_data.get('is_correct', instance.is_correct)
        instance.file = validated_data.get('file', instance.file)
        instance.save()
        return instance
class TheorySerializer(serializers.ModelSerializer):
    image = serializers.ImageField(required=False, allow_null=True)

    class Meta:
        model = Theory
        fields = '__all__'

class ThemeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Theme
        fields = ['id', 'name']
class TestQuestionSerializer(serializers.ModelSerializer):
    answer_options = AnswerOptionSerializer(many=True, partial=True, required=False)
    image = serializers.ImageField(required=False, allow_null=True)

    def get_image(self, obj):
        if obj.image:
            url = self.context['request'].build_absolute_uri(obj.image.url)
            return url
        return None

    class Meta:
        model = TestQuestion
        fields = ['id', 'test', 'question_text', 'duration_seconds', 'question_type', 'points', 'explanation', 'image', 'position', 'answer_options']
    def get_image_url(self, obj):
        request = self.context.get('request')
        if obj.image:
            return request.build_absolute_uri(obj.image.url)
        return None
    def update(self, instance, validated_data):
        # Обновляем только те поля, которые были указаны в запросе
        instance.test = validated_data.get('test', instance.test)
        instance.question_text = validated_data.get('question_text', instance.question_text)
        instance.question_type = validated_data.get('question_type', instance.question_type)
        instance.points = validated_data.get('points', instance.points)
        instance.image = validated_data.get('image', instance.image)  # Обновляем изображение

        # Получаем данные для обновления связанных ответов
        answer_options_data = validated_data.pop('answer_options', [])

        # Обновляем связанные ответы
        for answer_option_data in answer_options_data:
            answer_option_id = answer_option_data.get('id', None)
            if answer_option_id:
                answer_option = AnswerOption.objects.get(id=answer_option_id)
                answer_option.option_text = answer_option_data.get('option_text', answer_option.option_text)
                answer_option.is_correct = answer_option_data.get('is_correct', answer_option.is_correct)
                answer_option.save()
            else:
                AnswerOption.objects.create(question=instance, **answer_option_data)

        instance.save()
        return instance

    def create(self, validated_data):
        answer_options_data = validated_data.pop('answer_options', [])
        test = validated_data.pop('test')  # Извлекаем тест из validated_data
        question = TestQuestion.objects.create(test=test, **validated_data)
        return question

class ItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = Item
        fields = ['id', 'description', 'price', 'karma_bonus', 'experience_bonus', 'duration_days']
class EmployeeItemSerializer(serializers.ModelSerializer):
    item = ItemSerializer()  # Вложенный сериализатор для отображения информации о предмете

    class Meta:
        model = EmployeeItem
        fields = ['id', 'employee', 'item', 'acquired_at', 'is_active']
class TestSerializer(serializers.ModelSerializer):
    class Meta:
        model = Test
        fields = '__all__'
        extra_kwargs = {
            'image': {'allow_null': True, 'required': False}
        }

class RequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = Request
        fields = [
            'classification', 'responsible', 'support_operator',
            'initiator', 'status', 'description', 'number',
            'date', 'is_massive'
        ]


class EmployeeAchievementSerializer(serializers.ModelSerializer):
    achievement_name = serializers.CharField(source='achievement.name')
    achievement_image_url = serializers.SerializerMethodField()

    class Meta:
        model = EmployeeAchievement
        fields = ['achievement_name', 'achievement_image_url', 'level', 'progress']

    def get_achievement_image_url(self, obj):
        if obj.achievement.image and hasattr(obj.achievement.image, 'url'):
            return f"http://shaman.pythonanywhere.com{obj.achievement.image.url}"
        return "http://shaman.pythonanywhere.com/media/default.jpg"

class ThemeWithTestsSerializer(serializers.ModelSerializer):
    tests = TestSerializer(many=True, read_only=True)

    class Meta:
        model = Test
        fields = ['theme', 'tests']

    def validate(self, data):
        # Добавьте дополнительные проверки, если необходимо
        return data

class StyleCardSerializer(serializers.Serializer):
    border_style = serializers.CharField(default='solid')
    border_width = serializers.IntegerField(default=0, required=False)
    border_color = serializers.CharField(max_length=7, default='#000000')
    use_border = serializers.BooleanField(default=False)
    textColor = serializers.CharField(max_length=7, default='#00000')
    def validate_border_width(self, value):
        if value < 0:
            raise serializers.ValidationError("Толщина рамки не может быть отрицательной.")
        return value

    def validate_border_color(self, value):
        if not re.match(r'^#(?:[0-9a-fA-F]{3}){1,2}$', value):
            raise serializers.ValidationError("Цвет рамки должен быть валидным HEX кодом.")
        return value
    def validate_textColor(self, value):
        if not re.match(r'^#(?:[0-9a-fA-F]{3}){1,2}$', value):
            raise serializers.ValidationError("Цвет текста должен быть валидным HEX кодом.")
        return value


class TypeAchContentSerializer(serializers.Serializer):
    # Удаляем поле 'type' чтобы избежать конфликта
    difficulty = serializers.ChoiceField(choices=Achievement.DIFFICULTY_CHOICES)
    request_type = serializers.PrimaryKeyRelatedField(
        queryset=Classifications.objects.all(),
        allow_null=True,
        required=False
    )
    required_count = serializers.IntegerField(default=0, required=False)
    type_specific_data = serializers.JSONField(required=False)

    def validate(self, data):
        # Добавьте дополнительные проверки, если необходимо
        return data
class NestedJSONField(serializers.Field):
    def __init__(self, serializer_class, **kwargs):
        self.serializer_class = serializer_class
        super().__init__(**kwargs)

    def to_internal_value(self, data):
        # Логирование для отладки
        print(f"NestedJSONField received data: {data}")

        if isinstance(data, str):
            try:
                data = json.loads(data)
                print(f"Parsed JSON string: {data}")
            except json.JSONDecodeError:
                raise serializers.ValidationError("Invalid JSON format.")
        elif isinstance(data, dict):
            pass  # Данные уже в виде словаря
        else:
            raise serializers.ValidationError("Invalid data type. Expected a JSON string or object.")

        # Валидируем данные с помощью вложенного сериализатора
        serializer = self.serializer_class(data=data)
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data

    def to_representation(self, value):
        serializer = self.serializer_class(value)
        return serializer.data

class TemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Template
        fields = ['id', 'name', 'image', 'is_background', 'back_image']

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        request = self.context.get('request')

        # Обработка поля image
        if request and instance.image and hasattr(instance.image, 'url'):
            representation['image'] = request.build_absolute_uri(instance.image.url)
        else:
            representation['image'] = instance.image.url if instance.image and hasattr(instance.image, 'url') else None

        # Обработка поля back_image
        if request and instance.back_image and hasattr(instance.back_image, 'url'):
            representation['back_image'] = request.build_absolute_uri(instance.back_image.url)
        else:
            representation['back_image'] = instance.back_image.url if instance.back_image and hasattr(
                instance.back_image, 'url') else None

        return representation



from rest_framework import serializers

class AchievementSerializer(serializers.ModelSerializer):
    styleCard = NestedJSONField(serializer_class=StyleCardSerializer, required=False)
    typeAchContent = NestedJSONField(serializer_class=TypeAchContentSerializer, required=False)
    template_background = serializers.PrimaryKeyRelatedField(queryset=Template.objects.filter(is_background=True), required=False, allow_null=True)
    template_foreground = serializers.PrimaryKeyRelatedField(queryset=Template.objects.filter(is_background=False), required=False, allow_null=True)
    background_image = serializers.ImageField(required=False)
    foreground_image = serializers.ImageField(required=False)
    back_image = serializers.ImageField(required=False)

    class Meta:
        model = Achievement
        fields = [
            'id', 'name', 'description', 'reward_experience', 'reward_currency', 'template_background',
            'template_foreground', 'background_image', 'foreground_image', 'back_image', 'is_award', 'is_double', 'type',
            'styleCard', 'typeAchContent',
        ]

    def get_back_image(self, instance):
        """Возвращает URL для back_image из template_background или из самой ачивки."""
        request = self.context.get('request')
        if instance.template_background and instance.template_background.back_image and hasattr(instance.template_background.back_image, 'url'):
            return request.build_absolute_uri(instance.template_background.back_image.url) if request else instance.template_background.back_image.url
        elif instance.back_image and hasattr(instance.back_image, 'url'):
            return request.build_absolute_uri(instance.back_image.url) if request else instance.back_image.url
        else:
            return None

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        request = self.context.get('request')

        # Обработка основного фона (template_background или background_image)
        if instance.background_image and hasattr(instance.background_image, 'url'):
            representation['background_image'] = request.build_absolute_uri(instance.background_image.url)
        elif instance.template_background and instance.template_background.image and hasattr(instance.template_background.image, 'url'):
            representation['background_image'] = request.build_absolute_uri(instance.template_background.image.url)
        else:
            representation['background_image'] = None

        # Обработка основной части (template_foreground или foreground_image)
        if instance.foreground_image and hasattr(instance.foreground_image, 'url'):
            representation['foreground_image'] = request.build_absolute_uri(instance.foreground_image.url)
        elif instance.template_foreground and instance.template_foreground.image and hasattr(instance.template_foreground.image, 'url'):
            representation['foreground_image'] = request.build_absolute_uri(instance.template_foreground.image.url)
        else:
            representation['foreground_image'] = None

        # Формирование объекта styleCard
        representation['styleCard'] = {
            "background_image": representation['background_image'],
            "border_style": instance.border_style,
            "border_width": instance.border_width,
            "border_color": instance.border_color,
            "use_border": instance.use_border,
            "textColor": instance.textColor,
        }

        # Формирование объекта typeAchContent
        representation['typeAchContent'] = {
            "difficulty": instance.difficulty,
            "request_type": instance.request_type.id if instance.request_type else None,
            "required_count": instance.required_count,
            "type_specific_data": instance.type_specific_data,
        }

        # Добавление текстового названия типа достижения на основе номера типа
        representation['type'] = {
            "id": instance.type,
            "name": dict(Achievement.TYPE_CHOICES).get(instance.type, "Unknown")
        }

        # Добавление back_image
        representation['back_image'] = self.get_back_image(instance)

        return representation

    def validate(self, attrs):
        # Проверка, чтобы или template_background, или back_image было заполнено
        if not attrs.get('template_background') and not attrs.get('back_image'):
            raise serializers.ValidationError("Вы должны указать либо template_background, либо back_image.")
        return attrs

    def create(self, validated_data):
        style_data = validated_data.pop('styleCard', {})
        type_content_data = validated_data.pop('typeAchContent', {})
        type_specific_data = type_content_data.pop('type_specific_data', {})

        # Создаем объект Achievement
        achievement = Achievement.objects.create(**validated_data, type_specific_data=type_specific_data)

        # Применяем поля стиля к созданному объекту
        for attr, value in style_data.items():
            setattr(achievement, attr, value)

        # Применяем поля из typeAchContent
        for attr, value in type_content_data.items():
            setattr(achievement, attr, value)

        achievement.save()
        return achievement

    def update(self, instance, validated_data):
        style_data = validated_data.pop('styleCard', {})
        type_content_data = validated_data.pop('typeAchContent', {})
        type_specific_data = type_content_data.pop('type_specific_data', {})

        # Обновляем основные поля экземпляра
        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        # Обновляем поля стиля
        for attr, value in style_data.items():
            setattr(instance, attr, value)

        # Обновляем поля контента
        for attr, value in type_content_data.items():
            setattr(instance, attr, value)

        instance.type_specific_data = type_specific_data
        instance.save()

        return instance
