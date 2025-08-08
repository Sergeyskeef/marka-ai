"""
Инструменты для работы с файлами и проектами
"""

import os
import json
import logging
from pathlib import Path
from typing import List, Optional, Dict, Any
import mimetypes
import fnmatch

from .tools import create_openai_tool
from ..config import settings

logger = logging.getLogger(__name__)

# Безопасные директории для работы
SAFE_DIRECTORIES = [
    "/workspace",  # Основная рабочая директория
    "/app",        # Директория приложения в контейнере
    "/sandbox",    # Песочница
]

# Запрещенные паттерны файлов
FORBIDDEN_PATTERNS = [
    "*.pyc",
    "__pycache__/*",
    ".git/*",
    ".env*",
    "*.key",
    "*.pem",
    "*.secret"
]


def is_safe_path(path: str) -> bool:
    """Проверка безопасности пути"""
    try:
        # Преобразуем в абсолютный путь
        abs_path = os.path.abspath(path)
        
        # Проверяем, что путь в безопасных директориях
        is_in_safe_dir = any(
            abs_path.startswith(safe_dir) 
            for safe_dir in SAFE_DIRECTORIES
        )
        
        if not is_in_safe_dir:
            return False
        
        # Проверяем запрещенные паттерны
        for pattern in FORBIDDEN_PATTERNS:
            if fnmatch.fnmatch(abs_path, pattern):
                return False
        
        return True
    except Exception:
        return False


@create_openai_tool
async def read_file(
    file_path: str,
    start_line: Optional[int] = None,
    end_line: Optional[int] = None,
    encoding: str = "utf-8"
) -> str:
    """
    Читает содержимое файла.
    
    Args:
        file_path: Путь к файлу (абсолютный или относительный к /workspace)
        start_line: Начальная строка (1-based, включительно)
        end_line: Конечная строка (1-based, включительно)
        encoding: Кодировка файла
    
    Returns:
        Содержимое файла или его части
    """
    try:
        # Проверка безопасности
        if not is_safe_path(file_path):
            return f"❌ Ошибка: небезопасный путь '{file_path}'"
        
        # Если путь относительный, делаем относительно /workspace
        if not os.path.isabs(file_path):
            file_path = os.path.join("/workspace", file_path)
        
        if not os.path.exists(file_path):
            return f"❌ Ошибка: файл '{file_path}' не найден"
        
        if not os.path.isfile(file_path):
            return f"❌ Ошибка: '{file_path}' не является файлом"
        
        # Читаем файл
        with open(file_path, 'r', encoding=encoding) as f:
            lines = f.readlines()
        
        # Если указаны строки
        if start_line is not None or end_line is not None:
            start_idx = (start_line - 1) if start_line else 0
            end_idx = end_line if end_line else len(lines)
            
            # Проверка границ
            if start_idx < 0:
                start_idx = 0
            if end_idx > len(lines):
                end_idx = len(lines)
            
            lines = lines[start_idx:end_idx]
            
            # Добавляем номера строк
            result_lines = []
            for i, line in enumerate(lines):
                line_num = start_idx + i + 1
                result_lines.append(f"{line_num:6d}| {line.rstrip()}")
            
            return "\n".join(result_lines)
        
        # Возвращаем весь файл
        return "".join(lines)
        
    except UnicodeDecodeError:
        return f"❌ Ошибка: не удалось прочитать файл в кодировке {encoding}"
    except Exception as e:
        logger.error(f"Ошибка чтения файла {file_path}: {e}")
        return f"❌ Ошибка чтения файла: {str(e)}"


