import os
import re
import sys
import django
import pandas as pd
from datetime import datetime
import pytz

# Django setup
project_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(project_path)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'gamefication.settings')
django.setup()

# Import necessary models
from main.models import Classifications, Request, Employee, FilePath

# Кэш для классификаций
classification_cache = {}


def add_classification_levels(classification_string):
    """Кэшируем классификации для ускорения процесса."""
    levels = [level.strip() for level in classification_string.split('->')]
    parent = None
    cache_key = '->'.join(levels)

    if cache_key in classification_cache:
        return classification_cache[cache_key]

    for level in levels:
        obj = Classifications.objects.filter(name=level, parent=parent).first()
        if not obj:
            obj = Classifications.objects.create(name=level, parent=parent)
        parent = obj

    classification_cache[cache_key] = parent
    return parent


def is_classification(value):
    """Проверка, является ли значение классификацией."""
    if not isinstance(value, str):
        return False
    return '->' in value and not any(
        keyword in value for keyword in ['Укажите', 'Дополнительная информация', 'Опишите', '['])


def add_request(number, date, description, classification, initiator, responsible, support_operator, status,
                is_massive=False):
    if date.tzinfo is None:
        date = pytz.UTC.localize(date)

    if not support_operator:
        return None

    # Проверяем, существует ли запрос
    if Request.objects.filter(number=number).exists():
        return None

    # Создаем новый запрос
    new_request = Request(
        classification=classification,
        responsible=responsible,
        support_operator=support_operator,
        status=status,
        description=description,
        initiator=initiator,
        number=number,
        date=date,
        is_massive=is_massive
    )
    new_request.save()
    return new_request


def is_fio(value):
    """Проверка, является ли значение ФИО."""
    return isinstance(value, str) and bool(re.match(r'^[А-ЯЁ][а-яё]+\s[А-ЯЁ][а-яё]+\s[А-ЯЁ][а-яё]+$', value))


def find_column_positions(df):
    """Функция для динамического поиска нужных столбцов по заголовкам."""
    initiator_col = None
    responsible_col = None
    status_col = None

    for col in df.columns:
        if "Обращение.Инициатор" in str(col):
            initiator_col = col
        elif "Обращение.Ответственный" in str(col):
            responsible_col = col
        elif "Обращение.Состояние" in str(col) or "Статус" in str(col):
            status_col = col

    if not initiator_col or not responsible_col or not status_col:
        raise ValueError("Не удалось найти все необходимые столбцы: инициатор, ответственный, состояние")

    return initiator_col, responsible_col, status_col


def run_classification_script(file_path, file_path_entry=None):
    try:
        if not os.path.exists(file_path):
            raise ValueError(f"Файл {file_path} не найден")

        is_massive_file = "Массовые" in file_path
        df = pd.read_excel(file_path, sheet_name='TDSheet', skiprows=8)
        # Найти динамические позиции для столбцов инициатора, ответственного и статуса
        initiator_col, responsible_col, status_col = find_column_positions(df)
        support_operator = None
        requests_to_create = []
        total_requests = 0  # Счётчик успешных запросов
        for index, row in df.iterrows():
            for col_index, col in enumerate(df.columns[:1]):
                value = row[col]
                if pd.notna(value):
                    if is_fio(value):
                        full_name = value.strip()
                        first_name, last_name = full_name.split()[1], full_name.split()[0]
                        support_operator = Employee.objects.filter(first_name=first_name, last_name=last_name).first()
                    elif is_classification(value):
                        classification = add_classification_levels(value)
                    elif "Обращение" in str(value):
                        match = re.match(r"Обращение (\d+) от (\d{2}\.\d{2}\.\d{4} \d{1,2}:\d{2}:\d{2})", str(value))
                        if match:
                            number = match.group(1)
                            date_str = match.group(2)
                            date = datetime.strptime(date_str, '%d.%m.%Y %H:%M:%S')

                            description = df.iloc[index + 1, 0] if index + 1 < len(df) else ''
                            initiator = row[initiator_col]
                            responsible = row[responsible_col]
                            status = row[status_col]

                            if classification and pd.notna(initiator) and pd.notna(responsible) and support_operator:
                                new_request = add_request(number, date, description, classification, initiator,
                                                          responsible, support_operator, status, is_massive_file)
                                if new_request:
                                    requests_to_create.append(new_request)
                                    total_requests += 1

        # Массовое создание запросов
        Request.objects.bulk_create(requests_to_create)

        print(f"Successfully created {total_requests} requests")

        if file_path_entry:
            file_path_entry.last_updated = datetime.now(pytz.UTC)
            file_path_entry.save()

    except Exception as e:
        print(f"Error processing file {file_path}: {e}")


if __name__ == "__main__":
    run_classification_script()
