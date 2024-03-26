from django.test import TestCase

# Create your tests here.
from django.test import TestCase
from .models import Test, TestQuestion, AnswerOption, Employee


class TestModelTestCase(TestCase):
    def test_create_test(self):
        test = Test.objects.create(name="Test", description="Description", duration_minutes=60, passing_score=70)
        self.assertIsNotNone(test)

class TestQuestionModelTestCase(TestCase):
    def test_create_question(self):
        test = Test.objects.create(name="Test", description="Description", duration_minutes=60, passing_score=70)
        question = TestQuestion.objects.create(test=test, question_text="Question", question_type="single", points=1)
        self.assertIsNotNone(question)

class AnswerOptionModelTestCase(TestCase):
    def test_create_answer_option(self):
        test = Test.objects.create(name="Test", description="Description", duration_minutes=60, passing_score=70)
        question = TestQuestion.objects.create(test=test, question_text="Question", question_type="single", points=1)
        answer_option = AnswerOption.objects.create(question=question, option_text="Option", is_correct=True)
        self.assertIsNotNone(answer_option)

# Добавьте другие тесты по мере необходимости
from rest_framework.test import APITestCase
from rest_framework import status
from django.contrib.auth.models import User
from django.urls import reverse


from django.test import TestCase
from django.contrib.auth.models import User
from rest_framework.test import APIClient
from rest_framework import status

class RegisterAPITestCase(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_register_employee(self):
        # Подготовка данных для регистрации
        data = {
            'first_name': 'John',
            'last_name': 'Doe',
            'email': 'o.putintsev@autotrade.su',
            'position': 'Developer'
        }

        # Отправка запроса на регистрацию
        response = self.client.post('/register/', data, format='json')

        # Проверка успешного ответа
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Проверка создания пользователя
        self.assertTrue(User.objects.filter(username='john.doe').exists())

        # Проверка создания сотрудника
        self.assertTrue(Employee.objects.filter(email='john.doe@example.com').exists())

class LoginAPITestCase(TestCase):
    def setUp(self):
        # Создание пользователя для тестирования входа
        self.user = User.objects.create_user(username='testuser', password='testpassword')
        self.employee = Employee.objects.create(user=self.user, email='test@example.com', position='Tester')
        self.client = APIClient()

    def test_login_employee(self):
        # Подготовка данных для входа
        data = {
            'username': 'testuser',
            'password': 'testpassword'
        }

        # Отправка запроса на вход
        response = self.client.post('/login/', data, format='json')

        # Проверка успешного ответа
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Проверка возвращаемых данных
        self.assertIn('employee', response.data)
        self.assertEqual(response.data['employee']['email'], 'test@example.com')
