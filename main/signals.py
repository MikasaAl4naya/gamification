from django.db import models
from django.db.models.signals import post_save, pre_delete, post_delete
from django.dispatch import receiver
from django.forms import model_to_dict

from .models import TestAttempt, AcoinTransaction, Employee, create_acoin_transaction, TestQuestion, Test, Acoin, \
    Request, Achievement, EmployeeAchievement, ExperienceMultiplier, EmployeeActionLog, ShiftHistory, EmployeeLog, \
    UserSession
from django.contrib.auth.models import User, Group

@receiver(post_save, sender=TestAttempt)
def handle_test_attempt_status(sender, instance, **kwargs):
    if instance.status == TestAttempt.PASSED:
        create_acoin_transaction(instance)
        if instance.test.achievement:
            achievement = instance.test.achievement
            if instance.score == instance.test.max_score:
                EmployeeAchievement.objects.get_or_create(employee=instance.employee, achievement=achievement)
                print(f"Awarded achievement: {achievement.name} to employee: {instance.employee}")

@receiver(post_save, sender=TestQuestion)
@receiver(post_delete, sender=TestQuestion)
def update_total_questions(sender, instance, **kwargs):
    test = instance.test
    total_questions = TestQuestion.objects.filter(test=test).count()
    Test.objects.filter(pk=test.pk).update(total_questions=total_questions)

@receiver(post_save, sender=Employee)
def create_acoin(sender, instance, created, **kwargs):
    if created:
        Acoin.objects.create(employee=instance, amount=0)

@receiver(post_save, sender=AcoinTransaction)
def update_acoin_balance(sender, instance, created, **kwargs):
    if created:
        acoin, created = Acoin.objects.get_or_create(employee=instance.employee)
        acoin.amount += instance.amount
        acoin.save()

@receiver(pre_delete, sender=models.Model)
def reorder_ids(sender, instance, **kwargs):
    model_class = instance.__class__
    records_to_reorder = model_class.objects.filter(id__gt=instance.id)
    for record in records_to_reorder:
        record.id -= 1
        record.save(update_fields=['id'])

@receiver(post_save, sender=Employee)
def assign_group(sender, instance, created, **kwargs):
    if created:
        if instance.position == "Специалист технической поддержки":
            group_name = "Модераторы"
        elif instance.position == "Координатор технической поддержки":
            group_name = "Администраторы"
        else:
            group_name = "Операторы"
        group = Group.objects.get(name=group_name)
        instance.groups.add(group)


@receiver(post_save, sender=Request)
def award_experience(sender, instance, created, **kwargs):
    if created:
        # Получаем множители из базы данных по их названиям
        operator_responsible_multiplier = ExperienceMultiplier.objects.filter(name="operator_responsible_multiplier").first()
        massive_request_multiplier = ExperienceMultiplier.objects.filter(name="massive_request_multiplier").first()

        # Базовые очки опыта
        experience_points = instance.calculate_experience()
        print(f"Initial experience points: {experience_points}")

        # Увеличение опыта, если оператор и ответственный - одно и то же лицо
        if instance.support_operator is not None and instance.responsible == instance.support_operator.username:
            if operator_responsible_multiplier:
                experience_points *= operator_responsible_multiplier.multiplier
                print(f"Experience points after operator_responsible_multiplier: {experience_points}")

        # Увеличение опыта для массовых обращений
        if instance.is_massive:
            if massive_request_multiplier:
                experience_points *= massive_request_multiplier.multiplier
                print(f"Experience points after massive_request_multiplier: {experience_points}")

        support_operator = instance.support_operator
        if support_operator is not None:
            support_operator.add_experience(experience_points)
            print(f"Awarded {experience_points} experience points to {support_operator.first_name} {support_operator.last_name}")
            support_operator.save()  # Ensure the experience is saved to the database
        else:
            print(f"No support operator found for request {instance.id}")

@receiver(post_save, sender=Request)
def update_achievement_progress(sender, instance, **kwargs):
    if instance.status == 'Completed':
        try:
            achievement = Achievement.objects.get(request_type=instance.classification)
        except Achievement.DoesNotExist:
            return

        employee_achievement, created = EmployeeAchievement.objects.get_or_create(
            employee=instance.responsible,
            achievement=achievement
        )
        employee_achievement.increment_progress()
        employee_achievement.save()


@receiver(post_save)
def log_model_save(sender, instance, created, **kwargs):
    # Исключаем отслеживание определенных моделей
    if sender in [EmployeeActionLog, ShiftHistory, EmployeeLog, Request, UserSession]:
        return

    employee = None
    if hasattr(instance, 'employee'):
        employee = instance.employee
    elif hasattr(instance, 'user'):
        employee = instance.user

    if employee:
        action = 'created' if created else 'updated'

        # Получаем текущие данные модели
        current_data = model_to_dict(instance)
        # Получаем предыдущие данные модели (если обновление)
        if not created:
            old_instance = sender.objects.get(pk=instance.pk)
            old_data = model_to_dict(old_instance)
        else:
            old_data = {}

        changes = []
        for field, value in current_data.items():
            old_value = old_data.get(field, None)
            if old_value != value:
                changes.append(f"{field}: '{old_value}' -> '{value}'")

        change_description = "; ".join(changes) if changes else f"{sender.__name__} was {action}"

        EmployeeActionLog.objects.create(
            employee=employee,
            action_type=action,
            model_name=sender.__name__,
            object_id=str(instance.pk),
            description=change_description
        )

@receiver(post_delete)
def log_model_delete(sender, instance, **kwargs):
    if sender in [EmployeeActionLog, ShiftHistory, EmployeeLog, Request]:
        return

    employee = None
    if hasattr(instance, 'employee'):
        employee = instance.employee
    elif hasattr(instance, 'user'):
        employee = instance.user

    if employee:
        EmployeeActionLog.objects.create(
            employee=employee,
            action_type='deleted',
            model_name=sender.__name__,
            object_id=str(instance.pk),
            description=f"{sender.__name__} was deleted"
        )


@receiver(post_save, sender=Request)
def track_request_classification(sender, instance, created, **kwargs):
    if created:
        try:
            employee = instance.support_operator
            request_classification = instance.classification

            request_achievements = Achievement.objects.filter(type='Requests')

            for achievement in request_achievements:
                if achievement_matches_classification(achievement, request_classification):
                    employee_achievement, created = EmployeeAchievement.objects.get_or_create(
                        employee=employee,
                        achievement=achievement
                    )
                    employee_achievement.increment_progress()

        except Exception as e:
            print(f"Ошибка при обновлении прогресса ачивки: {e}")

@receiver(pre_delete, sender=Employee)
def delete_related_logs(sender, instance, **kwargs):
    EmployeeActionLog.objects.filter(employee=instance).delete()


def achievement_matches_classification(achievement, classification):
    """
    Проверяет, соответствует ли классификация (или её родители) классификации в ачивке.
    """
    if classification == achievement.request_type:
        return True

    # Проверяем родителей классификации
    parent_classification = classification.parent
    while parent_classification:
        if parent_classification == achievement.request_type:
            return True
        parent_classification = parent_classification.parent

    return False