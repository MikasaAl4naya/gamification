import os
import sys
import subprocess
from datetime import datetime, timedelta
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import pandas as pd
import django
from django.utils import timezone

# Add the project path into the sys.path
project_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(project_path)

# Set the Django settings module environment variable
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'gamefication.settings')

# Initialize Django
django.setup()

from main.models import Employee, FilePath, KarmaHistory

# Конфигурация базы данных для бэкапа
DB_HOST = 'solevoi.mysql.pythonanywhere-services.com'
DB_USER = 'Solevoi'
DB_NAME = '"Solevoi\\$gamificationBASE"'
DB_PASSWORD = 'Oleg.iori1'

# Конфигурация электронной почты для бэкапа
EMAIL_USER = 'oleg.pytin@gmail.com'
EMAIL_PASSWORD = 'cemi zewp jzeu phun'
EMAIL_RECIPIENT = 'oleg.pytin@gmail.com'
SMTP_SERVER = 'smtp.gmail.com'
SMTP_PORT = 587

# Директория для бэкапов
backup_dir = '/home/Solevoi/db_backups'

# Получение текущей даты для имени файла
current_date = datetime.now().strftime('%Y-%m-%d')
backup_file = os.path.join(backup_dir, f'backup_{current_date}.sql')

# Команда для выполнения дампа базы данных
dump_command = f'mysqldump --single-transaction -h {DB_HOST} -u {DB_USER} -p{DB_PASSWORD} {DB_NAME} > {backup_file}'

# Создание папки для бэкапов, если она не существует
os.makedirs(backup_dir, exist_ok=True)

def send_email(subject, body):
    msg = MIMEMultipart()
    msg['From'] = EMAIL_USER
    msg['To'] = EMAIL_RECIPIENT
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(EMAIL_USER, EMAIL_PASSWORD)
            server.sendmail(EMAIL_USER, EMAIL_RECIPIENT, msg.as_string())
        print("Email sent successfully")
    except Exception as e:
        print(f"Failed to send email: {e}")

# Выполнение команды дампа и логирование результата
try:
    subprocess.check_call(dump_command, shell=True)
    print(f"Backup completed: {backup_file}")
    send_email("Backup Successful", f"Backup completed successfully: {backup_file}")
except subprocess.CalledProcessError as e:
    print(f"Error during backup: {e}")
    send_email("Backup Failed", f"Backup failed for {DB_NAME}. Error: {e}")
    # Логирование ошибки
    with open(os.path.join(backup_dir, 'backup_error.log'), 'a') as log_file:
        log_file.write(f"{datetime.now()}: Backup failed for {DB_NAME}. Error: {e}\n")

# Удаление старых бэкапов (старше 7 дней)
for filename in os.listdir(backup_dir):
    file_path = os.path.join(backup_dir, filename)
    if os.path.isfile(file_path):
        file_creation_time = datetime.fromtimestamp(os.path.getctime(file_path))
        if file_creation_time < datetime.now() - timedelta(days=7):
            os.remove(file_path)
            print(f"Deleted old backup: {file_path}")

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
                last_karma_update = employee.last_karma_update.day if employee.last_karma_update else 0

                for day in range(last_karma_update + 1, current_date + 1):
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
                                KarmaHistory.objects.create(employee=employee, karma_change=-5, reason='Late start/early end')
                                print(f"Karma decreased by 5 for {full_name} (late start/early end)")

                        employee.karma += 2
                        KarmaHistory.objects.create(employee=employee, karma_change=2, reason='Daily increment')
                        print(f"Karma increased by 2 for {full_name} (daily increment)")

                        employee.save()

                employee.last_karma_update = timezone.now()
                employee.save()
        except Employee.DoesNotExist:
            print(f"Employee with name {full_name} does not exist.")
        except Exception as e:
            print(f"Error processing {full_name}: {e}")

def run_update(name):
    file_path = get_file_path(name)
    if file_path:
        update_employee_karma(file_path)
    else:
        print(f"File path for {name} not set")

# Run karma update after backup
run_update("work_schedule")
