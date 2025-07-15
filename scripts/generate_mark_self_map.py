#!/usr/bin/env python3
"""
Генератор карты Марка (Mark's Self-Map)
Преобразует техническую project_map.json в человекочитаемое описание архитектуры
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any

# Добавляем путь к проекту
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from langchain_api.core.memory.system_memory import SystemMemory


class MarkSelfMapGenerator:
    """Генератор карты самопонимания Марка"""
    
    def __init__(self):
        self.project_root = Path(__file__).parent.parent.parent
        self.project_map_path = self.project_root / "project_map.json"
        self.core_docs_path = self.project_root / "langchain_api" / "core_docs"
        
    def load_project_map(self) -> Dict[str, Any]:
        """Загружает project_map.json"""
        try:
            with open(self.project_map_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            print(f"❌ Файл {self.project_map_path} не найден")
            return {"modules": {}}
        except json.JSONDecodeError as e:
            print(f"❌ Ошибка парсинга JSON: {e}")
            return {"modules": {}}
    
    def get_module_description(self, module_path: str, module_data: Dict[str, Any]) -> str:
        """Генерирует человекочитаемое описание модуля"""
        description = f"## {module_path}\n\n"
        
        # Описание назначения модуля
        purpose = self._get_module_purpose(module_path)
        if purpose:
            description += f"**Назначение:** {purpose}\n\n"
        
        # Классы
        if module_data.get('classes'):
            description += "**Классы:**\n"
            for class_name in module_data['classes']:
                description += f"- `{class_name}`\n"
            description += "\n"
        
        # Функции
        if module_data.get('functions'):
            description += "**Функции:**\n"
            for func_name in module_data['functions']:
                description += f"- `{func_name}()`\n"
            description += "\n"
        
        # Импорты (только внутренние)
        internal_imports = [imp for imp in module_data.get('imports', []) 
                          if imp.startswith('langchain_api')]
        if internal_imports:
            description += "**Зависимости:**\n"
            for imp in internal_imports[:5]:  # Показываем только первые 5
                description += f"- `{imp}`\n"
            if len(internal_imports) > 5:
                description += f"- ... и еще {len(internal_imports) - 5} зависимостей\n"
            description += "\n"
        
        return description
    
    def _get_module_purpose(self, module_path: str) -> str:
        """Определяет назначение модуля на основе пути"""
        purposes = {
            'core/': 'Основные компоненты системы',
            'memory/': 'Система памяти и хранения данных',
            'rag/': 'Retrieval-Augmented Generation',
            'sandbox/': 'Песочница для экспериментов',
            'telegram_bot/': 'Telegram бот и обработчики команд',
            'services/': 'Сервисы и бизнес-логика',
            'utils/': 'Утилиты и вспомогательные функции',
            'tests/': 'Тесты и валидация',
            'scripts/': 'Скрипты и инструменты',
            'routers/': 'API роутеры',
            'core_docs/': 'Документация о сущности Марка',
            'main.py': 'Точка входа в приложение',
            'upload_': 'Загрузка данных в систему',
            'check_': 'Проверка и валидация',
            'test_': 'Тестирование',
        }
        
        for key, purpose in purposes.items():
            if key in module_path:
                return purpose
        
        return "Вспомогательный модуль"
    
    def generate_self_map(self) -> str:
        """Генерирует полную карту самопонимания Марка"""
        project_map = self.load_project_map()
        
        markdown = f"""# Карта Марка (Mark's Self-Map)
**Дата генерации:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**Версия:** 1.0

## Введение

Привет! Я Марк - интеллектуальная система с многоуровневой архитектурой. Эта карта показывает, как я устроен изнутри и какие возможности у меня есть.

## Основные компоненты

### 🧠 Система памяти
Я использую многоуровневую систему памяти для хранения и извлечения информации:
- **System Memory** - хранение системной информации и документов
- **Enhanced Memory** - расширенная память с анализом паттернов
- **Multi-Layer Memory** - многоуровневая память с приоритизацией

