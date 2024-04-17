from django.contrib.auth.models import User
from rest_framework import serializers

from main.models import Employee, AcoinTransaction, Acoin, Test, TestQuestion, AnswerOption, Theory, Achievement, \
    Request


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


class EmployeeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Employee
        fields = ['id', 'username', 'email', 'position', 'level', 'experience']


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['username', 'password']

class ExperienceIncreaseSerializer(serializers.Serializer):
    employee_id = serializers.IntegerField()
    experience_points = serializers.IntegerField()
class EmployeeRegSerializer(serializers.ModelSerializer):
    class Meta:
        model = Employee
        fields = ['first_name', 'last_name', 'email', 'position']

    def create(self, validated_data):
        # Извлекаем email из валидированных данных
        email = validated_data.get('email', '')
        # Используем часть email до символа '@' в качестве имени пользователя
        username = email.split('@')[0]
        # Генерируем случайный пароль
        password = User.objects.make_random_password()
        # Создаем пользователя с сгенерированным паролем и email в качестве username
        user = User.objects.create_user(username=username, password=password, email=email)
        # Создаем сотрудника, указывая пользователя как его владельца
        employee = Employee.objects.create(password=password, **validated_data)
        # Возвращаем созданный сотрудник и сгенерированный пароль
        return employee, password

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
    class Meta:
        model = Theory
        fields = '__all__'

class TestQuestionSerializer(serializers.ModelSerializer):
    answer_options = AnswerOptionSerializer(many=True, partial=True,required=False)
    image = serializers.SerializerMethodField()

    def get_image(self, obj):
        if obj.image:
            url = self.context['request'].build_absolute_uri(obj.image)
            return url
        return None

    class Meta:
        model = TestQuestion
        fields = ['id', 'test', 'question_text', 'question_type', 'points', 'explanation', 'image',  'answer_options']

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
    theories = TheorySerializer(many=True, read_only=True)

    class Meta:
        model = Test
        fields = ['id', 'name', 'description', 'duration_seconds', 'passing_score', 'unlimited_time', 'show_correct_answers', 'theme', 'required_karma','experience_points', 'acoin_reward', 'min_level', 'achievement', 'total_questions', 'can_attempt_twice', 'send_results_to_email', 'theories']


    def update(self, instance, validated_data):
        # Логика обновления
        instance.name = validated_data.get('name', instance.name)
        instance.description = validated_data.get('description', instance.description)
        instance.duration_minutes = validated_data.get('duration_minutes', instance.duration_minutes)
        instance.passing_score = validated_data.get('passing_score', instance.passing_score)
        instance.save()
        return instance
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