@create_openai_tool
async def write_file(
    file_path: str,
    content: str,
    create_dirs: bool = True,
    encoding: str = "utf-8"
) -> str:
    """
    Создает или перезаписывает файл.
    
    Args:
        file_path: Путь к файлу
        content: Содержимое для записи
        create_dirs: Создавать директории если не существуют
        encoding: Кодировка файла
    
    Returns:
        Сообщение о результате операции
    """
    try:
        # Проверка безопасности
        if not is_safe_path(file_path):
            return f"❌ Ошибка: небезопасный путь '{file_path}'"
        
        # Если путь относительный, делаем относительно /workspace
        if not os.path.isabs(file_path):
            file_path = os.path.join("/workspace", file_path)
        
        # Создаем директории если нужно
        if create_dirs:
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
        
        # Записываем файл
        with open(file_path, 'w', encoding=encoding) as f:
            f.write(content)
        
        # Получаем информацию о файле
        file_size = os.path.getsize(file_path)
        lines_count = content.count('\n') + 1
        
        return (f"✅ Файл '{file_path}' успешно создан/обновлен\n"
                f"   Размер: {file_size} байт\n"
                f"   Строк: {lines_count}")
        
    except Exception as e:
        logger.error(f"Ошибка записи файла {file_path}: {e}")
        return f"❌ Ошибка записи файла: {str(e)}"


@create_openai_tool
async def append_to_file(
    file_path: str,
    content: str,
    add_newline: bool = True,
    encoding: str = "utf-8"
) -> str:
    """
    Добавляет содержимое в конец файла.
    
    Args:
        file_path: Путь к файлу
        content: Содержимое для добавления
        add_newline: Добавить перевод строки перед содержимым
        encoding: Кодировка файла
    
    Returns:
        Сообщение о результате операции
    """
    try:
        # Проверка безопасности
        if not is_safe_path(file_path):
            return f"❌ Ошибка: небезопасный путь '{file_path}'"
        
        # Если путь относительный, делаем относительно /workspace
        if not os.path.isabs(file_path):
            file_path = os.path.join("/workspace", file_path)
        
        # Проверяем существование файла
        if not os.path.exists(file_path):
            return f"❌ Ошибка: файл '{file_path}' не существует. Используйте write_file для создания."
        
        # Добавляем содержимое
        with open(file_path, 'a', encoding=encoding) as f:
            if add_newline and not content.startswith('\n'):
                f.write('\n')
            f.write(content)
        
        # Информация о файле
        file_size = os.path.getsize(file_path)
        
        return (f"✅ Содержимое добавлено в '{file_path}'\n"
                f"   Новый размер: {file_size} байт\n"
                f"   Добавлено символов: {len(content)}")
        
    except Exception as e:
        logger.error(f"Ошибка добавления в файл {file_path}: {e}")
        return f"❌ Ошибка добавления в файл: {str(e)}"


@create_openai_tool
async def list_files(
    directory: str = ".",
    pattern: Optional[str] = None,
    recursive: bool = False,
    show_hidden: bool = False,
    max_files: int = 100
) -> str:
    """
    Список файлов в директории.
    
    Args:
        directory: Путь к директории
        pattern: Паттерн для фильтрации (например, "*.py")
        recursive: Рекурсивный поиск
        show_hidden: Показывать скрытые файлы
        max_files: Максимальное количество файлов
    
    Returns:
        Список файлов в формате JSON
    """
    try:
        # Если путь относительный, делаем относительно /workspace
        if not os.path.isabs(directory):
            directory = os.path.join("/workspace", directory)
        
        # Проверка безопасности
        if not is_safe_path(directory):
            return json.dumps({
                "error": f"Небезопасный путь '{directory}'"
            })
        
        if not os.path.exists(directory):
            return json.dumps({
                "error": f"Директория '{directory}' не найдена"
            })
        
        if not os.path.isdir(directory):
            return json.dumps({
                "error": f"'{directory}' не является директорией"
            })
        
        files = []
        dirs = []
        count = 0
        
        if recursive:
            # Рекурсивный обход
            for root, dirnames, filenames in os.walk(directory):
                # Фильтруем скрытые директории
                if not show_hidden:
                    dirnames[:] = [d for d in dirnames if not d.startswith('.')]
                
                for dirname in dirnames:
                    if count >= max_files:
                        break
                    dir_path = os.path.relpath(os.path.join(root, dirname), directory)
                    dirs.append({
                        "name": dirname,
                        "path": dir_path,
                        "type": "directory"
                    })
                    count += 1
                
                for filename in filenames:
                    if count >= max_files:
                        break
                    
                    # Фильтр по паттерну
                    if pattern and not fnmatch.fnmatch(filename, pattern):
                        continue
                    
                    # Фильтр скрытых файлов
                    if not show_hidden and filename.startswith('.'):
                        continue
                    
                    file_path = os.path.relpath(os.path.join(root, filename), directory)
                    full_path = os.path.join(root, filename)
                    
                    try:
                        size = os.path.getsize(full_path)
                        files.append({
                            "name": filename,
                            "path": file_path,
                            "type": "file",
                            "size": size
                        })
                        count += 1
                    except:
                        pass
        else:
            # Только текущая директория
            for entry in os.listdir(directory):
                if count >= max_files:
                    break
                
                # Фильтр скрытых
                if not show_hidden and entry.startswith('.'):
                    continue
                
                full_path = os.path.join(directory, entry)
                
                if os.path.isdir(full_path):
                    dirs.append({
                        "name": entry,
                        "path": entry,
                        "type": "directory"
                    })
                    count += 1
                else:
                    # Фильтр по паттерну
                    if pattern and not fnmatch.fnmatch(entry, pattern):
                        continue
                    
                    try:
                        size = os.path.getsize(full_path)
                        files.append({
                            "name": entry,
                            "path": entry,
                            "type": "file",
                            "size": size
                        })
                        count += 1
                    except:
                        pass
        
        result = {
            "directory": directory,
            "total_files": len(files),
            "total_dirs": len(dirs),
            "files": sorted(files, key=lambda x: x['name']),
            "directories": sorted(dirs, key=lambda x: x['name'])
        }
        
        if count >= max_files:
            result["warning"] = f"Показаны первые {max_files} элементов"
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        logger.error(f"Ошибка списка файлов {directory}: {e}")
        return json.dumps({
            "error": f"Ошибка: {str(e)}"
        })


