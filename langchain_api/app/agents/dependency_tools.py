"""
Инструменты для управления зависимостями Python
"""

import os
import json
import logging
import subprocess
import asyncio
import re
from pathlib import Path
from typing import Dict, List, Any, Optional, Set, Tuple
import pkg_resources
import sys

from .tools import create_openai_tool
from ..config import settings

logger = logging.getLogger(__name__)

# Безопасные директории для работы с зависимостями
SAFE_PROJECT_DIRS = [
    "/workspace",
    "/app",
    "/sandbox"
]


@create_openai_tool
async def pip_install(
    packages: List[str],
    upgrade: bool = False,
    requirements_file: Optional[str] = None,
    index_url: Optional[str] = None,
    extra_index_url: Optional[str] = None,
    no_deps: bool = False,
    force_reinstall: bool = False
) -> str:
    """
    Устанавливает Python пакеты через pip.
    
    Args:
        packages: Список пакетов для установки (игнорируется если указан requirements_file)
        upgrade: Обновить пакеты до последней версии
        requirements_file: Путь к файлу requirements.txt
        index_url: Альтернативный индекс пакетов (PyPI mirror)
        extra_index_url: Дополнительный индекс пакетов
        no_deps: Не устанавливать зависимости
        force_reinstall: Переустановить пакеты даже если они установлены
        
    Returns:
        Результат установки в формате JSON
    """
    try:
        # Формируем команду
        cmd_parts = [sys.executable, "-m", "pip", "install"]
        
        # Добавляем флаги
        if upgrade:
            cmd_parts.append("--upgrade")
        if no_deps:
            cmd_parts.append("--no-deps")
        if force_reinstall:
            cmd_parts.append("--force-reinstall")
        if index_url:
            cmd_parts.extend(["--index-url", index_url])
        if extra_index_url:
            cmd_parts.extend(["--extra-index-url", extra_index_url])
        
        # Добавляем пакеты или requirements файл
        if requirements_file:
            from .file_tools import is_safe_path
            
            # Нормализация пути
            if not os.path.isabs(requirements_file):
                requirements_file = os.path.join("/workspace", requirements_file)
            
            # Проверка безопасности
            if not is_safe_path(requirements_file):
                return json.dumps({
                    "success": False,
                    "error": f"Небезопасный путь: {requirements_file}"
                })
            
            if not os.path.exists(requirements_file):
                return json.dumps({
                    "success": False,
                    "error": f"Файл не найден: {requirements_file}"
                })
            
            cmd_parts.extend(["-r", requirements_file])
        else:
            if not packages:
                return json.dumps({
                    "success": False,
                    "error": "Не указаны пакеты для установки"
                })
            cmd_parts.extend(packages)
        
        # Выполняем команду
        logger.info(f"🔧 Установка пакетов: {' '.join(cmd_parts)}")
        
        process = await asyncio.create_subprocess_exec(
            *cmd_parts,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        # Парсим результат
        stdout_text = stdout.decode('utf-8', errors='replace')
        stderr_text = stderr.decode('utf-8', errors='replace')
        
        # Извлекаем установленные пакеты
        installed_packages = []
        for line in stdout_text.split('\n'):
            if 'Successfully installed' in line:
                # Парсим список установленных пакетов
                packages_str = line.split('Successfully installed')[1].strip()
                installed_packages = packages_str.split()
                break
        
        result = {
            "success": process.returncode == 0,
            "return_code": process.returncode,
            "installed_packages": installed_packages,
            "already_satisfied": 'Requirement already satisfied' in stdout_text,
            "stdout": stdout_text[-2000:] if len(stdout_text) > 2000 else stdout_text,
            "stderr": stderr_text[-1000:] if stderr_text else None
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        logger.error(f"Ошибка установки пакетов: {e}")
        return json.dumps({
            "success": False,
            "error": str(e)
        })


@create_openai_tool
async def pip_uninstall(
    packages: List[str],
    yes: bool = True
) -> str:
    """
    Удаляет Python пакеты.
    
    Args:
        packages: Список пакетов для удаления
        yes: Автоматически подтверждать удаление
        
    Returns:
        Результат удаления в формате JSON
    """
    try:
        if not packages:
            return json.dumps({
                "success": False,
                "error": "Не указаны пакеты для удаления"
            })
        
        # Формируем команду
        cmd_parts = [sys.executable, "-m", "pip", "uninstall"]
        
        if yes:
            cmd_parts.append("-y")
        
        cmd_parts.extend(packages)
        
        # Выполняем команду
        logger.info(f"🗑️ Удаление пакетов: {' '.join(packages)}")
        
        process = await asyncio.create_subprocess_exec(
            *cmd_parts,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        # Парсим результат
        stdout_text = stdout.decode('utf-8', errors='replace')
        stderr_text = stderr.decode('utf-8', errors='replace')
        
        # Извлекаем удаленные пакеты
        uninstalled_packages = []
        for line in stdout_text.split('\n'):
            if 'Successfully uninstalled' in line:
                package_name = line.split('Successfully uninstalled')[1].strip()
                uninstalled_packages.append(package_name)
        
        result = {
            "success": process.returncode == 0,
            "return_code": process.returncode,
            "uninstalled_packages": uninstalled_packages,
            "stdout": stdout_text[-2000:] if len(stdout_text) > 2000 else stdout_text,
            "stderr": stderr_text[-1000:] if stderr_text else None
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        logger.error(f"Ошибка удаления пакетов: {e}")
        return json.dumps({
            "success": False,
            "error": str(e)
        })


@create_openai_tool
async def pip_list(
    format: str = "columns",
    outdated: bool = False,
    uptodate: bool = False,
    user: bool = False,
    local: bool = False
) -> str:
    """
    Показывает список установленных пакетов.
    
    Args:
        format: Формат вывода (columns, freeze, json)
        outdated: Показать только устаревшие пакеты
        uptodate: Показать только актуальные пакеты
        user: Показать только пользовательские пакеты
        local: Показать только локальные пакеты
        
    Returns:
        Список пакетов в указанном формате
    """
    try:
        # Формируем команду
        cmd_parts = [sys.executable, "-m", "pip", "list"]
        
        # Добавляем флаги
        if format in ["columns", "freeze", "json"]:
            cmd_parts.extend(["--format", format])
        else:
            format = "columns"
            cmd_parts.extend(["--format", format])
        
        if outdated:
            cmd_parts.append("--outdated")
        elif uptodate:
            cmd_parts.append("--uptodate")
        
        if user:
            cmd_parts.append("--user")
        if local:
            cmd_parts.append("--local")
        
        # Выполняем команду
        process = await asyncio.create_subprocess_exec(
            *cmd_parts,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        # Декодируем результат
        stdout_text = stdout.decode('utf-8', errors='replace')
        stderr_text = stderr.decode('utf-8', errors='replace')
        
        if process.returncode != 0:
            return json.dumps({
                "success": False,
                "error": stderr_text or "Ошибка получения списка пакетов"
            })
        
        # Парсим результат в зависимости от формата
        if format == "json":
            try:
                packages_data = json.loads(stdout_text)
                return json.dumps({
                    "success": True,
                    "packages": packages_data,
                    "total": len(packages_data)
                }, ensure_ascii=False, indent=2)
            except json.JSONDecodeError:
                pass
        
        # Для других форматов парсим текст
        packages = []
        lines = stdout_text.strip().split('\n')
        
        if format == "freeze":
            for line in lines:
                if '==' in line:
                    name, version = line.split('==', 1)
                    packages.append({"name": name, "version": version})
        else:
            # columns format - пропускаем заголовки
            for i, line in enumerate(lines):
                if i < 2:  # Пропускаем заголовок
                    continue
                parts = line.split()
                if len(parts) >= 2:
                    packages.append({
                        "name": parts[0],
                        "version": parts[1],
                        "location": parts[2] if len(parts) > 2 else None
                    })
        
        return json.dumps({
            "success": True,
            "packages": packages,
            "total": len(packages),
            "format": format
        }, ensure_ascii=False, indent=2)
        
    except Exception as e:
        logger.error(f"Ошибка получения списка пакетов: {e}")
        return json.dumps({
            "success": False,
            "error": str(e)
        })


@create_openai_tool
async def pip_show(
    packages: List[str]
) -> str:
    """
    Показывает детальную информацию о пакетах.
    
    Args:
        packages: Список пакетов для просмотра информации
        
    Returns:
        Детальная информация о пакетах
    """
    try:
        if not packages:
            return json.dumps({
                "success": False,
                "error": "Не указаны пакеты"
            })
        
        # Формируем команду
        cmd_parts = [sys.executable, "-m", "pip", "show"] + packages
        
        # Выполняем команду
        process = await asyncio.create_subprocess_exec(
            *cmd_parts,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        # Декодируем результат
        stdout_text = stdout.decode('utf-8', errors='replace')
        stderr_text = stderr.decode('utf-8', errors='replace')
        
        if process.returncode != 0:
            return json.dumps({
                "success": False,
                "error": stderr_text or "Пакеты не найдены"
            })
        
        # Парсим информацию о пакетах
        packages_info = []
        current_package = {}
        
        for line in stdout_text.split('\n'):
            line = line.strip()
            if not line:
                if current_package:
                    packages_info.append(current_package)
                    current_package = {}
                continue
            
            if ': ' in line:
                key, value = line.split(': ', 1)
                key = key.lower().replace('-', '_')
                
                # Парсим специальные поля
                if key in ['requires', 'required_by']:
                    value = [v.strip() for v in value.split(',') if v.strip()]
                elif key == 'location':
                    current_package['location'] = value
                    continue
                
                current_package[key] = value
        
        # Добавляем последний пакет
        if current_package:
            packages_info.append(current_package)
        
        return json.dumps({
            "success": True,
            "packages": packages_info,
            "total": len(packages_info)
        }, ensure_ascii=False, indent=2)
        
    except Exception as e:
        logger.error(f"Ошибка получения информации о пакетах: {e}")
        return json.dumps({
            "success": False,
            "error": str(e)
        })


@create_openai_tool
async def analyze_requirements(
    project_path: str = ".",
    output_file: Optional[str] = None,
    include_dev: bool = False
) -> str:
    """
    Анализирует зависимости проекта и генерирует requirements.txt.
    
    Args:
        project_path: Путь к проекту
        output_file: Файл для сохранения requirements (если не указан, возвращает список)
        include_dev: Включить dev-зависимости
        
    Returns:
        Список зависимостей или результат сохранения
    """
    try:
        from .file_tools import list_files, read_file, write_file, is_safe_path
        from .code_analysis_tools import analyze_imports
        
        # Нормализация пути
        if not os.path.isabs(project_path):
            project_path = os.path.join("/workspace", project_path)
        
        # Проверка безопасности
        if not is_safe_path(project_path):
            return json.dumps({
                "success": False,
                "error": f"Небезопасный путь: {project_path}"
            })
        
        # Анализируем импорты в проекте
        imports_result = await analyze_imports(project_path)
        imports_data = json.loads(imports_result)
        
        if not imports_data.get("success"):
            return json.dumps({
                "success": False,
                "error": "Ошибка анализа импортов"
            })
        
        # Получаем список установленных пакетов
        pip_list_result = await pip_list(format="json")
        pip_list_data = json.loads(pip_list_result)
        
        if not pip_list_data.get("success"):
            return json.dumps({
                "success": False,
                "error": "Ошибка получения списка пакетов"
            })
        
        installed_packages = {
            pkg["name"].lower(): pkg["version"] 
            for pkg in pip_list_data["packages"]
        }
        
        # Собираем требуемые пакеты
        required_packages = set()
        
        # Добавляем third-party импорты
        third_party_imports = set()
        for file_imports in imports_data.get("import_graph", {}).values():
            for imp in file_imports:
                # Берем корневой модуль
                root_module = imp.split('.')[0]
                # Проверяем что это third-party
                if root_module in imports_data["issues"].get("third_party", []):
                    third_party_imports.add(root_module)
        
        # Сопоставляем с установленными пакетами
        for module in third_party_imports:
            # Некоторые модули имеют другие имена пакетов
            package_name = IMPORT_TO_PACKAGE_MAP.get(module, module)
            
            if package_name.lower() in installed_packages:
                version = installed_packages[package_name.lower()]
                required_packages.add(f"{package_name}=={version}")
            else:
                # Пытаемся найти по частичному совпадению
                for pkg_name, version in installed_packages.items():
                    if module.lower() in pkg_name or pkg_name in module.lower():
                        required_packages.add(f"{pkg_name}=={version}")
                        break
        
        # Проверяем существующие requirements файлы
        existing_requirements = []
        for req_file in ["requirements.txt", "requirements.in", "setup.py", "pyproject.toml"]:
            file_path = os.path.join(project_path, req_file)
            if os.path.exists(file_path):
                existing_requirements.append(req_file)
                
                # Парсим существующие requirements
                if req_file.endswith('.txt') or req_file.endswith('.in'):
                    content = await read_file(file_path)
                    if not content.startswith("❌"):
                        for line in content.split('\n'):
                            line = line.strip()
                            if line and not line.startswith('#'):
                                required_packages.add(line)
        
        # Сортируем пакеты
        sorted_packages = sorted(required_packages)
        
        # Сохраняем или возвращаем результат
        if output_file:
            # Нормализация пути
            if not os.path.isabs(output_file):
                output_file = os.path.join("/workspace", output_file)
            
            # Проверка безопасности
            if not is_safe_path(output_file):
                return json.dumps({
                    "success": False,
                    "error": f"Небезопасный путь для сохранения: {output_file}"
                })
            
            # Формируем содержимое файла
            content_lines = [
                "# Auto-generated requirements file",
                f"# Generated from: {project_path}",
                "# Date: " + str(asyncio.get_event_loop().time()),
                ""
            ]
            content_lines.extend(sorted_packages)
            
            result = await write_file(output_file, '\n'.join(content_lines))
            
            return json.dumps({
                "success": result.startswith("✅"),
                "output_file": output_file,
                "packages_count": len(sorted_packages),
                "packages": sorted_packages,
                "existing_files": existing_requirements
            }, ensure_ascii=False, indent=2)
        else:
            return json.dumps({
                "success": True,
                "packages": sorted_packages,
                "packages_count": len(sorted_packages),
                "third_party_imports": list(third_party_imports),
                "existing_files": existing_requirements
            }, ensure_ascii=False, indent=2)
            
    except Exception as e:
        logger.error(f"Ошибка анализа зависимостей: {e}")
        return json.dumps({
            "success": False,
            "error": str(e)
        })


@create_openai_tool
async def check_security_vulnerabilities(
    packages: Optional[List[str]] = None,
    requirements_file: Optional[str] = None
) -> str:
    """
    Проверяет пакеты на известные уязвимости безопасности.
    
    Args:
        packages: Список пакетов для проверки (если не указан, проверяет все)
        requirements_file: Файл requirements для проверки
        
    Returns:
        Отчет об уязвимостях
    """
    try:
        # Сначала пробуем установить safety если его нет
        safety_check = await pip_show(["safety"])
        safety_data = json.loads(safety_check)
        
        if not safety_data.get("packages"):
            # Устанавливаем safety
            install_result = await pip_install(["safety"])
            install_data = json.loads(install_result)
            
            if not install_data.get("success"):
                # Если не удалось установить safety, делаем базовую проверку
                return await basic_security_check(packages, requirements_file)
        
        # Формируем команду safety
        cmd_parts = [sys.executable, "-m", "safety", "check", "--json"]
        
        if requirements_file:
            from .file_tools import is_safe_path
            
            # Нормализация пути
            if not os.path.isabs(requirements_file):
                requirements_file = os.path.join("/workspace", requirements_file)
            
            # Проверка безопасности
            if not is_safe_path(requirements_file):
                return json.dumps({
                    "success": False,
                    "error": f"Небезопасный путь: {requirements_file}"
                })
            
            cmd_parts.extend(["-r", requirements_file])
        
        # Выполняем проверку
        process = await asyncio.create_subprocess_exec(
            *cmd_parts,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        # Парсим результат
        stdout_text = stdout.decode('utf-8', errors='replace')
        
        try:
            vulnerabilities = json.loads(stdout_text)
        except json.JSONDecodeError:
            # Если не JSON, возвращаем базовую проверку
            return await basic_security_check(packages, requirements_file)
        
        # Форматируем результат
        if isinstance(vulnerabilities, list):
            vulnerable_packages = []
            for vuln in vulnerabilities:
                vulnerable_packages.append({
                    "package": vuln.get("package"),
                    "installed_version": vuln.get("installed_version"),
                    "affected_versions": vuln.get("affected_versions"),
                    "vulnerability": vuln.get("vulnerability"),
                    "description": vuln.get("description"),
                    "severity": vuln.get("severity", "unknown")
                })
            
            return json.dumps({
                "success": True,
                "vulnerabilities_found": len(vulnerable_packages),
                "vulnerable_packages": vulnerable_packages,
                "recommendation": "Обновите уязвимые пакеты до безопасных версий"
            }, ensure_ascii=False, indent=2)
        else:
            return json.dumps({
                "success": True,
                "vulnerabilities_found": 0,
                "message": "Уязвимостей не обнаружено"
            })
            
    except Exception as e:
        logger.error(f"Ошибка проверки уязвимостей: {e}")
        # Возвращаем базовую проверку при ошибке
        return await basic_security_check(packages, requirements_file)


async def basic_security_check(
    packages: Optional[List[str]] = None,
    requirements_file: Optional[str] = None
) -> str:
    """Базовая проверка безопасности без специальных инструментов"""
    try:
        # Список известных проблемных версий (упрощенный)
        KNOWN_VULNERABILITIES = {
            "django": {
                "vulnerable_versions": ["<2.2.28", "<3.2.13"],
                "severity": "high",
                "description": "SQL injection vulnerability"
            },
            "flask": {
                "vulnerable_versions": ["<2.0.3"],
                "severity": "medium",
                "description": "Security update recommended"
            },
            "requests": {
                "vulnerable_versions": ["<2.20.0"],
                "severity": "high",
                "description": "Security vulnerabilities in older versions"
            },
            "urllib3": {
                "vulnerable_versions": ["<1.26.5"],
                "severity": "high",
                "description": "Multiple security issues"
            },
            "pyyaml": {
                "vulnerable_versions": ["<5.4"],
                "severity": "high",
                "description": "Arbitrary code execution vulnerability"
            }
        }
        
        # Получаем список установленных пакетов
        pip_list_result = await pip_list(format="json")
        pip_list_data = json.loads(pip_list_result)
        
        if not pip_list_data.get("success"):
            return json.dumps({
                "success": False,
                "error": "Не удалось получить список пакетов"
            })
        
        installed_packages = {
            pkg["name"].lower(): pkg["version"]
            for pkg in pip_list_data["packages"]
        }
        
        # Проверяем на известные уязвимости
        vulnerabilities = []
        
        for pkg_name, pkg_info in KNOWN_VULNERABILITIES.items():
            if pkg_name in installed_packages:
                installed_version = installed_packages[pkg_name]
                
                # Упрощенная проверка версии
                vulnerabilities.append({
                    "package": pkg_name,
                    "installed_version": installed_version,
                    "severity": pkg_info["severity"],
                    "description": pkg_info["description"],
                    "recommendation": f"Рекомендуется обновить {pkg_name}"
                })
        
        return json.dumps({
            "success": True,
            "vulnerabilities_found": len(vulnerabilities),
            "vulnerable_packages": vulnerabilities,
            "note": "Это базовая проверка. Для полной проверки установите 'safety' пакет",
            "recommendation": "pip install safety && safety check"
        }, ensure_ascii=False, indent=2)
        
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": f"Ошибка базовой проверки: {str(e)}"
        })


# Маппинг имен импортов к именам пакетов
IMPORT_TO_PACKAGE_MAP = {
    "cv2": "opencv-python",
    "sklearn": "scikit-learn",
    "PIL": "Pillow",
    "yaml": "PyYAML",
    "msgpack": "msgpack-python",
    "openai": "openai",
    "dotenv": "python-dotenv",
    "bs4": "beautifulsoup4",
    "telegram": "python-telegram-bot",
    "httpx": "httpx",
    "fastapi": "fastapi",
    "uvicorn": "uvicorn",
    "pydantic": "pydantic",
    "sqlalchemy": "SQLAlchemy",
    "numpy": "numpy",
    "pandas": "pandas",
    "matplotlib": "matplotlib",
    "requests": "requests",
    "pytest": "pytest",
    "coverage": "coverage"
}


# Экспортируем инструменты
DEPENDENCY_TOOLS = [
    pip_install,
    pip_uninstall,
    pip_list,
    pip_show,
    analyze_requirements,
    check_security_vulnerabilities
]