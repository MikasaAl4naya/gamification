from django.db import models
from django.db.models.signals import post_save, pre_delete, post_delete
from django.dispatch import receiver
from .models import TestAttempt, AcoinTransaction, Employee, create_acoin_transaction, TestQuestion, Test, Acoin, \
    Request, Achievement, EmployeeAchievement
from django.contrib.auth.models import User, Group

@receiver(post_save, sender=TestAttempt)
def handle_test_attempt_status(sender, instance, **kwargs):
    if instance.status == TestAttempt.PASSED:
        create_acoin_transaction(instance)

@receiver(post_save, sender=TestQuestion)
@receiver(post_delete, sender=TestQuestion)
def update_total_questions(sender, instance, **kwargs):
    # Получаем тест, к которому привязан вопрос
    test = instance.test

    # Получаем общее количество вопросов для этого теста
    total_questions = TestQuestion.objects.filter(test=test).count()

    # Обновляем поле total_questions в модели Test
    Test.objects.filter(pk=test.pk).update(total_questions=total_questions)

@receiver(post_save, sender=Employee)
def create_acoin(sender, instance, created, **kwargs):
    if created:
        Acoin.objects.create(employee=instance, amount=0)

@receiver(post_save, sender=AcoinTransaction)
def update_acoin_balance(sender, instance, created, **kwargs):
    if created:
        # Обновляем баланс акоинов сотрудника в таблице Acoin
        acoin, created = Acoin.objects.get_or_create(employee=instance.employee)
        acoin.amount += instance.amount
        acoin.save()
@receiver(pre_delete, sender=models.Model)
def reorder_ids(sender, instance, **kwargs):
    # Получаем класс модели удаляемого экземпляра
    model_class = instance.__class__

    # Получаем список записей, у которых идентификатор больше чем у удаляемой записи
    records_to_reorder = model_class.objects.filter(id__gt=instance.id)

    # Перенумеровываем идентификаторы
    for record in records_to_reorder:
        record.id -= 1
        record.save(update_fields=['id'])
# Декоратор для обработки события post_save модели Employee
@receiver(post_save, sender=Employee)
def assign_group(sender, instance, created, **kwargs):
    if created:
        if instance.position == "Специалист технической поддержки":
            group = Group.objects.get(name="Модераторы")
        elif instance.position == "Координатор технической поддержки":
            group = Group.objects.get(name="Администраторы")
        else:
            group = Group.objects.get(name="Операторы")
        instance.groups.add(group)

@receiver(post_save, sender=Employee)
def assign_group(sender, instance, created, **kwargs):
    if created:
        if instance.position == "Специалист технической поддержки":
            group = Group.objects.get(name="Модераторы")
        elif instance.position == "Координатор технической поддержки":
            group = Group.objects.get(name="Администраторы")
        else:
            group = Group.objects.get(name="Операторы")
        instance.groups.add(group)
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


