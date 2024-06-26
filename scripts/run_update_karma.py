import django
import os
import sys

project_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(project_path)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'gamefication.settings')
django.setup()

from tasks import update_employee_karma

file_path = '/home/Solevoi/work_schedule/Табель тест.xlsx'
update_employee_karma(file_path)
