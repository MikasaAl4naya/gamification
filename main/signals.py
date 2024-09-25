from django.contrib.admin.models import LogEntry
from django.core.exceptions import ObjectDoesNotExist
from django.db import models
from django.db.models.signals import post_save, pre_delete, post_delete
from django.dispatch import receiver
from django.forms import model_to_dict
from django.utils.translation import gettext as _
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
        operator_responsible_multiplier = ExperienceMultiplier.objects.filter(
            name="operator_responsible_multiplier").first()
        massive_request_multiplier = ExperienceMultiplier.objects.filter(name="massive_request_multiplier").first()

        # Проверяем наличие оператора поддержки
        support_operator = instance.support_operator
        if not support_operator:
            print(f"No support operator found for request {instance.number}")
            return

        # Проверяем, существует ли опыт по классификации
        experience_points = getattr(instance.classification, 'experience_points', None)
        if not experience_points:
            print(f"No experience points found for classification in request {instance.number}")
            return

        # Логика начисления опыта
        print(f"Initial experience points from classification: {experience_points}")

        # Проверяем совпадение оператора и ответственного
        responsible_full_name = instance.responsible.split()
        if len(responsible_full_name) >= 2:
            responsible_name = f"{responsible_full_name[1]} {responsible_full_name[0]}"  # Имя + Фамилия
            operator_full_name = f"{support_operator.first_name} {support_operator.last_name}"

            if responsible_name == operator_full_name:
                if operator_responsible_multiplier:
                    experience_points *= operator_responsible_multiplier.multiplier
                    print(f"Experience points after operator_responsible_multiplier: {experience_points}")
                else:
                    print("No operator_responsible_multiplier found.")

        # Увеличение опыта для массовых обращений
        if instance.is_massive:
            if massive_request_multiplier:
                experience_points *= massive_request_multiplier.multiplier
                print(f"Experience points after massive_request_multiplier: {experience_points}")
            else:
                print("No massive_request_multiplier found.")

        # Добавление опыта оператору
        if instance.is_massive:
            support_operator.add_experience(experience_points, source="За массовую")
        else:
            support_operator.add_experience(experience_points, source="За обращение")

        print(
            f"Awarded {experience_points} experience points to {support_operator.first_name} {support_operator.last_name}")
        support_operator.save()  # Сохраняем изменения в сотруднике


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
    excluded_models = [EmployeeActionLog, ShiftHistory, EmployeeLog, Request, UserSession, LogEntry]
    if sender in excluded_models:
        return

    employee = None
    if hasattr(instance, 'employee'):
        employee = instance.employee
    elif hasattr(instance, 'user'):
        employee = instance.user

    if not employee:
        return  # Если нет связанного сотрудника, не логируем

    action = 'создано' if created else 'обновлено'

    # Получаем текущие данные модели
    current_data = model_to_dict(instance)

    # Получаем предыдущие данные модели (если обновление)
    old_data = {}
    if not created:
        try:
            old_instance = sender.objects.get(pk=instance.pk)
            old_data = model_to_dict(old_instance)
        except ObjectDoesNotExist:
            pass  # В редких случаях объект может быть удален до сигнала

    changes = []
    for field, value in current_data.items():
        old_value = old_data.get(field, None)
        if old_value != value:
            # Переводим поле и формируем понятную строку изменений
            field_name = field_translation(field)
            changes.append(f"{field_name}: '{old_value}' -> '{value}'")

    # Специальная логика для различных моделей
    if sender.__name__ == 'TestAttempt':
        change_description = _handle_test_attempt_log(instance, created, changes, employee, sender, action)
    elif sender.__name__ == 'Test' and created:
        change_description = _handle_test_log(instance, created, employee, sender, action)
    elif sender.__name__ == 'EmployeeAchievement':
        change_description = _handle_employee_achievement_log(instance, old_data, current_data, employee, sender, action)
    else:
        change_description = "; ".join(changes) if changes else f"{sender.__name__} {action}"

    # Логируем изменения
    EmployeeActionLog.objects.create(
        employee=employee,
        action_type=action,
        model_name=sender.__name__,
        object_id=str(instance.pk),
        description=change_description
    )

