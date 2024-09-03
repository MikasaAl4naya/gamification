from django.test import TestCase
from main.models import Test, TestAttempt, Employee, Achievement, EmployeeAchievement, AcoinTransaction

class AchievementTestCase(TestCase):
    def setUp(self):
        self.employee = Employee.objects.create(name="Test Employee")
        self.achievement = Achievement.objects.create(
            name="Test Achievement",
            description="Awarded for perfect score",
            type="Test",
            required_count=1,
            reward_experience=50,
            reward_currency=100
        )
        self.test = Test.objects.create(
            name="Sample Test",
            max_score=100,
            achievement=self.achievement
        )
        self.test_attempt = TestAttempt.objects.create(
            employee=self.employee,
            test=self.test,
            status=TestAttempt.PASSED,
            score=100  # Max score
        )

    def test_achievement_awarded(self):
        employee_achievement = EmployeeAchievement.objects.get(employee=self.employee, achievement=self.achievement)
        self.assertEqual(employee_achievement.level, 1)

    def test_acoin_transaction_created(self):
        self.assertTrue(AcoinTransaction.objects.filter(employee=self.employee, amount=self.test.acoin_reward).exists())

    def test_experience_and_acoins_awarded(self):
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.experience, 50)
        self.assertEqual(self.employee.acoins, 100)
