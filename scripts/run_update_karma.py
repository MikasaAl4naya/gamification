import os
import sys
import django

project_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_path)
print("Project path:", project_path)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'gamefication.settings')
print("DJANGO_SETTINGS_MODULE:", os.environ.get('DJANGO_SETTINGS_MODULE'))
django.setup()

from tasks import run_update

run_update('work_schedule')
