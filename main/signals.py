from django.db import models
from django.db.models.signals import post_save, pre_delete, post_delete
from django.dispatch import receiver
from .models import TestAttempt, AcoinTransaction, Employee, create_acoin_transaction, TestQuestion, Test, Acoin, \
    Request, Achievement, EmployeeAchievement, ExperienceMultiplier
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

        # Увеличение опыта, если оператор и ответственный - одно и то же лицо
        if instance.support_operator is not None and instance.responsible == instance.support_operator.username:
            if operator_responsible_multiplier:
                experience_points *= operator_responsible_multiplier.multiplier

        # Увеличение опыта для массовых обращений
        if instance.is_massive:
            if massive_request_multiplier:
                experience_points *= massive_request_multiplier.multiplier

        support_operator = instance.support_operator
        if support_operator is not None:
            support_operator.add_experience(experience_points)
            print(f"Awarded {experience_points} experience points to {support_operator.first_name} {support_operator.last_name}")

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