import os
import sys
import django
import pandas as pd

# Настройка Django
project_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(project_path)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'gamefication.settings')
django.setup()
from main.models import Classifications

# Функция для создания или получения классификации
def get_or_create_classification(name, parent=None):
    classification, created = Classifications.objects.get_or_create(name=name, parent=parent)
    return classification

# Функция для парсинга и сохранения иерархии классификаций
def parse_and_save_classifications(classification_hierarchy):
    for hierarchy in classification_hierarchy:
        parent = None
        for level in hierarchy:
            parent = get_or_create_classification(level.strip(), parent)

# Основная функция
def main():
    file_path = 'C:/Users/olegp/PycharmProjects/DjangoProjects/gamefication/work_schedule/тест статистика 1 день.xls'

    # Загрузка данных из файла
    data_xls = pd.read_excel(file_path, skiprows=4).dropna(how='all')

    # Извлечение уникальных классификаций
    classifications = data_xls['Operator_Service'].dropna().unique()

    # Создание иерархии классификаций
    classification_hierarchy = [classification.split('->') for classification in classifications]

    # Сохранение классификаций в базу данных
    parse_and_save_classifications(classification_hierarchy)
    print("Successfully parsed and saved classifications")

# Запуск основного скрипта
if __name__ == '__main__':
    main()
