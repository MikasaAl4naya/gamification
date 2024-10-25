from datetime import timedelta

from django.contrib.admin.models import LogEntry
from django.core.exceptions import ObjectDoesNotExist
from django.db import models
from django.db.models import F, Sum
from django.db.models.signals import post_save, pre_delete, post_delete, pre_save
from django.dispatch import receiver
from django.forms import model_to_dict
from django.utils import timezone
from django.utils.translation import gettext as _
from .models import TestAttempt, AcoinTransaction, Employee, create_acoin_transaction, TestQuestion, Test, Acoin, \
    Request, Achievement, EmployeeAchievement, ExperienceMultiplier, EmployeeActionLog, ShiftHistory, EmployeeLog, \
    UserSession, ComplexityThresholds
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
    if created or instance.status == 'Completed':  # Добавляем условие, чтобы начислять опыт при завершении
        # Получаем множители
        operator_responsible_multiplier = ExperienceMultiplier.objects.filter(
            name="operator_responsible_multiplier").first()
        massive_request_multiplier = ExperienceMultiplier.objects.filter(name="massive_request_multiplier").first()

        support_operator = instance.support_operator
        if not support_operator:
            print(f"No support operator found for request {instance.number}")
            return

        experience_points = getattr(instance.classification, 'experience_points', None)
        if not experience_points:
            print(f"No experience points found for classification in request {instance.number}")
            return

        # Получаем сложность обращения
        complexity = instance.get_complexity()
        print(f"Complexity of the request: {complexity}")

        # Применяем множитель за ответственность, если оператор сам завершил обращение
        responsible_full_name = instance.responsible.split()
        if len(responsible_full_name) >= 2:
            responsible_name = f"{responsible_full_name[1]} {responsible_full_name[0]}"  # Имя + Фамилия
            operator_full_name = f"{support_operator.first_name} {support_operator.last_name}"

            if responsible_name == operator_full_name:
                if operator_responsible_multiplier:
                    experience_points *= operator_responsible_multiplier.multiplier
                    print(f"Experience points after operator_responsible_multiplier: {experience_points}")

        # Применяем множитель за массовое обращение
        if instance.is_massive:
            if massive_request_multiplier:
                experience_points *= massive_request_multiplier.multiplier
                print(f"Experience points after massive_request_multiplier: {experience_points}")

        # Добавляем опыт оператору
        support_operator.add_experience(experience_points, source=f"За {complexity} обращение {instance.number}")
        print(f"Awarded {experience_points} experience points to {support_operator.first_name} {support_operator.last_name}")
        support_operator.save()


@receiver(post_save, sender=Employee)
def track_experience_and_karma_changes(sender, instance, created, **kwargs):
    # Если сотрудник был создан, ничего не делаем
    if created:
        return

    # Получаем старые значения из базы данных
    try:
        old_instance = sender.objects.get(pk=instance.pk)
    except sender.DoesNotExist:
        return

    # Проверяем изменения опыта
    if old_instance.experience != instance.experience:
        instance.set_experience(instance.experience, source="Ручное изменение через админку или API")

    # Проверяем изменения кармы
    if old_instance.karma != instance.karma:
        instance.set_karma(instance.karma, source="Ручное изменение через админку или API")
