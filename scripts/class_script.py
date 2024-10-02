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

# Кэш для классификаций и сотрудников
classification_cache = {}
employee_cache = {}


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
        keyword in value for keyword in ['Укажите', 'Дополнительная информация', 'Опишите', '[']
    )


def add_request_bulk(requests):
    """
    Массовое создание запросов с использованием bulk_create.
    """
    try:
        Request.objects.bulk_create(requests, ignore_conflicts=True)
        print(f"Successfully created {len(requests)} requests")
    except Exception as e:
        print(f"Error during bulk_create: {e}")


def is_fio(value):
    """Проверка, является ли значение ФИО."""
    if not isinstance(value, str):
        return False
    # Регулярное выражение для кириллицы
    pattern_cyrillic = r'^[А-ЯЁ][а-яё]+\s[А-ЯЁ][а-яё]+\s[А-ЯЁ][а-яё]+$'
    # Регулярное выражение для латиницы (транскрибированные имена)
    pattern_latin = r'^[A-Za-z]+\s[A-Za-z]+\s[A-Za-z]+$'
    return bool(re.match(pattern_cyrillic, value)) or bool(re.match(pattern_latin, value))


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


def preload_employee_cache():
    """
    Предзагрузка всех сотрудников в кэш для уменьшения количества запросов к базе данных.
    Добавляем поддержку транскрибированных имён, если они существуют.
    """
    global employee_cache
    employees = Employee.objects.all().values('id', 'first_name', 'last_name',
                                              'username')  # Возможно, username содержит транскрибированные имена
    for emp in employees:
        # Добавляем оригинальные имена
        key_original = (emp['first_name'].strip().lower(), emp['last_name'].strip().lower())
        employee_cache[key_original] = emp['id']

        # Добавляем транскрибированные имена, если они отличаются
        # Предполагаем, что транскрибированные имена могут быть в 'username' или другом поле
        # Здесь нужно уточнить, где хранятся транскрибированные имена
        # Например, если транскрибированные имена хранятся в 'username':
        if emp['username']:
            # Разделяем 'username' на части
            parts = emp['username'].strip().split()
            if len(parts) >= 2:
                first_name_translit = parts[1].lower()
                last_name_translit = parts[0].lower()
                key_translit = (first_name_translit, last_name_translit)
                employee_cache[key_translit] = emp['id']

    print(f"Preloaded {len(employee_cache)} employees into cache.")


def run_classification_script(file_path, file_path_entry=None):
    try:
        if not os.path.exists(file_path):
            raise ValueError(f"Файл {file_path} не найден")

        is_massive_file = "Массовые" in file_path
        df = pd.read_excel(file_path, sheet_name='TDSheet', skiprows=8)
        # Найти динамические позиции для столбцов инициатора, ответственного и статуса
        initiator_col, responsible_col, status_col = find_column_positions(df)
        classification = None  # Инициализируем переменную классификации
        requests_to_create = []
        total_requests = 0  # Счётчик успешных запросов

        # Предзагрузка кэша сотрудников
        preload_employee_cache()

        # Для логирования не найденных операторов
        not_found_operators = set()

        for index, row in df.iterrows():
            value = row[df.columns[0]]
            if pd.notna(value):
                if is_fio(value):
                    full_name = value.strip()
                    parts = full_name.split()
                    if len(parts) >= 2:
                        first_name, last_name = parts[1], parts[0]
                        key = (first_name.strip().lower(), last_name.strip().lower())
                        support_operator_id = employee_cache.get(key)
                        if not support_operator_id:
                            not_found_operators.add(full_name)
                            support_operator = None
                        else:
                            support_operator = support_operator_id
                elif is_classification(value):
                    classification = add_classification_levels(value)
                elif "Обращение" in str(value):
                    match = re.match(r"Обращение (\d+) от (\d{2}\.\d{2}\.\d{4} \d{1,2}:\d{2}:\d{2})", str(value))
                    if match:
                        number = match.group(1)
                        date_str = match.group(2)
                        date = datetime.strptime(date_str, '%d.%m.%Y %H:%M:%S')
                        date = pytz.UTC.localize(date)  # Локализация времени

                        description = df.iloc[index + 1, 0] if index + 1 < len(df) else ''
                        initiator = row[initiator_col]
                        responsible = row[responsible_col]
                        status = row[status_col]

                        # Проверяем, что все необходимые поля присутствуют
                        if classification and pd.notna(initiator) and pd.notna(responsible) and support_operator:
                            # Создаём объект Request без сохранения в базу
                            request = Request(
                                number=number,
                                classification=classification,
                                responsible=responsible,
                                support_operator_id=support_operator,
                                status=status,
                                description=description,
                                initiator=initiator,
                                date=date,
                                is_massive=is_massive_file
                            )
                            requests_to_create.append(request)
                            total_requests += 1
                        else:
                            print(
                                f"Не все данные присутствуют для создания обращения номер {number}. Обращение не создано.")

        # Массовое создание обращений
        if requests_to_create:
            add_request_bulk(requests_to_create)

        print(f"Total requests processed: {total_requests}")

        if not_found_operators:
            print("Следующие операторы не найдены и обращения для них не созданы:")
            for operator in not_found_operators:
                print(f"- {operator}")

        if file_path_entry:
            file_path_entry.last_updated = datetime.now(pytz.UTC)
            file_path_entry.save()

    except Exception as e:
        import traceback
        print(f"Error processing file {file_path}: {e}")
        traceback.print_exc()


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python script.py <file_path>")
    else:
        run_classification_script(sys.argv[1])
