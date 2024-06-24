# main/run_update_karma.py
import os
import sys
import django

# Добавляем корневую директорию проекта в sys.path
project_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_path)
print("Project path:", project_path)

# Настройка Django окружения
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'gamefication.settings')
print("DJANGO_SETTINGS_MODULE:", os.environ.get('DJANGO_SETTINGS_MODULE'))
django.setup()

# Импортируем функцию обновления после настройки Django
from scripts.tasks import run_update

# Запуск обновления
run_update('work_schedule')