@receiver(post_save, sender=ShiftHistory)
def track_shift_late_achievements(sender, instance, created, **kwargs):
    if created:
        try:
            employee = instance.employee

            # Получаем все достижения по отсутствию опозданий и по отработанным дням
            achievements = Achievement.objects.filter(type=4)

            # Стрик дней без опозданий
            shift_history = ShiftHistory.objects.filter(employee=employee).order_by('date')

            max_days_without_late = 0
            current_streak = 0
            last_date = None

            for shift in shift_history:
                if not shift.late:
                    if last_date:
                        day_difference = (shift.date - last_date).days
                        if day_difference > 1:
                            dates_in_between = [
                                last_date + timedelta(days=i)
                                for i in range(1, day_difference)
                            ]
                            shifts_in_between = ShiftHistory.objects.filter(
                                employee=employee,
                                date__in=dates_in_between
                            )
                            if not shifts_in_between.exists():
                                current_streak += 1
                            else:
                                current_streak = 1
                        else:
                            current_streak += 1
                    else:
                        current_streak = 1
                    max_days_without_late = max(max_days_without_late, current_streak)
                else:
                    current_streak = 0
                last_date = shift.date

            # Общее количество дней без опозданий
            total_days_without_late = ShiftHistory.objects.filter(employee=employee, late=False).count()

            # Общее количество отработанных дней
            total_worked_days = ShiftHistory.objects.filter(employee=employee).values('date').distinct().count()

            for achievement in achievements:
                if achievement.type_specific_data:
                    type_data = achievement.type_specific_data

                    # Проверяем достижение на 10 дней подряд без опозданий
                    if 'streak_days_required' in type_data:
                        required_streak = type_data['streak_days_required']
                        employee_achievement, created = EmployeeAchievement.objects.get_or_create(
                            employee=employee,
                            achievement=achievement
                        )
                        # Обновляем прогресс по стрику
                        if max_days_without_late > employee_achievement.progress:
                            employee_achievement.progress = min(max_days_without_late, required_streak)
                            if employee_achievement.progress >= required_streak and not employee_achievement.date_awarded:
                                employee_achievement.date_awarded = timezone.now()
                            employee_achievement.save()
                    if 'total_days_required' in type_data:
                        required_total = type_data['total_days_required']
                        employee_achievement, created = EmployeeAchievement.objects.get_or_create(
                            employee=employee,
                            achievement=achievement
                        )
                        # Обновляем прогресс по общему количеству дней без опозданий
                        if total_days_without_late > employee_achievement.progress:
                            employee_achievement.progress = min(total_days_without_late, required_total)
                            if employee_achievement.progress >= required_total and not employee_achievement.date_awarded:
                                employee_achievement.date_awarded = timezone.now()
                            employee_achievement.save()

                    # Проверяем достижение на общее количество отработанных дней
                    if 'total_worked_days_required' in type_data:
                        required_worked_days = type_data['total_worked_days_required']
                        employee_achievement, created = EmployeeAchievement.objects.get_or_create(
                            employee=employee,
                            achievement=achievement
                        )
                        # Обновляем прогресс по общему количеству отработанных дней
                        if total_worked_days > employee_achievement.progress:
                            employee_achievement.progress = min(total_worked_days, required_worked_days)
                            if employee_achievement.progress >= required_worked_days and not employee_achievement.date_awarded:
                                employee_achievement.date_awarded = timezone.now()
                            employee_achievement.save()

        except Exception as e:
            print(f"Ошибка при обновлении прогресса ачивки: {e}")

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
    excluded_models = [EmployeeActionLog, ShiftHistory, EmployeeLog, Request, UserSession, LogEntry, EmployeeAchievement, Acoin, AcoinTransaction]
    if sender in excluded_models:
        return

    employee = None
    if hasattr(instance, 'employee'):
        employee = instance.employee
    elif hasattr(instance, 'user'):
        employee = instance.user

    # Специальная обработка для Classifications
    if sender.__name__ == 'Classifications' and not employee:
        try:
            employee = Employee.objects.get(username='oleg')
        except Employee.DoesNotExist:
            print("Employee with username 'oleg' does not exist.")
            return

    if not employee:
        return  # Если нет связанного сотрудника, не логируем

    action = 'создано' if created else 'обновлено'

    # Обработка для модели EmployeeAchievement
    if sender.__name__ == 'EmployeeAchievement':
        # Логируем только если достижение завершено и выдано (т.е. есть date_awarded)
        if instance.date_awarded:
            change_description = _handle_employee_achievement_log(instance, employee, sender, action)
            EmployeeActionLog.objects.create(
                employee=employee,
                action_type=action,
                model_name=sender.__name__,
                object_id=str(instance.pk),
                description=change_description
            )
        return  # Выходим из обработчика, чтобы избежать ненужных логов для EmployeeAchievement

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
    elif sender.__name__ == 'Classifications':
        change_description = _handle_classification_log(instance, old_data, current_data, employee, sender, action)
    else:
        change_description = "; ".join(changes) if changes else f"{sender.__name__} {action}"

    # Логируем изменения для всех остальных моделей
    EmployeeActionLog.objects.create(
        employee=employee,
        action_type=action,
        model_name=sender.__name__,
        object_id=str(instance.pk),
        description=change_description
    )

