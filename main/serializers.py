from django.contrib.auth.models import User, Permission, Group
from django.utils.crypto import get_random_string
from rest_framework import serializers, viewsets
from rest_framework.permissions import IsAdminUser

from main.models import Employee, AcoinTransaction, Acoin, Test, TestQuestion, AnswerOption, Theory, Achievement, \
    Request, Theme, Classifications, TestAttempt, Feedback


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

class ClassificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Classifications
        fields = '__all__'

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
        # Возвращаем URL дефолтного изображения
        return "https://example.com/default_avatar.png"
class EmployeeSerializer(serializers.ModelSerializer):
    acoin_amount = serializers.IntegerField(source='acoin.amount', read_only=True)
    avatar_url = serializers.SerializerMethodField()

    class Meta:
        model = Employee
        fields = [
            'id','username', 'email', 'first_name', 'last_name', 'position', 'level', 'experience',
            'next_level_experience', 'karma', 'birth_date', 'about_me',
            'avatar_url', 'status', 'acoin_amount', 'is_active', 'groups'
        ]
        read_only_fields = ['username', 'email', 'position', 'level', 'experience', 'next_level_experience', 'karma']

    def get_avatar_url(self, obj):
        request = self.context.get('request')
        if obj.avatar and hasattr(obj.avatar, 'url'):
            return request.build_absolute_uri(obj.avatar.url)
        return None
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
            'about_me', 'avatar', 'status', 'is_active', 'acoin_amount', 'groups'
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
        fields = ['first_name', 'last_name', 'birth_date', 'about_me', 'avatar']

class FeedbackSerializer(serializers.ModelSerializer):
    target_employee = serializers.PrimaryKeyRelatedField(queryset=Employee.objects.all())

    class Meta:
        model = Feedback
        fields = '__all__'

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        if instance.status == 'pending':
            representation.pop('level', None)
            representation.pop('karma_change', None)
            representation.pop('moderator', None)
            representation.pop('moderator_comment', None)
        else:
            # Добавить детализированное представление сотрудника и типа отзыва
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
    class Meta:
        model = Permission
        fields = ['id', 'name', 'codename']

class GroupSerializer(serializers.ModelSerializer):
    permissions = serializers.PrimaryKeyRelatedField(queryset=Permission.objects.all(), many=True, write_only=True)
    permissions_info = PermissionSerializer(many=True, read_only=True, source='permissions')

    class Meta:
        model = Group
        fields = ['id', 'name', 'permissions', 'permissions_info']



    def update(self, instance, validated_data):
        permissions = validated_data.pop('permissions', None)
        instance = super(GroupSerializer, self).update(instance, validated_data)
        if permissions is not None:
            instance.permissions.set(permissions)
        return instance

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
        fields = ['classification', 'responsible', 'status']


class ThemeWithTestsSerializer(serializers.ModelSerializer):
    tests = TestSerializer(many=True, read_only=True)

    class Meta:
        model = Test
        fields = ['theme', 'tests']

class AchievementSerializer(serializers.ModelSerializer):
    class Meta:
        model = Achievement
        fields = ['id', 'name', 'description', 'type', 'request_type', 'required_count', 'reward_experience', 'reward_currency', 'image']
class ClassificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Classifications
        fields = ['id', 'name']#коммент ради коммента