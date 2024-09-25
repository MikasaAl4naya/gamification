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
    Item, EmployeeItem
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
            'id', 'first_name', 'last_name', 'level', 'experience',
            'next_level_experience', 'avatar_url', 'acoin_amount'
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
        return obj.parent.name if obj.parent else None
class PasswordPolicySerializer(serializers.ModelSerializer):

    class Meta:
        model = PasswordPolicy
        fields = '__all__'

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


class EmployeeActionLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmployeeActionLog
        fields = '__all__'
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
        acoin_data = validated_data.pop('acoin', None)
        groups_data = validated_data.pop('groups', None)

        # Update the Employee instance
        instance = super().update(instance, validated_data)

        # Update Acoin amount if present
        if acoin_data:
            acoin_instance, created = Acoin.objects.get_or_create(employee=instance)
            acoin_instance.amount = acoin_data['amount']
            acoin_instance.save()

        # Update groups if present
        if groups_data:
            instance.groups.set(groups_data)

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

from rest_framework import serializers
from .models import EmployeeActionLog


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
        else:
            return self._handle_general(obj, employee_name)

    def _handle_test_attempt(self, obj, employee_name):
        """
        Обрабатывает логи для модели TestAttempt.
        """
        test_name = self._extract_field_from_description(obj.description, "тест '", "'")
        if "провалил тест" in obj.description.lower():
            return f"{employee_name} провалил тест '{test_name}'."
        elif "успешно прошел тест" in obj.description.lower():
            return f"{employee_name} успешно прошёл тест '{test_name}'."
        elif "отправлен на модерацию" in obj.description.lower():
            return f"{employee_name} завершил тест '{test_name}', и он отправлен на модерацию."
        elif "начал проходить тест" in obj.description.lower():
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

class AchievementSerializer(serializers.ModelSerializer):
    class Meta:
        model = Achievement
        fields = '__all__'
    def get_image_url(self, obj):
        request = self.context.get('request')
        if obj.image:
            return request.build_absolute_uri(obj.image.url)
        return None
class ClassificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Classifications
        fields = ['id', 'name']#коммент ради коммента