import os
from datetime import datetime, timedelta, time
import pandas as pd
import re
import calendar
from django.utils import timezone
from main.models import Employee, FilePath, KarmaHistory, KarmaSettings, ShiftHistory


def get_file_path(name):
    try:
        file_path_obj = FilePath.objects.get(name=name)
        return file_path_obj.path
    except FilePath.DoesNotExist:
        print(f"Путь к файлу с именем {name} не найден.")
        return None


def process_work_schedule(file_path):
    df = pd.read_excel(file_path)

    # Находим начало таблицы (где находится заголовок "ФИО")
    start_row, start_col = find_start_of_table(df)

    if start_row is None or start_col is None:
        print("Не удалось найти заголовок 'ФИО'.")
        return None, None  # Возвращаем также start_col

    # Обрезаем строки, начиная с заголовка, оставляем все столбцы
    df = df.iloc[start_row:].reset_index(drop=True)

    # Переименовываем колонку, где находится ФИО
    df = df.rename(columns={df.columns[start_col]: 'ФИО'})

    return df, start_col  # Возвращаем start_col



def determine_late_penalty_level(start_diff):
    """Определяем уровень штрафа за опоздание в зависимости от времени опоздания."""
    if start_diff <= 5:
        return 1  # Уровень 1 - до 5 минут
    elif start_diff <= 10:
        return 2  # Уровень 2 - до 10 минут
    elif start_diff <= 20:
        return 3  # Уровень 3 - до 20 минут
    elif start_diff <= 30:
        return 4  # Уровень 4 - до 30 минут
    else:
        return 5  # Уровень 5 - более 30 минут


def check_work_time(scheduled_start, scheduled_end, actual_start, actual_end):
    try:
        # Расчет разницы в минутах между запланированным и фактическим временем начала
        start_diff = (datetime.combine(datetime.today(), actual_start) - datetime.combine(datetime.today(),
                                                                                          scheduled_start)).total_seconds() / 60.0

        # Расчет разницы в минутах между запланированным и фактическим временем окончания
        end_diff = (datetime.combine(datetime.today(), actual_end) - datetime.combine(datetime.today(),
                                                                                      scheduled_end)).total_seconds() / 60.0

        grace_period = 5  # Допустимая граница в 5 минут

        # print(f"Start difference: {start_diff} minutes, End difference: {end_diff} minutes")

        if start_diff <= grace_period and end_diff >= -grace_period:
            print("Время в пределах допустимых границ")
            return True, 0  # Время в норме, уровень опоздания 0
        else:
            late_level = determine_late_penalty_level(start_diff)
            # print(f"Опоздание уровня {late_level}")
            return False, late_level  # Определяем уровень штрафа
    except Exception as e:
        # print(f"Error in check_work_time: {e}")
        return False, 0


def extract_date_from_filename(filename):
    match = re.search(r'(\d{2}).(\d{2}).(\d{4})', filename)
    if match:
        day, month, year = map(int, match.groups())
        return datetime(year, month, day)
    return None

def find_start_of_table(df):
    for i in range(len(df)):
        for j in range(len(df.columns)):
            cell_value = str(df.iloc[i, j]).strip().lower()
            if 'фио' in cell_value:  # Ищем "ФИО" в любой форме
                # print(f"Найдено 'ФИО' в строке {i}, столбец {j}")
                return i, j
    return None, None





def time_str_to_time_obj(time_str):
    """ Преобразование строкового времени в объект datetime.time. """
    return datetime.strptime(time_str, '%H:%M').time()


