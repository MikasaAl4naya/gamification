import os
import sys
import django
from datetime import datetime, timedelta
import subprocess
from email_utlis import send_email

# Настройка Django
project_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(project_path)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'gamefication.settings')
django.setup()

# Импорт необходимых модулей и функций
from tasks import run_update_karma

# Конфигурация базы данных для бэкапа
DB_HOST = 'solevoi.mysql.pythonanywhere-services.com'
DB_USER = 'Solevoi'
DB_NAME = '"Solevoi\\$gamificationBASE"'
DB_PASSWORD = 'Oleg.iori1'

# Получение пути для резервных копий из модели FilePath
from main.models import FilePath

backup_path_obj = FilePath.objects.get(name='db_backups')
backup_dir = backup_path_obj.path

# Получение текущей даты для имени файла
current_date = datetime.now().strftime('%Y-%m-%d')
backup_file = os.path.join(backup_dir, f'backup_{current_date}.sql')

# Команда для выполнения дампа базы данных
dump_command = f'mysqldump --single-transaction -h {DB_HOST} -u {DB_USER} -p{DB_PASSWORD} {DB_NAME} > {backup_file}'

# Создание папки для бэкапов, если она не существует
os.makedirs(backup_dir, exist_ok=True)

def perform_backup():
    try:
        subprocess.check_call(dump_command, shell=True)
        print(f"Резервное копирование завершено: {backup_file}")
        return backup_file, None
    except subprocess.CalledProcessError as e:
        print(f"Ошибка во время резервного копирования: {e}")
        return None, e

def cleanup_old_backups():
    for filename in os.listdir(backup_dir):
        file_path = os.path.join(backup_dir, filename)
        if os.path.isfile(file_path):
            file_creation_time = datetime.fromtimestamp(os.path.getctime(file_path))
            if file_creation_time < datetime.now() - timedelta(days=7):
                os.remove(file_path)
                print(f"Удален старый бэкап: {file_path}")

def main():
    # backup_file, error = perform_backup()
    # if backup_file:
    #     send_email("Резервное копирование успешно", f"Резервное копирование завершено успешно: {backup_file}")
    # else:
    #     send_email("Резервное копирование не удалось", f"Резервное копирование не удалось. Ошибка: {error}")

    cleanup_old_backups()
    run_update_karma("work_schedule")

if __name__ == "__main__":
    main()
