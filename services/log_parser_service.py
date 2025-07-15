"""
LogParserService - сервис для парсинга и анализа логов
"""

import logging
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class LogParserService:
    """Сервис для парсинга логов"""

    def __init__(self, log_dir: str = "logs"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(exist_ok=True)
        logger.info("✅ LogParserService инициализирован")

    def get_log_files(self) -> list[Path]:
        """Возвращает список лог-файлов"""
        if not self.log_dir.exists():
            return []

        log_files = []
        for file in self.log_dir.iterdir():
            if file.is_file() and file.suffix in ['.log', '.txt']:
                log_files.append(file)

        return sorted(log_files, key=lambda x: x.stat().st_mtime, reverse=True)

    def get_recent_changes(self, hours: int = 24) -> list[dict[str, Any]]:
        """Получает недавние изменения из логов"""
        changes = []
        cutoff_time = datetime.now() - timedelta(hours=hours)

        for log_file in self.get_log_files():
            try:
                with open(log_file, encoding='utf-8', errors='ignore') as f:
                    for line in f:
                        # Парсим строку лога
                        parsed = self._parse_log_line(line)
                        if parsed and parsed['timestamp'] >= cutoff_time:
                            changes.append(parsed)
            except Exception as e:
                logger.warning(f"⚠️ Ошибка чтения лог-файла {log_file}: {e}")

        # Сортируем по времени (новые сначала)
        changes.sort(key=lambda x: x['timestamp'], reverse=True)
        return changes[:100]  # Ограничиваем количество

    def get_errors(self, hours: int = 24) -> list[dict[str, Any]]:
        """Получает ошибки из логов"""
        all_changes = self.get_recent_changes(hours)
        errors = [change for change in all_changes if change['level'] == 'ERROR']
        return errors

    def get_changes_summary(self, hours: int = 24) -> dict[str, Any]:
        """Получает сводку изменений"""
        changes = self.get_recent_changes(hours)
        errors = self.get_errors(hours)

        # Группируем по уровню
        by_level = {}
        for change in changes:
            level = change['level']
            by_level[level] = by_level.get(level, 0) + 1

        # Группируем по файлу
        by_file = {}
        for change in changes:
            file = change.get('file', 'unknown')
            by_file[file] = by_file.get(file, 0) + 1

        return {
            "total_entries": len(changes),
            "errors": len(errors),
            "by_level": by_level,
            "by_file": by_file,
            "time_range": f"Последние {hours} часов"
        }

    def _parse_log_line(self, line: str) -> dict[str, Any] | None:
        """Парсит строку лога"""
        try:
            # Простой парсер для стандартного формата логов
            # Пример: 2025-07-14 13:30:00,123 - INFO - message
            pattern = r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),(\d{3}) - (\w+) - (.+)'
            match = re.match(pattern, line.strip())

            if match:
                timestamp_str = match.group(1)
                level = match.group(3)
                message = match.group(4)

                # Парсим timestamp
                timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')

                return {
                    'timestamp': timestamp,
                    'level': level,
                    'message': message,
                    'file': 'app.log'  # По умолчанию
                }

            return None

        except Exception as e:
            logger.debug(f"Ошибка парсинга строки лога: {e}")
            return None

    def add_log_entry(self, level: str, message: str, file: str = "app.log"):
        """Добавляет запись в лог"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S,%f')[:-3]
        log_entry = f"{timestamp} - {level.upper()} - {message}\n"

        log_file = self.log_dir / file
        try:
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(log_entry)
        except Exception as e:
            logger.error(f"❌ Ошибка записи в лог: {e}")

    def clear_old_logs(self, days: int = 7):
        """Очищает старые логи"""
        cutoff_time = datetime.now() - timedelta(days=days)
        cleared_count = 0

        for log_file in self.get_log_files():
            try:
                if datetime.fromtimestamp(log_file.stat().st_mtime) < cutoff_time:
                    log_file.unlink()
                    cleared_count += 1
            except Exception as e:
                logger.warning(f"⚠️ Ошибка удаления старого лога {log_file}: {e}")

        logger.info(f"🧹 Очищено {cleared_count} старых лог-файлов")
        return cleared_count