@create_openai_tool
async def search_in_files(
    pattern: str,
    directory: str = ".",
    file_pattern: Optional[str] = None,
    case_sensitive: bool = False,
    max_results: int = 50
) -> str:
    """
    Поиск текста в файлах.
    
    Args:
        pattern: Текст или регулярное выражение для поиска
        directory: Директория для поиска
        file_pattern: Паттерн файлов (например, "*.py")
        case_sensitive: Учитывать регистр
        max_results: Максимальное количество результатов
    
    Returns:
        Результаты поиска в формате JSON
    """
    try:
        import re
        
        # Если путь относительный, делаем относительно /workspace
        if not os.path.isabs(directory):
            directory = os.path.join("/workspace", directory)
        
        # Проверка безопасности
        if not is_safe_path(directory):
            return json.dumps({
                "error": f"Небезопасный путь '{directory}'"
            })
        
        # Компилируем регулярное выражение
        flags = 0 if case_sensitive else re.IGNORECASE
        try:
            regex = re.compile(pattern, flags)
        except re.error as e:
            return json.dumps({
                "error": f"Некорректное регулярное выражение: {str(e)}"
            })
        
        results = []
        files_searched = 0
        
        # Рекурсивный поиск
        for root, _, filenames in os.walk(directory):
            for filename in filenames:
                # Фильтр по паттерну файлов
                if file_pattern and not fnmatch.fnmatch(filename, file_pattern):
                    continue
                
                # Пропускаем бинарные файлы
                mime_type, _ = mimetypes.guess_type(filename)
                if mime_type and not mime_type.startswith('text/'):
                    continue
                
                file_path = os.path.join(root, filename)
                
                # Проверка безопасности файла
                if not is_safe_path(file_path):
                    continue
                
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        lines = f.readlines()
                    
                    files_searched += 1
                    file_matches = []
                    
                    for line_num, line in enumerate(lines, 1):
                        matches = list(regex.finditer(line))
                        if matches:
                            for match in matches:
                                file_matches.append({
                                    "line": line_num,
                                    "column": match.start() + 1,
                                    "text": line.rstrip(),
                                    "match": match.group()
                                })
                                
                                if len(results) + len(file_matches) >= max_results:
                                    break
                    
                    if file_matches:
                        results.append({
                            "file": os.path.relpath(file_path, directory),
                            "matches": file_matches
                        })
                    
                    if len(results) >= max_results:
                        break
                        
                except (UnicodeDecodeError, PermissionError):
                    # Пропускаем файлы которые не можем прочитать
                    pass
            
            if len(results) >= max_results:
                break
        
        return json.dumps({
            "pattern": pattern,
            "directory": directory,
            "files_searched": files_searched,
            "total_matches": sum(len(r['matches']) for r in results),
            "results": results
        }, ensure_ascii=False, indent=2)
        
    except Exception as e:
        logger.error(f"Ошибка поиска в файлах: {e}")
        return json.dumps({
            "error": f"Ошибка поиска: {str(e)}"
        })