def _handle_employee_achievement_log(instance, employee, sender, action):
    """
    Обрабатывает логи для модели EmployeeAchievement, когда достижение выдается.
    """
    achievement_name = instance.achievement.name if hasattr(instance, 'achievement') and instance.achievement else _("Неизвестное достижение")
    return f"{employee.get_full_name()} получил достижение '{achievement_name}' с уровнем {instance.level}."
def _handle_classification_log(instance, old_data, current_data, employee, sender, action):
    """
    Обрабатывает логи для модели Classifications.
    """
    if action == 'создано':
        parent = instance.parent.name if instance.parent else 'None'
        return f"{employee.get_full_name()} создал классификацию '{instance.name}' с родителем '{parent}'."
    else:
        changes = []
        if old_data.get('name') != current_data.get('name'):
            changes.append(f"Название изменено с '{old_data.get('name')}' на '{current_data.get('name')}'")
        if old_data.get('parent') != current_data.get('parent'):
            old_parent = old_data.get('parent')
            new_parent = current_data.get('parent')
            old_parent_name = old_parent.name if old_parent else 'None'
            new_parent_name = new_parent.name if new_parent else 'None'
            changes.append(f"Родитель изменен с '{old_parent_name}' на '{new_parent_name}'")
        return "; ".join(changes) if changes else f"{sender.__name__} {action}"



def _handle_test_attempt_log(instance, created, changes, employee, sender, action):
    """
    Обрабатывает логи для модели TestAttempt.
    """
    test_name = instance.test.name if hasattr(instance, 'test') and instance.test else _('Неизвестный тест')

    if created:
        return f"{employee.get_full_name()} начал проходить тест '{test_name}'"
    else:
        status_lower = instance.status.lower()

        if instance.status == TestAttempt.PASSED:
            return f"{employee.get_full_name()} успешно прошёл тест '{test_name}'"
        elif instance.status == TestAttempt.FAILED:
            return f"{employee.get_full_name()} провалил тест '{test_name}'"
        elif instance.status == TestAttempt.MODERATION:
            return f"{employee.get_full_name()} завершил тест '{test_name}', и он отправлен на модерацию"
        elif instance.status == TestAttempt.IN_PROGRESS:
            return f"{employee.get_full_name()} начал прохождение теста '{test_name}'"
        else:
            return "; ".join(changes) if changes else f"{sender.__name__} {action}"

