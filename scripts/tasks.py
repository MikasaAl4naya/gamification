import os
from datetime import datetime, timedelta, time
import pandas as pd
import re
import calendar
from django.utils import timezone
from main.models import Employee, FilePath, KarmaHistory

def get_file_path(name):
    try:
        file_path_obj = FilePath.objects.get(name=name)
        return file_path_obj.path
    except FilePath.DoesNotExist:
        print(f"Путь к файлу с именем {name} не найден.")
        return None

def process_work_schedule(file_path):
    df = pd.read_excel(file_path)
    start_row, start_col = find_start_of_table(df)
    if start_row is None or start_col is None:
        print("Не удалось найти начало таблицы.")
        return None
    df = df.iloc[start_row:, start_col:].reset_index(drop=True)
    df = df.rename(columns={df.columns[0]: 'ФИО', df.columns[1]: 'Город'})
    return df

def check_work_time(scheduled_start, scheduled_end, actual_start, actual_end):
    fmt = '%H:%M'
    scheduled_start_dt = datetime.strptime(scheduled_start, fmt)
    scheduled_end_dt = datetime.strptime(scheduled_end, fmt)
    actual_start_dt = datetime.strptime(actual_start, fmt)
    actual_end_dt = datetime.strptime(actual_end, fmt)

    start_diff = (actual_start_dt - scheduled_start_dt).total_seconds() / 60.0
    end_diff = (actual_end_dt - scheduled_end_dt).total_seconds() / 60.0

    grace_period = 10

    if start_diff <= grace_period and end_diff >= -grace_period:
        return True

    return False

def extract_date_from_filename(filename):
    match = re.search(r'(\d{2}).(\d{2}).(\d{4})', filename)
    if match:
        day, month, year = map(int, match.groups())
        return datetime(year, month, day)
    return None

def find_start_of_table(df):
    for i in range(len(df)):
        for j in range(len(df.columns)):
            if str(df.iloc[i, j]).lower() == 'фио':
                return i + 1, j  # Предполагается, что данные начинаются на следующей строке
    return None, None

def update_employee_karma(file_path):
    df = pd.read_excel(file_path)
    filename = os.path.basename(file_path)
    file_date = extract_date_from_filename(filename)
    if not file_date:
        print(f"Не удалось извлечь дату из названия файла: {filename}")
        return

    df = process_work_schedule(file_path)
    if df is None:
        print(f"Не удалось обработать файл: {file_path}")
        return

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
                print(f"Сотрудник: {employee.id}, Имя: {employee.first_name} {employee.last_name}, Last karma update: {employee.last_karma_update}")

                last_karma_update = employee.last_karma_update

                if last_karma_update:
                    last_update_date = last_karma_update.date()
                else:
                    last_update_date = file_date.replace(day=1)

                print(f"Последнее обновление кармы: {last_update_date}")
                print(f"Дата из файла: {file_date}")

                update_day = last_update_date.day + 1
                update_month = last_update_date.month
                update_year = last_update_date.year

                last_processed_date = last_update_date

                while (update_year, update_month, update_day) <= (file_date.year, file_date.month, file_date.day):
                    # Проверка существования даты
                    if update_day > calendar.monthrange(update_year, update_month)[1]:
                        update_day = 1
                        update_month += 1
                        if update_month > 12:
                            update_month = 1
                            update_year += 1

                    if (update_year, update_month) == (file_date.year, file_date.month) and update_day > file_date.day:
                        break

                    # Извлечение информации о смене
                    shift_info = row.get(f'Unnamed: {update_day}', '').strip().lower()
                    print(shift_info)
                    if any(x in shift_info for x in ['выходной', 'о', 'бс', 'б']):
                        print(f"Пропуск смены для {full_name} в {update_year}-{update_month:02}-{update_day:02} (выходной)")
                        last_processed_date = datetime(update_year, update_month, update_day)
                        update_day += 1
                        continue

                    if '\n' in shift_info:
                        parts = shift_info.split('\n')
                    elif ';' in shift_info:
                        parts = shift_info.split(';')
                    else:
                        parts = [shift_info]

                    if len(parts) < 4:
                        print(f"Неполные данные для {update_year}-{update_month:02}-{update_day:02}: {parts}")
                        last_processed_date = datetime(update_year, update_month, update_day)
                        update_day += 1
                        continue

                    scheduled_time = parts[1]
                    actual_time = parts[3]
                    print(f"Запланированное время: {scheduled_time}, Фактическое время: {actual_time}")

                    daily_karma_change = 0

                    if scheduled_time and actual_time:
                        try:
                            scheduled_start, scheduled_end = scheduled_time.split('-')
                            actual_start, actual_end = actual_time.split('-')

                            if not check_work_time(scheduled_start, scheduled_end, actual_start, actual_end):
                                daily_karma_change -= 5
                                KarmaHistory.objects.create(employee=employee, karma_change=-5,
                                                            reason=f'Позднее начало/раннее завершение ({update_year}-{update_month:02}-{update_day:02})')
                                print(f"Карма уменьшена на 5 для {full_name} (позднее начало/раннее завершение)")
                        except Exception as e:
                            print(f"Ошибка при разбиении времени: {e}")

                    daily_karma_change += 2
                    KarmaHistory.objects.create(employee=employee, karma_change=2,
                                                reason=f'Ежедневное повышение ({update_year}-{update_month:02}-{update_day:02})')
                    print(f"Карма увеличена на 2 для {full_name} (ежедневное повышение)")

                    employee.karma += daily_karma_change
                    employee.save()
                    print(f"Карма сохранена для {full_name}: {employee.karma}")

                    last_processed_date = datetime(update_year, update_month, update_day)
                    update_day += 1

                employee.last_karma_update = timezone.make_aware(datetime.combine(last_processed_date + timedelta(days=1), time.min))
                employee.save()
                print(f"Дата последнего обновления кармы обновлена для {full_name}: {employee.last_karma_update}")

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
