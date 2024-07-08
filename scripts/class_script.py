import os
import re
import sys
import django
import pandas as pd

# Настройка Django
project_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(project_path)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'gamefication.settings')
django.setup()

# Импорт необходимых моделей
from main.models import Classifications

# Путь к файлу Excel
file_path = "C:/Users/olegp/Downloads/тест-статистика-1-день.xlsx"

# Загрузка данных из Excel файла
df = pd.read_excel(file_path, sheet_name='TDSheet', skiprows=12)

# Проверка структуры DataFrame
print(df.columns)

# Функция для добавления уровней классификации в БД
def add_classification_levels(classification_string):
    levels = [level.strip() for level in classification_string.split('->')]
    parent = None
    for level in levels:
        obj, created = Classifications.objects.get_or_create(name=level, parent=parent)
        parent = obj

# Функция для проверки, является ли строка классификацией
def is_classification(value):
    if not isinstance(value, str):
        return False
    if '->' not in value:
        return False
    # Исключение строк, вероятно являющихся описаниями обращений
    if len(value) > 100:  # Описание обычно длиннее
        return False
    if any(keyword in value for keyword in ['Укажите', 'Дополнительная информация', 'Опишите', '[']):
        return False
    # Учитываем количество слов
    if len(re.findall(r'\w+', value)) > 10:  # Примерное количество слов
        return False
    return True

# Итерация по строкам DataFrame
for index, row in df.iterrows():
    for col in df.columns:
        value = row[col]
        if is_classification(value):
            add_classification_levels(value)

print("Классификации успешно добавлены в базу данных.")