@receiver(post_save, sender=EmployeeLog)
def track_karma_and_acoin_achievements(sender, instance, created, **kwargs):
    try:
        # Получаем текущего сотрудника и тип изменения
        employee = instance.employee
        change_type = instance.change_type

        # Получаем текущие дату и время для вычисления периодов
        today = timezone.now()
        start_of_day = today.replace(hour=0, minute=0, second=0, microsecond=0)
        start_of_week = today - timedelta(days=today.weekday())
        start_of_week = start_of_week.replace(hour=0, minute=0, second=0, microsecond=0)
        start_of_month = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        # Получаем все достижения типа "Indicators"
        indicator_achievements = Achievement.objects.filter(type=6)

        for achievement in indicator_achievements:
            type_specific_data = achievement.type_specific_data

            # Логика для кармы
            if change_type == 'karma':
                # Заработано кармы
                if 'karma_earned' in type_specific_data:
                    required_karma = type_specific_data['karma_earned']
                    total_karma_earned = EmployeeLog.objects.filter(
                        employee=employee,
                        change_type='karma',
                        new_value__gt=F('old_value')
                    ).annotate(gain=F('new_value') - F('old_value')).aggregate(total=Sum('gain'))['total'] or 0

                    # Найти или создать объект EmployeeAchievement
                    employee_achievement, created = EmployeeAchievement.objects.get_or_create(
                        employee=employee,
                        achievement=achievement
                    )

                    if total_karma_earned >= required_karma and not employee_achievement.date_awarded:
                        employee_achievement.progress = required_karma
                        employee_achievement.reward_employee()
                        employee_achievement.date_awarded = timezone.now()

                # Заработать кармы за день, неделю, месяц
                if 'karma_earned_day' in type_specific_data:
                    required_karma_day = type_specific_data['karma_earned_day']
                    karma_earned_day = EmployeeLog.objects.filter(
                        employee=employee,
                        change_type='karma',
                        timestamp__gte=start_of_day,
                        new_value__gt=F('old_value')
                    ).annotate(gain=F('new_value') - F('old_value')).aggregate(total=Sum('gain'))['total'] or 0

                    if karma_earned_day >= required_karma_day and not employee_achievement.date_awarded:
                        employee_achievement.progress = required_karma_day
                        employee_achievement.reward_employee()
                        employee_achievement.date_awarded = timezone.now()

                if 'karma_earned_week' in type_specific_data:
                    required_karma_week = type_specific_data['karma_earned_week']
                    karma_earned_week = EmployeeLog.objects.filter(
                        employee=employee,
                        change_type='karma',
                        timestamp__gte=start_of_week,
                        new_value__gt=F('old_value')
                    ).annotate(gain=F('new_value') - F('old_value')).aggregate(total=Sum('gain'))['total'] or 0

                    if karma_earned_week >= required_karma_week and not employee_achievement.date_awarded:
                        employee_achievement.progress = required_karma_week
                        employee_achievement.reward_employee()
                        employee_achievement.date_awarded = timezone.now()

                if 'karma_earned_month' in type_specific_data:
                    required_karma_month = type_specific_data['karma_earned_month']
                    karma_earned_month = EmployeeLog.objects.filter(
                        employee=employee,
                        change_type='karma',
                        timestamp__gte=start_of_month,
                        new_value__gt=F('old_value')
                    ).annotate(gain=F('new_value') - F('old_value')).aggregate(total=Sum('gain'))['total'] or 0

                    if karma_earned_month >= required_karma_month and not employee_achievement.date_awarded:
                        employee_achievement.progress = required_karma_month
                        employee_achievement.reward_employee()
                        employee_achievement.date_awarded = timezone.now()

            # Логика для акоинов
            if change_type == 'acoins':
                # Заработать акоины
                if 'acoins_earned' in type_specific_data:
                    required_acoins = type_specific_data['acoins_earned']
                    total_acoins_earned = AcoinTransaction.objects.filter(
                        employee=employee
                    ).aggregate(total=Sum('amount'))['total'] or 0

                    # Найти или создать объект EmployeeAchievement
                    employee_achievement, created = EmployeeAchievement.objects.get_or_create(
                        employee=employee,
                        achievement=achievement
                    )

                    if total_acoins_earned >= required_acoins and not employee_achievement.date_awarded:
                        employee_achievement.progress = required_acoins
                        employee_achievement.reward_employee()
                        employee_achievement.date_awarded = timezone.now()

                # Заработать акоины за день, неделю, месяц
                if 'acoins_earned_day' in type_specific_data:
                    required_acoins_day = type_specific_data['acoins_earned_day']
                    acoins_earned_day = AcoinTransaction.objects.filter(
                        employee=employee,
                        timestamp__gte=start_of_day
                    ).aggregate(total=Sum('amount'))['total'] or 0

                    if acoins_earned_day >= required_acoins_day and not employee_achievement.date_awarded:
                        employee_achievement.progress = required_acoins_day
                        employee_achievement.reward_employee()
                        employee_achievement.date_awarded = timezone.now()

                if 'acoins_earned_week' in type_specific_data:
                    required_acoins_week = type_specific_data['acoins_earned_week']
                    acoins_earned_week = AcoinTransaction.objects.filter(
                        employee=employee,
                        timestamp__gte=start_of_week
                    ).aggregate(total=Sum('amount'))['total'] or 0

                    if acoins_earned_week >= required_acoins_week and not employee_achievement.date_awarded:
                        employee_achievement.progress = required_acoins_week
                        employee_achievement.reward_employee()
                        employee_achievement.date_awarded = timezone.now()

                if 'acoins_earned_month' in type_specific_data:
                    required_acoins_month = type_specific_data['acoins_earned_month']
                    acoins_earned_month = AcoinTransaction.objects.filter(
                        employee=employee,
                        timestamp__gte=start_of_month
                    ).aggregate(total=Sum('amount'))['total'] or 0

                    if acoins_earned_month >= required_acoins_month and not employee_achievement.date_awarded:
                        employee_achievement.progress = required_acoins_month
                        employee_achievement.reward_employee()
                        employee_achievement.date_awarded = timezone.now()

            # Сохраняем изменения в объекте EmployeeAchievement
            employee_achievement.save()

    except Exception as e:
        print(f"Ошибка при отслеживании прогресса показателей: {e}")
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
        'name': 'Название',
        'parent': 'Родитель',
        # Добавьте другие переводы полей по необходимости
    }
    return field_translations.get(field, field)  # Возвращаем перевод или само поле, если перевода нет
