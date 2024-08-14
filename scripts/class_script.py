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

def add_classification_levels(classification_string):
    levels = [level.strip() for level in classification_string.split('->')]
    parent = None
    for level in levels:
        obj, created = Classifications.objects.get_or_create(name=level, parent=parent)
        if created:
            print(f"Добавлена новая классификация: {level}")
        parent = obj
    return parent

def is_classification(value):
    if not isinstance(value, str):
        return False
    if '->' not in value:
        return False
    if any(keyword in value for keyword in ['Укажите', 'Дополнительная информация', 'Опишите', '[']):
        return False
    return True

def add_request(number, date, description, classification, initiator, responsible, support_operator, status,
                is_massive=False):
    if date.tzinfo is None:
        date = pytz.UTC.localize(date)

    if support_operator is None:
        print(f"Skipping request {number} because support operator is None")
        return

    request = Request.objects.create(
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
    print(f"Added request: {request.number}, status: {request.status}, is_massive: {request.is_massive}")
    return request

def is_fio(value):
    if isinstance(value, str):
        fio_pattern = re.compile(r'^[А-ЯЁ][а-яё]+\s[А-ЯЁ][а-яё]+\s[А-ЯЁ][а-яё]+$')
        return bool(fio_pattern.match(value))
    return False

def run_classification_script():
    try:
        file_path_entry = FilePath.objects.get(name="Requests")
        directory_path = file_path_entry.path
    except FilePath.DoesNotExist:
        raise ValueError("Directory path with name 'Requests' not found in the database")

    file_names = ["1 линия. Тип обращений.xlsx", "1 линия. Тип обращений Массовые.xlsx"]
    files = [os.path.join(directory_path, fn) for fn in file_names if os.path.exists(os.path.join(directory_path, fn))]

    for file_path in files:
        is_massive_file = "Массовые" in file_path
        print(f"Processing file: {file_path}, is_massive_file: {is_massive_file}")

        df = pd.read_excel(file_path, sheet_name='TDSheet', skiprows=12)

        if is_massive_file:
            initiator_col = 'Unnamed: 16'
            responsible_col = 'Unnamed: 22'
        else:
            initiator_col = 'Unnamed: 17'
            responsible_col = 'Unnamed: 22'

        classification = None
        description = ''
        support_operator = None

        for index, row in df.iterrows():
            for col_index, col in enumerate(df.columns[:1]):
                value = row[col]
                if pd.notna(value):
                    if is_fio(value):
                        next_values = row[col_index + 1:col_index + 4]
                        if next_values.isnull().all():
                            full_name = value.strip()
                            name_parts = full_name.split()
                            if len(name_parts) == 3:
                                first_name, last_name = name_parts[1], name_parts[0]
                                print(f"Detected FIO: {first_name} {last_name}")
                                try:
                                    support_operator = Employee.objects.get(first_name=first_name, last_name=last_name)
                                except Employee.DoesNotExist:
                                    support_operator = None

                    elif is_classification(value):
                        classification = add_classification_levels(value)

                    elif "Обращение" in str(value):
                        match = re.match(r"Обращение (\d+) от (\d{2}\.\d{2}\.\d{4} \d{1,2}:\d{2}:\d{2})", str(value))
                        if match:
                            number = match.group(1)
                            date_str = match.group(2)
                            date = datetime.strptime(date_str, '%d.%m.%Y %H:%M:%S')

                            description = df.iloc[index + 1, 0] if index + 1 < len(df) else ''

                            print(f"Processing request {number} - date: {date}, description: {description}")

                            initiator = row[initiator_col]
                            responsible = row[responsible_col]
                            status = row['Unnamed: 25']

                            print(
                                f"Request {number} - initiator: {initiator}, responsible: {responsible}, status: {status}, classification: {classification}")

                            if pd.notna(initiator) and pd.notna(responsible) and classification is not None:
                                is_massive = is_massive_file
                                add_request(number, date, description, classification, initiator, responsible,
                                            support_operator, status, is_massive)
                            elif is_massive_file and support_operator is not None:
                                print(
                                    f"Adding massive request with missing data - initiator: {initiator}, responsible: {responsible}, classification: {classification}")
                                add_request(number, date, description, classification, '', '', support_operator, status,
                                            True)
                            else:
                                print(
                                    f"Skipping due to missing data - initiator: {initiator}, responsible: {responsible}, classification: {classification}")

    file_path_entry.last_updated = datetime.now(pytz.UTC)
    file_path_entry.save()

if __name__ == "__main__":
    run_classification_script()
