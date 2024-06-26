import os
import sys
import time
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import django

# Настройка Django
project_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(project_path)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'gamefication.settings')
django.setup()

from main.models import FilePath
from tasks import update_employee_karma

class Watcher:
    def __init__(self, name, path):
        self.name = name
        self.directory_to_watch = os.path.abspath(path)
        if not self.directory_to_watch:
            raise ValueError(f"Directory path for {name} not set.")
        if not os.path.exists(self.directory_to_watch):
            raise ValueError(f"Directory {self.directory_to_watch} does not exist.")
        self.observer = Observer()

    def run(self):
        event_handler = Handler(self.name)
        self.observer.schedule(event_handler, self.directory_to_watch, recursive=True)
        print(f"Starting observer for {self.directory_to_watch}")
        self.observer.start()
        try:
            while True:
                time.sleep(5)
        except KeyboardInterrupt:
            self.observer.stop()
            print("Observer Stopped by Keyboard Interrupt")
        except Exception as e:
            self.observer.stop()
            print(f"Observer Stopped: {e}")

        self.observer.join()

class Handler(FileSystemEventHandler):
    def __init__(self, name):
        self.name = name

    def on_created(self, event):
        print(f"Event type: {event.event_type} - Path: {event.src_path}")
        if event.is_directory:
            return None
        elif event.src_path.endswith(".xlsx"):
            print(f"Received created event - {event.src_path}")
            try:
                update_employee_karma(event.src_path)
            except Exception as e:
                print(f"Error handling created event: {e}")

    def on_modified(self, event):
        print(f"Event type: {event.event_type} - Path: {event.src_path}")
        if event.is_directory:
            return None
        elif event.src_path.endswith(".xlsx"):
            print(f"Received modified event - {event.src_path}")
            try:
                update_employee_karma(event.src_path)
            except Exception as e:
                print(f"Error handling modified event: {e}")

def run_all_watchers():
    file_paths = FilePath.objects.all()
    watchers = []
    for file_path in file_paths:
        print(f"Setting up watcher for: {file_path.path}")
        watcher = Watcher(file_path.name, file_path.path)
        watchers.append(watcher)
        watcher.run()

if __name__ == '__main__':
    print("Running all watchers...")
    run_all_watchers()