@receiver(post_save, sender=TestAttempt)
def track_test_achievement(sender, instance, created, **kwargs):
    if created and instance.status == TestAttempt.PASSED:
        try:
            employee = instance.employee
            test_id = instance.test.id

            # Найти все достижения, которые связаны с данным тестом
            test_achievements = Achievement.objects.filter(
                type=5,  # Тип достижения "Тест"
                type_specific_data__test_id=test_id
            )

            for achievement in test_achievements:
                # Проверка выполнения условия (например, процент правильных ответов)
                required_score = achievement.type_specific_data.get("required_score", None)
                if required_score is None or instance.score >= required_score:
                    # Найти или создать EmployeeAchievement
                    employee_achievement, created = EmployeeAchievement.objects.get_or_create(
                        employee=employee,
                        achievement=achievement
                    )
                    # Если достижение только что создано или прогресс не завершён, обновляем прогресс
                    if created or employee_achievement.progress < 1:
                        employee_achievement.progress = 1
                        employee_achievement.reward_employee()  # Выдаем награду
                        employee_achievement.date_awarded = timezone.now()  # Фиксируем дату награждения
                        employee_achievement.save()

        except Exception as e:
            print(f"Ошибка при отслеживании прогресса тестового достижения: {e}")

@receiver(post_save, sender=TestAttempt)
def track_test_attempt_achievements(sender, instance, created, **kwargs):
    try:
        employee = instance.employee

        # Получаем все достижения, относящиеся к тестам
        test_achievements = Achievement.objects.filter(type=5)

        # Проверяем, какие достижения связаны с количеством тестов
        for achievement in test_achievements:
            if achievement.type_specific_data:
                type_data = achievement.type_specific_data

                required_tests = type_data.get('total_tests_required')
                required_successful_tests = type_data.get('successful_tests_required')
                required_perfect_score_tests = type_data.get('perfect_score_tests_required')
                required_moderation_tests = type_data.get('moderation_tests_required')

                # Найти или создать объект EmployeeAchievement
                employee_achievement, created = EmployeeAchievement.objects.get_or_create(
                    employee=employee,
                    achievement=achievement
                )

                # Отслеживаем прогресс по каждому условию отдельно
                progress_total_tests = 0
                progress_successful_tests = 0
                progress_perfect_score_tests = 0
                progress_moderation_tests = 0
                total_conditions = 0
                fulfilled_conditions = 0

                # Отслеживаем прогресс по общему количеству выполненных тестов
                if required_tests is not None:
                    total_tests_completed = TestAttempt.objects.filter(
                        employee=employee, status=TestAttempt.PASSED
                    ).count()
                    progress_total_tests = min(total_tests_completed, required_tests)
                    total_conditions += 1
                    if total_tests_completed >= required_tests:
                        fulfilled_conditions += 1

                # Отслеживаем прогресс по успешным тестам
                if required_successful_tests is not None:
                    successful_tests_completed = TestAttempt.objects.filter(
                        employee=employee,
                        status=TestAttempt.PASSED
                    ).count()
                    progress_successful_tests = min(successful_tests_completed, required_successful_tests)
                    total_conditions += 1
                    if successful_tests_completed >= required_successful_tests:
                        fulfilled_conditions += 1

                # Отслеживаем прогресс по тестам, выполненным на 100%
                if required_perfect_score_tests is not None:
                    perfect_score_tests_completed = TestAttempt.objects.filter(
                        employee=employee,
                        score=instance.test.max_score
                    ).count()
                    progress_perfect_score_tests = min(perfect_score_tests_completed, required_perfect_score_tests)
                    total_conditions += 1
                    if perfect_score_tests_completed >= required_perfect_score_tests:
                        fulfilled_conditions += 1

                # Отслеживаем прогресс по модерации тестов
                if required_moderation_tests is not None:
                    moderation_tests_completed = TestAttempt.objects.filter(
                        employee=employee,
                        status=TestAttempt.MODERATION
                    ).count()
                    progress_moderation_tests = min(moderation_tests_completed, required_moderation_tests)
                    total_conditions += 1
                    if moderation_tests_completed >= required_moderation_tests:
                        fulfilled_conditions += 1

                # Обновляем прогресс достижения
                total_progress = (progress_total_tests + progress_successful_tests +
                                 progress_perfect_score_tests + progress_moderation_tests)
                employee_achievement.progress = total_progress

                # Если все указанные условия выполнены, фиксируем дату награждения и выдаем награду
                if fulfilled_conditions == total_conditions and not employee_achievement.date_awarded:
                    employee_achievement.reward_employee()
                    employee_achievement.date_awarded = timezone.now()

                # Сохраняем изменения в объекте EmployeeAchievement
                employee_achievement.save()

    except Exception as e:
        print(f"Ошибка при отслеживании прогресса теста: {e}")

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
@receiver(pre_delete, sender=Employee)
def delete_related_logs(sender, instance, **kwargs):
    EmployeeActionLog.objects.filter(employee=instance).delete()


