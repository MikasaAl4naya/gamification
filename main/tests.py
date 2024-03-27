from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status
from .models import Test, Employee, AcoinTransaction
from django.contrib.auth.models import User

class APITests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_get_all_tests(self):
        response = self.client.get('/api/tests/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_get_test_by_id(self):
        test = Test.objects.create(name='Test', description='Description')
        response = self.client.get(f'/api/test/{test.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_get_all_users(self):
        response = self.client.get('/users/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_get_user(self):
        user = User.objects.create(username='testuser')
        response = self.client.get(f'/user/{user.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_get_user_balance(self):
        user = Employee.objects.create(username='testuser')
        response = self.client.get(f'/user/{user.id}/balance/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_get_user_transactions(self):
        user = Employee.objects.create(username='testuser')
        response = self.client.get(f'/user/{user.id}/transactions/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_create_acoin_transaction(self):
        user = Employee.objects.create(username='testuser')
        data = {'user': user.id, 'amount': 100}
        response = self.client.post('/api/create_acoin_transaction/', data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(AcoinTransaction.objects.count(), 1)
