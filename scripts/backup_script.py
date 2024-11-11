import os
import sys
import django
from datetime import datetime, timedelta
import subprocess

# Настройка Django
project_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(project_path)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'gamefication.settings')
django.setup()

# Импорт необходимых модулей и функций
from tasks import run_update_karma
from main.models import FilePath

# Конфигурация базы данных для бэкапа
DB_HOST = 'shaman.mysql.pythonanywhere-services.com'
DB_USER = 'Shaman'
DB_NAME = '"Shaman\\$default"'
DB_PASSWORD = 'Oleg.iori1'

# Получение пути для резервных копий
backup_path_obj = FilePath.objects.get(name='db_backups')
backup_dir = backup_path_obj.path

# Получение текущей даты для имени файла
current_date = datetime.now().strftime('%Y-%m-%d')
backup_file = os.path.join(backup_dir, f'backup_{current_date}.sql')

# Команда для выполнения дампа базы данных (только INSERT)
dump_command = (
    f'mysqldump --single-transaction --no-create-info --skip-add-drop-table '
    f'-h {DB_HOST} -u {DB_USER} -p{DB_PASSWORD} {DB_NAME} > {backup_file}'
)

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

def main():
    backup_file, error = perform_backup()
    if backup_file:
        print("Резервное копирование выполнено успешно.")
    else:
        print("Ошибка при выполнении резервного копирования.")

if __name__ == "__main__":
    main()