@receiver(post_save, sender=Request)
def track_request_classification(sender, instance, created, **kwargs):
    if created:
        try:
            employee = instance.support_operator
            request_classification = instance.classification
            is_massive = instance.is_massive

            # Фильтрация достижений типа "Обращения" (type=1)
            request_achievements = Achievement.objects.filter(type=1)

            for achievement in request_achievements:
                # Получаем данные из type_specific_data для каждого достижения
                type_specific_data = achievement.type_specific_data
                required_requests_count = type_specific_data.get("required_requests_count")
                required_classification_ids = type_specific_data.get("classification_ids", [])
                is_massive_required = type_specific_data.get("is_massive", False)

                # Проверяем соответствие классификации и типу обращения
                if request_classification.id in required_classification_ids and is_massive == is_massive_required:
                    # Найти или создать объект EmployeeAchievement
                    employee_achievement, _ = EmployeeAchievement.objects.get_or_create(
                        employee=employee,
                        achievement=achievement
                    )

                    # Увеличить прогресс на 1
                    if required_requests_count:
                        current_progress = employee_achievement.progress + 1
                        employee_achievement.progress = current_progress
                        progress_percent = min(current_progress / required_requests_count, 1.0) * 100

                        # Обновляем процент выполнения достижения
                        employee_achievement.progress_percent = progress_percent

                        # Проверяем, достигнут ли необходимый прогресс для награждения
                        if current_progress >= required_requests_count and not employee_achievement.date_awarded:
                            employee_achievement.reward_employee()
                            employee_achievement.date_awarded = timezone.now()

                        # Сохраняем изменения в объекте EmployeeAchievement
                        employee_achievement.save()

        except Exception as e:
            print(f"Ошибка при обновлении прогресса ачивки: {e}")