@create_openai_tool
async def delete_file(
    file_path: str,
    confirm: bool = False
) -> str:
    """
    Удаляет файл.
    
    Args:
        file_path: Путь к файлу
        confirm: Подтверждение удаления (должно быть True)
    
    Returns:
        Сообщение о результате операции
    """
    try:
        if not confirm:
            return "⚠️ Для удаления файла установите confirm=True"
        
        # Проверка безопасности
        if not is_safe_path(file_path):
            return f"❌ Ошибка: небезопасный путь '{file_path}'"
        
        # Если путь относительный, делаем относительно /workspace
        if not os.path.isabs(file_path):
            file_path = os.path.join("/workspace", file_path)
        
        if not os.path.exists(file_path):
            return f"❌ Ошибка: файл '{file_path}' не существует"
        
        if not os.path.isfile(file_path):
            return f"❌ Ошибка: '{file_path}' не является файлом"
        
        # Получаем информацию перед удалением
        file_size = os.path.getsize(file_path)
        
        # Удаляем файл
        os.remove(file_path)
        
        return (f"✅ Файл '{file_path}' успешно удален\n"
                f"   Размер: {file_size} байт")
        
    except Exception as e:
        logger.error(f"Ошибка удаления файла {file_path}: {e}")
        return f"❌ Ошибка удаления файла: {str(e)}"


@create_openai_tool
async def file_info(file_path: str) -> str:
    """
    Получает информацию о файле.
    
    Args:
        file_path: Путь к файлу
    
    Returns:
        Информация о файле в формате JSON
    """
    try:
        # Если путь относительный, делаем относительно /workspace
        if not os.path.isabs(file_path):
            file_path = os.path.join("/workspace", file_path)
        
        # Проверка безопасности
        if not is_safe_path(file_path):
            return json.dumps({
                "error": f"Небезопасный путь '{file_path}'"
            })
        
        if not os.path.exists(file_path):
            return json.dumps({
                "error": f"Файл '{file_path}' не найден"
            })
        
        stat = os.stat(file_path)
        
        info = {
            "path": file_path,
            "name": os.path.basename(file_path),
            "directory": os.path.dirname(file_path),
            "exists": True,
            "is_file": os.path.isfile(file_path),
            "is_directory": os.path.isdir(file_path),
            "is_symlink": os.path.islink(file_path),
            "size": stat.st_size,
            "permissions": oct(stat.st_mode)[-3:],
            "modified": stat.st_mtime,
            "created": stat.st_ctime,
            "accessed": stat.st_atime
        }
        
        # Для файлов добавляем дополнительную информацию
        if info["is_file"]:
            # MIME тип
            mime_type, encoding = mimetypes.guess_type(file_path)
            info["mime_type"] = mime_type
            info["encoding"] = encoding
            
            # Расширение
            info["extension"] = os.path.splitext(file_path)[1]
            
            # Попробуем посчитать строки для текстовых файлов
            if mime_type and mime_type.startswith('text/'):
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        line_count = sum(1 for _ in f)
                    info["lines"] = line_count
                except:
                    pass
        
        return json.dumps(info, ensure_ascii=False, indent=2)
        
    except Exception as e:
        logger.error(f"Ошибка получения информации о файле {file_path}: {e}")
        return json.dumps({
            "error": f"Ошибка: {str(e)}"
        })


# Экспортируем инструменты
FILE_TOOLS = [
    read_file,
    write_file,
    append_to_file,
    list_files,
    search_in_files,
    delete_file,
    file_info
]