def _handle_test_attempt_log(instance, created, changes, employee, sender, action):
    """
    Обрабатывает логи для модели TestAttempt.
    """
    test_name = instance.test.name if hasattr(instance, 'test') and instance.test else _('Неизвестный тест')
    if created:
        return f"{employee.get_full_name()} начал проходить тест '{test_name}'"
    else:
        description_lower = instance.description.lower()
        if "провалил тест" in description_lower:
            return f"{employee.get_full_name()} провалил тест '{test_name}'"
        elif "успешно прошел тест" in description_lower:
            return f"{employee.get_full_name()} успешно прошел тест '{test_name}'"
        elif "отправлен на модерацию" in description_lower:
            return f"{employee.get_full_name()} завершил тест '{test_name}', и он отправлен на модерацию"
        elif "начал проходить тест" in description_lower:
            return f"{employee.get_full_name()} начал прохождение теста '{test_name}'"
        else:
            return "; ".join(changes) if changes else f"{sender.__name__} {action}"

def _handle_test_log(instance, created, employee, sender, action):
    """
    Обрабатывает логи для модели Test.
    """
    test_name = instance.name
    if created:
        return f"{employee.get_full_name()} создал тест '{test_name}'"
    else:
        return f"{employee.get_full_name()} обновил тест '{test_name}'"

def _handle_employee_achievement_log(instance, old_data, current_data, employee, sender, action):
    """
    Обрабатывает логи для модели EmployeeAchievement.
    """
    achievement_name = instance.achievement.name if hasattr(instance, 'achievement') and instance.achievement else _("Неизвестное достижение")
    changes = []

    if old_data.get('progress') != current_data.get('progress'):
        changes.append(_(
            f"Прогресс по достижению '{achievement_name}' изменён с {old_data.get('progress')} до {current_data.get('progress')}"
        ))

    if old_data.get('level') != current_data.get('level'):
        changes.append(_(
            f"Уровень по достижению '{achievement_name}' изменён с {old_data.get('level')} до {current_data.get('level')}"
        ))

    return "; ".join(changes) if changes else f"{sender.__name__} {action}"

# Вспомогательная функция для перевода полей в читабельный вид
def field_translation(field):
    field_translations = {
        'id': 'ID',
        'employee': 'Сотрудник',
        'achievement': 'Достижение',
        'progress': 'Прогресс',
        'level': 'Уровень',
        'status': 'Статус',
        'test': 'Тест',
        'start_time': 'Время начала',
        'end_time': 'Время окончания',
        'attempts': 'Попытки',
        'test_results': 'Результаты теста',
        # Добавьте другие переводы полей по необходимости
    }
    return field_translations.get(field, field)  # Возвращаем перевод или само поле, если перевода нет

@receiver(post_delete)
def log_model_delete(sender, instance, **kwargs):
    excluded_models = [EmployeeActionLog, ShiftHistory, EmployeeLog, Request]
    if sender in excluded_models:
        return

    employee = None
    if hasattr(instance, 'employee'):
        employee = instance.employee
    elif hasattr(instance, 'user'):
        employee = instance.user

    if not employee:
        return

    EmployeeActionLog.objects.create(
        employee=employee,
        action_type='deleted',
        model_name=sender.__name__,
        object_id=str(instance.pk),
        description=f"{sender.__name__} был удален"
    )
# Вспомогательная функция для перевода полей в читабельный вид
def field_translation(field):
    field_translations = {
        'id': 'ID',
        'employee': 'Сотрудник',
        'achievement': 'Достижение',
        'progress': 'Прогресс',
        'level': 'Уровень',
        'status': 'Статус',
        'test': 'Тест',
        'start_time': 'Время начала',
        'end_time': 'Время окончания',
        'attempts': 'Попытки',
        'test_results': 'Результаты теста',
    }
    return field_translations.get(field, field)  # Возвращаем перевод или само поле, если перевода нет


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