@receiver(post_save, sender=Employee)
def track_employee_level_and_experience(sender, instance, **kwargs):
    try:
        # Получаем текущий уровень и опыт сотрудника
        current_level = instance.level
        current_exp = instance.experience
        today = timezone.now()
        start_of_week = today - timedelta(days=today.weekday())
        start_of_week = start_of_week.replace(hour=0, minute=0, second=0, microsecond=0)

        # Фильтрация достижений типа "NewLvl" (type=3)
        level_achievements = Achievement.objects.filter(type=3)

        total_experience_earned_week = EmployeeLog.objects.filter(
            employee=instance,
            change_type='experience',
            timestamp__gte=start_of_week,
            new_value__gt=F('old_value')
        ).annotate(gain=F('new_value') - F('old_value')).aggregate(total=Sum('gain'))['total'] or 0

        for achievement in level_achievements:
            type_specific_data = achievement.type_specific_data
            required_level = type_specific_data.get("required_level")
            exp_earned = type_specific_data.get("exp_earned")
            exp_earned_week = type_specific_data.get("exp_earned_week")

            # Найти или создать объект EmployeeAchievement
            employee_achievement, created = EmployeeAchievement.objects.get_or_create(
                employee=instance,
                achievement=achievement
            )

            # Инициализируем список для хранения прогрессов по каждому условию
            progress_values = []

            # Проверяем прогресс по уровню
            if required_level is not None:
                level_progress = min(current_level / required_level, 1.0) * 100  # Прогресс по уровню в процентах
                progress_values.append(level_progress)

                # Обновляем прогресс, если уровень достигнут
                if current_level >= required_level:
                    employee_achievement.progress = required_level
                    if not employee_achievement.date_awarded:
                        employee_achievement.reward_employee()
                        employee_achievement.date_awarded = timezone.now()

            # Проверяем прогресс по общему заработанному опыту
            if exp_earned is not None:
                experience_progress = min(current_exp / exp_earned, 1.0) * 100  # Прогресс по опыту в процентах
                progress_values.append(experience_progress)

                if current_exp >= exp_earned:
                    employee_achievement.progress = exp_earned
                    if not employee_achievement.date_awarded:
                        employee_achievement.reward_employee()
                        employee_achievement.date_awarded = timezone.now()

            # Проверяем прогресс по заработанному опыту за неделю
            if exp_earned_week is not None:
                weekly_exp_progress = min(total_experience_earned_week / exp_earned_week, 1.0) * 100  # Прогресс по неделе
                progress_values.append(weekly_exp_progress)

                if total_experience_earned_week >= exp_earned_week:
                    employee_achievement.progress = exp_earned_week
                    if not employee_achievement.date_awarded:
                        employee_achievement.reward_employee()
                        employee_achievement.date_awarded = timezone.now()

            # Рассчитываем общий прогресс
            if progress_values:
                overall_progress_percent = min(progress_values)  # Общий прогресс равен минимальному из всех условий
                employee_achievement.progress_percent = overall_progress_percent

            # Сохраняем изменения в объекте EmployeeAchievement
            employee_achievement.save()

    except Exception as e:
        print(f"Ошибка при отслеживании прогресса уровня и опыта: {e}")
