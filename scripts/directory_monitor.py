import os
import sys
import time
import django
import pandas as pd
from datetime import datetime
from django.utils import timezone
from django.core.exceptions import ValidationError

# Настройка путей и Django
project_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(project_path)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'gamefication.settings')
django.setup()

from main.models import Employee, LastProcessedDate, FilePath
from tasks import update_employee_karma, process_work_schedule

def get_existing_files(directory):
    return {f for f in os.listdir(directory) if os.path.isfile(os.path.join(directory, f)) and f.endswith('.xlsx')}

def monitor_directory(directory):
    processed_files = get_existing_files(directory)
    print(f"Initially processed files: {processed_files}")

    while True:
        current_files = get_existing_files(directory)
        new_files = current_files - processed_files

        for new_file in new_files:
            file_path = os.path.join(directory, new_file)
            print(f"New file detected: {file_path}")
            try:
                update_employee_karma(file_path)
                processed_files.add(new_file)
            except Exception as e:
                print(f"Error processing file {file_path}: {e}")

        time.sleep(10)  # Задержка перед следующей проверкой

def main():
    file_paths = FilePath.objects.all()
    if not file_paths:
        print("No file paths found in the database.")
        return

    for file_path in file_paths:
        directory = file_path.path
        if os.path.exists(directory):
            print(f"Monitoring directory: {directory}")
            monitor_directory(directory)
        else:
            print(f"Directory does not exist: {directory}")

if __name__ == '__main__':
    main()
