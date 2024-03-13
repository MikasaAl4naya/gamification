from django.contrib.auth.models import User
from rest_framework import serializers

from main.models import Employee


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
        fields = ['id', 'username', 'email', 'position', 'level', 'experience', 'balance']


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['username', 'password']


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
        employee = Employee.objects.create(password=password,**validated_data)

        # Возвращаем созданный сотрудник и сгенерированный пароль
        return employee, password