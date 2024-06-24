import os
import subprocess
from datetime import datetime, timedelta
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Конфигурация базы данных
DB_HOST = 'solevoi.mysql.pythonanywhere-services.com'
DB_USER = 'Solevoi'
DB_NAME = '"Solevoi\\$gamificationBASE"'
DB_PASSWORD = 'Oleg.iori1'

# Конфигурация электронной почты
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
