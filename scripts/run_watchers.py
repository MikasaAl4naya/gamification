# scripts/run_watchers.py
import os
import sys
import time

# Добавляем корневую директорию проекта в sys.path
project_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(project_path)

import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'gamefication.settings')
django.setup()

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from main.models import FilePath
from tasks import update_employee_karma, get_file_path

class Watcher:
    def __init__(self, name, path):
        self.name = name
        self.directory_to_watch = path
        if not self.directory_to_watch:
            raise ValueError(f"Directory path for {name} not set.")
        self.observer = Observer()

    def run(self):
        event_handler = Handler(self.name)
        self.observer.schedule(event_handler, self.directory_to_watch, recursive=True)
        self.observer.start()
        try:
            while True:
                time.sleep(5)
        except Exception as e:
            self.observer.stop()
            print(f"Observer Stopped: {e}")

        self.observer.join()

class Handler(FileSystemEventHandler):
    def __init__(self, name):
        self.name = name

    def on_created(self, event):
        if event.is_directory:
            return None
        elif event.src_path.endswith(".xlsx"):  # Убедитесь, что это Excel файл
            print(f"Received created event - {event.src_path}")
            update_employee_karma(event.src_path)

def run_all_watchers():
    file_paths = FilePath.objects.all()
    watchers = []
    for file_path in file_paths:
        watcher = Watcher(file_path.name, file_path.path)
        watchers.append(watcher)
        watcher.run()

if __name__ == '__main__':
    run_all_watchers()