def update_employee_karma(file_path):
    df = pd.read_excel(file_path)
    filename = os.path.basename(file_path)
    file_date = extract_date_from_filename(filename)
    if not file_date:
        print(f"Не удалось извлечь дату из названия файла: {filename}")
        return

    df, start_col = process_work_schedule(file_path)
    if df is None:
        print(f"Не удалось обработать файл: {file_path}")
        return

    # Определяем имена столбцов, соответствующие дням месяца
    day_columns = []
    number_of_days = calendar.monthrange(file_date.year, file_date.month)[1]
    for day in range(1, number_of_days + 1):
        column_index = start_col + day  # Предполагаем, что дни идут подряд после 'ФИО'
        if column_index < len(df.columns):
            column_name = df.columns[column_index]
            day_columns.append((day, column_name))
        else:
            day_columns.append((day, None))  # Если столбца нет

    for index, row in df.iterrows():
        try:
            full_name = row['ФИО']
            if pd.isna(full_name) or len(str(full_name).split()) < 3:
                print(f"Пропуск строки с некорректным ФИО: {full_name}")
                continue

            last_name, first_name, middle_name = full_name.split()
            print(f"Обработка {full_name} ({first_name} {last_name})")

            employees = Employee.objects.filter(first_name=first_name, last_name=last_name)

            if not employees.exists():
                print(f"Сотрудник с именем {full_name} не существует.")
                continue

            for employee in employees:
                print(f"Сотрудник: {employee.id}, Имя: {employee.first_name} {employee.last_name}")

                for day, column_name in day_columns:
                    if column_name is None:
                        print(f"Нет данных для дня {day}")
                        continue

                    shift_info = row.get(column_name, '')

                    # Проверка типа данных
                    if isinstance(shift_info, int):
                        print(f"Ошибка в данных для дня {day}: целое число {shift_info}")
                        continue

                    print(f"Данные для дня {day}: {shift_info}")

                    # Проверка на выходные или специальные пометки
                    if isinstance(shift_info, str) and any(x in shift_info.lower() for x in ['выходной', 'о', 'бс', 'б']) and not re.search(r'\d{1,2}:\d{2}', shift_info):
                        print(f"Пропуск смены для {full_name} в {file_date.year}-{file_date.month:02}-{day:02} (выходной)")
                        continue

                    if not shift_info or shift_info == '':
                        print(f"Пустые данные для {file_date.year}-{file_date.month:02}-{day:02}: '{shift_info}'")
                        continue

                    parts = re.split(r'\n|;', shift_info)

                    if len(parts) < 4:
                        print(f"Неполные данные для {file_date.year}-{file_date.month:02}-{day:02}: {parts}")
                        continue

                    scheduled_time = parts[1]
                    actual_time = parts[3]
                    print(f"Запланированное время: {scheduled_time}, Фактическое время: {actual_time}")

                    try:
                        # Парсинг времени начала и окончания
                        scheduled_start, scheduled_end = map(time_str_to_time_obj, scheduled_time.split('-'))
                        actual_start, actual_end = map(time_str_to_time_obj, actual_time.split('-'))
                    except ValueError as e:
                        print(f"Ошибка преобразования времени для {file_date.year}-{file_date.month:02}-{day:02}: {e}")
                        continue

                    # Проверка, есть ли уже запись в ShiftHistory
                    shift_date = datetime(file_date.year, file_date.month, day).date()
                    try:
                        shift_record = ShiftHistory.objects.get(
                            employee=employee,
                            date=shift_date,
                            scheduled_start=scheduled_start,
                            scheduled_end=scheduled_end
                        )
                        print(f"Найдена существующая запись в ShiftHistory для {full_name} на {shift_date}")
                    except ShiftHistory.DoesNotExist:
                        print(f"Добавление новой записи в ShiftHistory для {full_name} на {shift_date}")
                        shift_record = ShiftHistory.objects.create(
                            employee=employee,
                            date=shift_date,
                            scheduled_start=scheduled_start,
                            scheduled_end=scheduled_end,
                            actual_start=actual_start,
                            actual_end=actual_end,
                            karma_change=0,
                            experience_change=0
                        )

                    # Проверка фактического времени и начисление/штраф кармы
                    is_on_time, late_level = check_work_time(scheduled_start, scheduled_end, actual_start, actual_end)
                    print(f"Проверка: is_on_time={is_on_time}, late_level={late_level}")

                    if (shift_record.actual_start != actual_start) or (shift_record.actual_end != actual_end):
                        # Обратное применение предыдущих изменений
                        employee.karma -= shift_record.karma_change
                        employee.experience -= shift_record.experience_change

                        # Установка новых фактических времен
                        shift_record.actual_start = actual_start
                        shift_record.actual_end = actual_end

                        if is_on_time:
                            try:
                                settings = KarmaSettings.objects.get(operation_type='shift_completion')
                                shift_record.karma_change = settings.karma_change
                                shift_record.experience_change = settings.experience_change
                                employee.karma += settings.karma_change
                                employee.experience += settings.experience_change
                                print(f"Карма и опыт начислены: Карма = {settings.karma_change}, Опыт = {settings.experience_change}")
                            except KarmaSettings.DoesNotExist:
                                print("Настройки для правильного выполнения смены не найдены")
                                shift_record.karma_change = 0
                                shift_record.experience_change = 0
                        else:
                            try:
                                settings = KarmaSettings.objects.get(operation_type='late_penalty', level=late_level)
                                shift_record.karma_change = -settings.karma_change
                                shift_record.experience_change = 0  # Устанавливаем опыт в 0 при опоздании
                                employee.karma -= settings.karma_change
                                print(f"Штраф за опоздание: Карма уменьшена на {settings.karma_change}")
                            except KarmaSettings.DoesNotExist:
                                print("Настройки для штрафа за опоздание не найдены")
                                shift_record.karma_change = 0

                        # Сохраняем изменения в ShiftHistory и сотруднике
                        shift_record.save()
                        employee.save()

                        print(f"Карма и опыт сохранены для {employee.first_name} {employee.last_name}: Карма = {employee.karma}, Опыт = {employee.experience}")

                # Обновление последней даты изменения кармы
                employee.last_karma_update = timezone.make_aware(datetime.combine(file_date, time.min))
                employee.save()
                print(f"Дата последнего обновления кармы обновлена для {employee.first_name} {employee.last_name}: {employee.last_karma_update}")

        except Employee.DoesNotExist:
            print(f"Сотрудник с именем {full_name} не существует.")
        except Exception as e:
            print(f"Ошибка при обработке {full_name}: {e}")

def run_update_karma(name):
    directory_path = get_file_path(name)
    if directory_path and os.path.isdir(directory_path):
        files = [f for f in os.listdir(directory_path) if os.path.isfile(os.path.join(directory_path, f))]
        if files:
            files.sort(key=lambda x: os.path.getmtime(os.path.join(directory_path, x)), reverse=True)
            newest_file = os.path.join(directory_path, files[0])
            print(f"Обновление кармы из файла: {newest_file}")
            update_employee_karma(newest_file)
        else:
            print(f"Файлы не найдены в директории {directory_path}")
    else:
        print(f"Путь к директории для {name} не установлен или не является директорией")
