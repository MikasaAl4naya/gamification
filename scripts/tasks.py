import pandas as pd
from django.core.exceptions import ValidationError
from django.utils import timezone
from main.models import Employee, LastProcessedDate, FilePath
from datetime import datetime

def get_file_path(name):
    try:
        file_path_obj = FilePath.objects.get(name=name)
        return file_path_obj.path
    except FilePath.DoesNotExist:
        return None

def process_work_schedule(file_path):
    df = pd.read_excel(file_path, skiprows=3)
    df = df.rename(columns={'Unnamed: 1': 'ФИО', 'Unnamed: 2': 'Город'})
    print(f"DataFrame columns: {df.columns}")
    print(df.head())
    return df

def check_work_time(scheduled_start, scheduled_end, actual_start, actual_end):
    scheduled_start = pd.to_datetime(scheduled_start)
    scheduled_end = pd.to_datetime(scheduled_end)
    actual_start = pd.to_datetime(actual_start)
    actual_end = pd.to_datetime(actual_end)

    if actual_start > scheduled_start or actual_end < scheduled_end:
        return False
    return True

def update_employee_karma(file_path):
    df = process_work_schedule(file_path)
    last_processed_date_obj, created = LastProcessedDate.objects.get_or_create(id=1)
    last_processed_date = last_processed_date_obj.last_date.day if last_processed_date_obj.last_date else 0

    current_date = datetime.now().day
    for index, row in df.iterrows():
        try:
            full_name = row['ФИО']
            name_parts = full_name.split()
            if len(name_parts) < 3:
                print(f"Invalid name format for {full_name}")
                continue
            last_name, first_name, middle_name = name_parts[0], name_parts[1], name_parts[2]
            print(f"Processing {full_name} ({first_name} {last_name})")

            employees = Employee.objects.filter(first_name=first_name, last_name=last_name)

            if not employees.exists():
                print(f"Employee with name {full_name} does not exist.")
                continue

            for employee in employees:
                for day in range(last_processed_date + 1, current_date + 1):
                    shift_info = row.get(f'Unnamed: {day}', '').strip().lower()
                    if any(x in shift_info for x in ['выходной', 'о', 'бс', 'б']):
                        continue

                    if '\n' in shift_info:
                        parts = shift_info.split('\n')
                        scheduled_time = parts[1] if len(parts) > 1 else ''
                        actual_time = parts[3] if len(parts) > 3 else ''

                        if scheduled_time and actual_time:
                            scheduled_start, scheduled_end = scheduled_time.split('-')
                            actual_start, actual_end = actual_time.split('-')

                            if not check_work_time(scheduled_start, scheduled_end, actual_start, actual_end):
                                employee.karma -= 5
                                print(f"Karma decreased by 5 for {full_name} (late start/early end)")

                        employee.karma += 2
                        print(f"Karma increased by 2 for {full_name} (daily increment)")

                        employee.save()
        except Employee.DoesNotExist:
            print(f"Employee with name {full_name} does not exist.")
        except Exception as e:
            print(f"Error processing {full_name}: {e}")

    last_processed_date_obj.last_date = timezone.now()
    last_processed_date_obj.save()
    print(f"Last processed date updated to {last_processed_date_obj.last_date}")

def run_update(name):
    file_path = get_file_path(name)
    if file_path:
        update_employee_karma(file_path)
    else:
        print(f"File path for {name} not set")
