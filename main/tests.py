from rest_framework.test import APITestCase
from rest_framework import status
from django.urls import reverse
from .models import Employee, AcoinTransaction, Acoin, Test, TestQuestion, AnswerOption, Theory
from .serializers import (LoginSerializer, EmployeeSerializer, UserSerializer, EmployeeRegSerializer,
                          AcoinSerializer, AcoinTransactionSerializer, AnswerOptionSerializer,
                          TheorySerializer, TestQuestionSerializer, TestSerializer)

class LoginSerializerTestCase(APITestCase):
    def test_login_serializer(self):
        data = {'username': 'test_user', 'password': 'test_password'}
        serializer = LoginSerializer(data=data)
        self.assertTrue(serializer.is_valid())

class EmployeeSerializerTestCase(APITestCase):
    def test_employee_serializer(self):
        employee = Employee.objects.create(username='test_user', email='test@example.com', position='Tester')
        serializer = EmployeeSerializer(instance=employee)
        self.assertEqual(serializer.data['username'], 'test_user')

class UserSerializerTestCase(APITestCase):
    def test_user_serializer(self):
        user_data = {'username': 'test_user', 'password': 'test_password'}
        serializer = UserSerializer(data=user_data)
        self.assertTrue(serializer.is_valid())

class EmployeeRegSerializerTestCase(APITestCase):
    def test_employee_reg_serializer(self):
        employee_data = {'first_name': 'John', 'last_name': 'Doe', 'email': 'john@example.com', 'position': 'Developer'}
        serializer = EmployeeRegSerializer(data=employee_data)
        self.assertTrue(serializer.is_valid())

class AcoinSerializerTestCase(APITestCase):
    def test_acoin_serializer(self):
        employee = Employee.objects.create(username='test_user', email='test@example.com', position='Tester')
        acoin = Acoin.objects.create(employee=employee, amount=100)
        serializer = AcoinSerializer(instance=acoin)
        self.assertEqual(serializer.data['amount'], 100)

class AcoinTransactionSerializerTestCase(APITestCase):
    def test_acoin_transaction_serializer(self):
        employee = Employee.objects.create(username='test_user', email='test@example.com', position='Tester')
        transaction_data = {'employee': employee.id, 'amount': 50}
        serializer = AcoinTransactionSerializer(data=transaction_data)
        self.assertTrue(serializer.is_valid())

class AnswerOptionSerializerTestCase(APITestCase):
    def test_answer_option_serializer(self):
        question = TestQuestion.objects.create(question_text='Test Question')
        answer_option_data = {'question': question.id, 'option_text': 'Test Option', 'is_correct': True}
        serializer = AnswerOptionSerializer(data=answer_option_data)
        self.assertTrue(serializer.is_valid())

class TheorySerializerTestCase(APITestCase):
    def test_theory_serializer(self):
        theory_data = {'title': 'Test Theory', 'content': 'Theory Content'}
        serializer = TheorySerializer(data=theory_data)
        self.assertTrue(serializer.is_valid())

class TestQuestionSerializerTestCase(APITestCase):
    def test_test_question_serializer(self):
        test = Test.objects.create(name='Test', description='Test Description')
        question_data = {'test': test.id, 'question_text': 'Test Question'}
        serializer = TestQuestionSerializer(data=question_data)
        self.assertTrue(serializer.is_valid())

class TestSerializerTestCase(APITestCase):
    def test_test_serializer(self):
        test_data = {'name': 'Test', 'description': 'Test Description'}
        serializer = TestSerializer(data=test_data)
        self.assertTrue(serializer.is_valid())
