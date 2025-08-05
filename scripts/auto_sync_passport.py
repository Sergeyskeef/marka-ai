import logging
import os
import time
from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from scripts.update_passport import PassportUpdater

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename='passport_auto_sync.log'
)
logger = logging.getLogger(__name__)

class ChangeReport:
    def __init__(self):
        self.changes: dict[str, list[str]] = {
            'added_files': [],
            'removed_files': [],
            'modified_files': [],
            'added_dirs': [],
            'removed_dirs': []
        }
        self.timestamp = time.time()
        self.formatted_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(self.timestamp))

    def to_dict(self) -> dict:
        return {
            'changes': self.changes,
            'timestamp': self.timestamp,
            'formatted_time': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(self.timestamp))
        }

    def to_markdown(self) -> str:
        """Форматирует отчет в markdown"""
        report = f"# Отчет об изменениях ({self.formatted_time})\n\n"

        if any(self.changes.values()):
            for category, items in self.changes.items():
                if items:
                    report += f"## {self._format_category(category)}\n"
                    for item in items:
                        report += f"- {item}\n"
                    report += "\n"
        else:
            report += "Изменений не обнаружено\n"

        return report

    def _format_category(self, category: str) -> str:
        """Форматирует название категории для отображения"""
        categories = {
            'added_files': 'Добавленные файлы',
            'removed_files': 'Удаленные файлы',
            'modified_files': 'Измененные файлы',
            'added_dirs': 'Добавленные директории',
            'removed_dirs': 'Удаленные директории'
        }
        return categories.get(category, category)

class PassportSyncHandler(FileSystemEventHandler):
    def __init__(self, updater, sync_interval=60):
        self.updater = updater
        self.sync_interval = sync_interval
        self.last_sync = time.time()
        self.pending_changes = ChangeReport()
        self.ignored_patterns = [
            '*.pyc',
            '*.pyo',
            '*.pyd',
            '.git',
            '__pycache__',
            '*.log',
            '*.json',
            '*.md',
            '*.txt',
            '*.csv',
            '*.db',
            '*.sqlite',
            '*.sqlite3',
            '*.bak',
            '*.tmp',
            '*.temp',
            '*.swp',
            '*.swo',
            '*.swn',
            '*.sublime-workspace',
            '*.sublime-project',
            '.DS_Store',
            'Thumbs.db'
        ]

    def should_ignore(self, path):
        """Проверяет, нужно ли игнорировать файл"""
        path_str = str(path)
        path_obj = Path(path)
        
        # Проверяем точные совпадения паттернов
        for pattern in self.ignored_patterns:
            if pattern == '__pycache__':
                # Для __pycache__ проверяем, содержит ли путь эту директорию
                if '__pycache__' in path_str:
                    return True
            elif path_obj.match(pattern):
                return True
            elif pattern.startswith('*') and path_str.endswith(pattern[1:]):
                return True
            elif pattern in path_str:
                return True
        
        return False

    def on_any_event(self, event):
        """Обрабатывает любое событие файловой системы"""
        if event.is_directory:
            return

        if self.should_ignore(event.src_path):
            return

        current_time = time.time()
        if current_time - self.last_sync < self.sync_interval:
            return

        # Добавляем изменение в отчет
        if event.event_type == 'created':
            self.pending_changes.changes['added_files'].append(event.src_path)
        elif event.event_type == 'deleted':
            self.pending_changes.changes['removed_files'].append(event.src_path)
        elif event.event_type == 'modified':
            self.pending_changes.changes['modified_files'].append(event.src_path)

        logger.info(f"Обнаружены изменения: {event.src_path}")
        self.last_sync = current_time

    def get_pending_changes(self) -> ChangeReport:
        """Возвращает отчет о накопленных изменениях"""
        return self.pending_changes

    def clear_pending_changes(self):
        """Очищает накопленные изменения"""
        self.pending_changes = ChangeReport()

    def apply_changes(self) -> bool:
        """Применяет накопленные изменения"""
        if not any(self.pending_changes.changes.values()):
            logger.info("Нет изменений для применения")
            return True

        try:
            if self.updater.update_passport():
                logger.info("Паспорт успешно обновлен")
                self.clear_pending_changes()
                return True
            else:
                logger.error("Не удалось обновить паспорт")
                return False
        except Exception as e:
            logger.error(f"Ошибка при обновлении паспорта: {e}")
            return False

def main():
    project_root = os.getenv('PROJECT_ROOT', '/home/sergey/marka/langchain_api')
    sync_interval = int(os.getenv('PASSPORT_SYNC_INTERVAL', '60'))

    updater = PassportUpdater(project_root)
    handler = PassportSyncHandler(updater, sync_interval)

    observer = Observer()
    observer.schedule(handler, project_root, recursive=True)
    observer.start()

    logger.info(f"Запущено автоматическое сканирование изменений в {project_root}")
    logger.info(f"Интервал синхронизации: {sync_interval} секунд")

    try:
        while True:
            time.sleep(1)

            # Проверяем наличие изменений
            changes = handler.get_pending_changes()
            if any(changes.changes.values()):
                # Выводим отчет
                print("\n" + changes.to_markdown())

                # Запрашиваем подтверждение
                response = input("\nПрименить изменения? (y/n): ").lower()
                if response == 'y':
                    if handler.apply_changes():
                        print("Изменения успешно применены")
                    else:
                        print("Ошибка при применении изменений")
                else:
                    print("Изменения отменены")
                    handler.clear_pending_changes()

    except KeyboardInterrupt:
        observer.stop()
        logger.info("Сканирование остановлено")

    observer.join()

if __name__ == '__main__':
    main()
    logging.shutdown()