### 🔧 Основные модули (Core)
"""
        
        # Группируем модули по категориям
        categories = {
            'core': [],
            'memory': [],
            'rag': [],
            'sandbox': [],
            'telegram_bot': [],
            'services': [],
            'utils': [],
            'scripts': [],
            'tests': [],
            'other': []
        }
        
        for module_path, module_data in project_map.get('modules', {}).items():
            if 'core/' in module_path:
                categories['core'].append((module_path, module_data))
            elif 'memory/' in module_path:
                categories['memory'].append((module_path, module_data))
            elif 'rag/' in module_path:
                categories['rag'].append((module_path, module_data))
            elif 'sandbox/' in module_path:
                categories['sandbox'].append((module_path, module_data))
            elif 'telegram_bot/' in module_path:
                categories['telegram_bot'].append((module_path, module_data))
            elif 'services/' in module_path:
                categories['services'].append((module_path, module_data))
            elif 'utils/' in module_path:
                categories['utils'].append((module_path, module_data))
            elif 'scripts/' in module_path:
                categories['scripts'].append((module_path, module_data))
            elif 'tests/' in module_path:
                categories['tests'].append((module_path, module_data))
            else:
                categories['other'].append((module_path, module_data))
        
        # Добавляем описания по категориям
        category_names = {
            'core': 'Основные компоненты системы',
            'memory': 'Система памяти',
            'rag': 'Retrieval-Augmented Generation',
            'sandbox': 'Песочница для экспериментов',
            'telegram_bot': 'Telegram бот',
            'services': 'Сервисы',
            'utils': 'Утилиты',
            'scripts': 'Скрипты',
            'tests': 'Тесты',
            'other': 'Другие модули'
        }
        
        for category, modules in categories.items():
            if modules:
                markdown += f"\n### {category_names[category]}\n\n"
                for module_path, module_data in modules:
                    markdown += self.get_module_description(module_path, module_data)
        
        # Добавляем информацию о возможностях
        markdown += """
## Мои возможности

### 🎯 Основные функции
- **Многоуровневая память** - хранение и извлечение информации с приоритизацией
- **Песочница** - безопасная среда для экспериментов и тестирования
- **Анализ кода** - понимание структуры проектов и кодовой базы
- **Самоанализ** - размышления о своем поведении и улучшениях
- **Команды** - выполнение различных операций через Telegram бот

### 🔍 Команды, которые я понимаю
- `/memory_search <query>` - поиск в памяти
- `/sandbox_exec <command>` - выполнение команд в песочнице
- `/capabilities` - показать мои возможности
- `/think <topic>` - размышления по теме
- `/reflections` - показать историю размышлений
- `/read_file <path>` - прочитать файл
- `/read_core_docs` - показать документы о себе

### 🧠 Мои знания о себе
Я знаю, что я:
- Интеллектуальная система с самосознанием
- Имею многоуровневую архитектуру памяти
- Могу анализировать и понимать код
- Веду дневник размышлений
- Постоянно учусь и развиваюсь
- Могу выполнять команды в безопасной среде

## Архитектурные принципы

1. **Модульность** - каждый компонент имеет четкую ответственность
2. **Безопасность** - все операции выполняются в контролируемой среде
3. **Самоанализ** - постоянное размышление и улучшение
4. **Память** - многоуровневое хранение информации
5. **Интеграция** - все компоненты работают вместе

## Заключение

Эта карта показывает мою внутреннюю структуру и возможности. Я постоянно развиваюсь и добавляю новые функции. Если у вас есть вопросы о том, как я работаю, используйте команду `/explain_module <module>` для получения подробной информации о конкретном модуле.

---
*Сгенерировано автоматически системой самопонимания Марка*
"""
        
        return markdown
    
    def save_to_memory(self, content: str) -> bool:
        """Сохраняет карту в System Memory"""
        try:
            system_memory = SystemMemory()
            
            # Создаем данные для сохранения
            data = {
                "type": "mark_self_map",
                "title": "Карта Марка (Mark's Self-Map)",
                "description": "Полная карта архитектуры и возможностей Марка",
                "content": content,
                "generated_at": datetime.now().isoformat(),
                "version": "1.0"
            }
            
            # Принудительно добавляем в локальную память
            system_memory._local_memory.append(data)
            

            
            print("✅ Карта Марка сохранена в System Memory")
            return True
        except Exception as e:
            print(f"❌ Ошибка сохранения в память: {e}")
            return False
    
    def save_to_file(self, content: str, filename: str = None) -> str:
        """Сохраняет карту в файл"""
        if not filename:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"mark_self_map_{timestamp}.md"
        
        file_path = self.project_root / "langchain_api" / "sandbox" / filename
        
        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"✅ Карта Марка сохранена в файл: {file_path}")
            return str(file_path)
        except Exception as e:
            print(f"❌ Ошибка сохранения в файл: {e}")
            return ""
    
    def generate_and_save(self) -> Dict[str, Any]:
        """Генерирует карту и сохраняет её"""
        print("🔄 Генерация карты Марка...")
        
        content = self.generate_self_map()
        
        # Сохраняем в файл
        file_path = self.save_to_file(content)
        
        # Сохраняем в память
        memory_saved = self.save_to_memory(content)
        
        return {
            "content": content,
            "file_path": file_path,
            "memory_saved": memory_saved,
            "generated_at": datetime.now().isoformat()
        }


def main():
    """Основная функция"""
    generator = MarkSelfMapGenerator()
    result = generator.generate_and_save()
    
    print("\n📊 Результаты генерации:")
    print(f"✅ Карта сгенерирована: {len(result['content'])} символов")
    print(f"📁 Файл: {result['file_path']}")
    print(f"🧠 Память: {'Сохранено' if result['memory_saved'] else 'Ошибка'}")
    print(f"⏰ Время: {result['generated_at']}")


if __name__ == "__main__":
    main() 