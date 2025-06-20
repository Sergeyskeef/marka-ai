import os
import re
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from pathlib import Path

class LogParserService:
    def __init__(self, logs_dir: str = "logs"):
        self.logs_dir = Path(logs_dir).resolve()
        self.log_patterns = {
            'error': r'ERROR|Exception|Error|error',
            'warning': r'WARNING|Warning|warning',
            'info': r'INFO|Info|info',
            'debug': r'DEBUG|Debug|debug'
        }
        print(f"LogParserService initialized with logs_dir: {self.logs_dir}")
        
    def get_log_files(self) -> List[Path]:
        """Получить список всех лог-файлов в директории"""
        if not self.logs_dir.exists():
            print(f"Directory does not exist: {self.logs_dir}")
            return []
            
        log_files = list(self.logs_dir.glob("*.log"))
        print(f"Found log files: {log_files}")
        return log_files
    
    def parse_log_file(self, log_file: Path) -> List[Dict]:
        """Парсить отдельный лог-файл и возвращать структурированные записи"""
        entries = []
        
        try:
            if not log_file.exists():
                print(f"File does not exist: {log_file}")
                return entries
                
            print(f"Reading file: {log_file}")
            with open(log_file, 'r', encoding='utf-8') as f:
                for line in f:
                    entry = self._parse_log_line(line, log_file.name)
                    if entry:
                        entries.append(entry)
                        
            print(f"Parsed {len(entries)} entries from {log_file}")
        except Exception as e:
            print(f"Error reading file {log_file}: {str(e)}")
            
        return entries
    
    def _parse_log_line(self, line: str, file_name: str) -> Optional[Dict]:
        """Парсить отдельную строку лога"""
        if not line.strip():
            return None
            
        # Базовый парсинг даты и времени
        datetime_pattern = r'(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2}:\d{2})'
        datetime_match = re.search(datetime_pattern, line)
        
        entry = {
            'file': file_name,
            'raw_line': line.strip(),
            'timestamp': None,
            'level': None,
            'message': line.strip()
        }
        
        if datetime_match:
            try:
                date_str = datetime_match.group(1)
                time_str = datetime_match.group(2)
                entry['timestamp'] = f"{date_str} {time_str}"
            except:
                pass
        
        # Определение уровня логирования
        for level, pattern in self.log_patterns.items():
            if re.search(pattern, line):
                entry['level'] = level
                break
                
        return entry
    
    def _parse_datetime(self, timestamp: str) -> Optional[datetime]:
        """Парсить дату и время из строки в разных форматах"""
        formats = [
            '%Y-%m-%d %H:%M:%S',  # 2024-03-30 10:00:00
            '%d/%m/%Y %H:%M:%S',  # 30/03/2024 10:00:00
            '%Y-%m-%d %H:%M',     # 2024-03-30 10:00
            '%d/%m/%Y %H:%M'      # 30/03/2024 10:00
        ]
        
        for fmt in formats:
            try:
                return datetime.strptime(timestamp, fmt)
            except ValueError:
                continue
        return None
    
    def get_recent_changes(self, hours: int = 24) -> List[Dict]:
        """Получить список недавних изменений за указанный период"""
        all_entries = []
        log_files = self.get_log_files()
        
        if not log_files:
            print(f"No log files found in directory: {self.logs_dir}")
            return all_entries
            
        for log_file in log_files:
            entries = self.parse_log_file(log_file)
            all_entries.extend(entries)
            
        # Фильтрация по времени
        if hours and hours > 0:
            try:
                cutoff_time = datetime.now() - timedelta(hours=hours)
                filtered_entries = []
                for entry in all_entries:
                    if entry['timestamp']:
                        entry_time = self._parse_datetime(entry['timestamp'])
                        if entry_time and entry_time >= cutoff_time:
                            filtered_entries.append(entry)
                    else:
                        # Если нет временной метки, включаем запись
                        filtered_entries.append(entry)
                all_entries = filtered_entries
            except Exception as e:
                print(f"Error filtering by time: {e}")
                # В случае ошибки возвращаем все записи
                pass
            
        print(f"Found {len(all_entries)} recent changes")
        return sorted(all_entries, key=lambda x: x['timestamp'] if x['timestamp'] else '', reverse=True)
    
    def get_errors(self, hours: int = 24) -> List[Dict]:
        """Получить список ошибок за указанный период"""
        entries = self.get_recent_changes(hours)
        errors = [entry for entry in entries if entry['level'] == 'error']
        print(f"Found {len(errors)} errors")
        return errors
    
    def get_changes_summary(self, hours: int = 24) -> Dict:
        """Получить сводку изменений за указанный период"""
        entries = self.get_recent_changes(hours)
        
        summary = {
            'total_entries': len(entries),
            'errors': len([e for e in entries if e['level'] == 'error']),
            'warnings': len([e for e in entries if e['level'] == 'warning']),
            'info': len([e for e in entries if e['level'] == 'info']),
            'debug': len([e for e in entries if e['level'] == 'debug']),
            'files_modified': len(set(e['file'] for e in entries))
        }
        
        print(f"Generated summary: {summary}")
        return summary 