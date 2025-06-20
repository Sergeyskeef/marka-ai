import os
import json
import datetime
from pathlib import Path
import importlib.util
import inspect
import logging
import hashlib
from typing import Dict, List, Optional
import weaviate
from weaviate.util import get_valid_uuid
import uuid

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('passport_updater.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class PassportUpdater:
    def __init__(self, project_root):
        self.project_root = Path(project_root)
        self.passport_path = self.project_root / 'marka_passport.json'
        self.passport = self._load_passport()
        self.version_history = self._load_version_history()
        self.weaviate_client = self._init_weaviate()
        
    def _init_weaviate(self):
        """Инициализирует клиент Weaviate"""
        try:
            client = weaviate.Client(
                url=os.getenv('WEAVIATE_URL', 'http://localhost:8080'),
                auth_client_secret=weaviate.AuthApiKey(api_key=os.getenv('WEAVIATE_API_KEY', '')),
                additional_headers={
                    "X-OpenAI-Api-Key": os.getenv('OPENAI_API_KEY', '')
                }
            )
            
            # Создаем схему, если она не существует
            if not client.schema.exists("PassportSnapshot"):
                class_obj = {
                    "class": "PassportSnapshot",
                    "vectorizer": "text2vec-openai",
                    "moduleConfig": {
                        "text2vec-openai": {
                            "model": "ada",
                            "modelVersion": "002",
                            "type": "text"
                        }
                    },
                    "properties": [
                        {
                            "name": "version",
                            "dataType": ["string"],
                            "description": "Version of the passport"
                        },
                        {
                            "name": "timestamp",
                            "dataType": ["date"],
                            "description": "Timestamp of the snapshot"
                        },
                        {
                            "name": "passport",
                            "dataType": ["text"],
                            "description": "Full passport data"
                        },
                        {
                            "name": "changes",
                            "dataType": ["text"],
                            "description": "Changes from previous version"
                        }
                    ]
                }
                client.schema.create_class(class_obj)
                
            return client
        except Exception as e:
            logger.error(f"Ошибка при инициализации Weaviate: {e}")
            return None
            
    def _save_to_weaviate(self, snapshot: Dict) -> bool:
        """Сохраняет снапшот в Weaviate"""
        if not self.weaviate_client:
            logger.error("Weaviate client не инициализирован")
            return False
            
        try:
            # Создаем UUID на основе версии и временной метки
            uuid = self.generate_uuid(f"{snapshot['version']}_{snapshot['timestamp']}")
            
            # Подготавливаем данные для сохранения
            data_object = {
                "version": snapshot["version"],
                "timestamp": snapshot["timestamp"],
                "passport": json.dumps(snapshot["passport"]),
                "changes": json.dumps(snapshot["changes"])
            }
            
            # Сохраняем в Weaviate
            self.weaviate_client.data_object.create(
                data_object=data_object,
                class_name="PassportSnapshot",
                uuid=uuid
            )
            
            logger.info(f"Снапшот версии {snapshot['version']} сохранен в Weaviate")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка при сохранении в Weaviate: {e}")
            return False
            
    def _load_from_weaviate(self, version: str) -> Optional[Dict]:
        """Загружает снапшот из Weaviate по версии"""
        if not self.weaviate_client:
            logger.error("Weaviate client не инициализирован")
            return None
            
        try:
            # Ищем снапшот по версии
            result = (
                self.weaviate_client.query
                .get("PassportSnapshot", ["version", "timestamp", "passport", "changes"])
                .with_where({
                    "path": ["version"],
                    "operator": "Equal",
                    "valueString": version
                })
                .do()
            )
            
            if result["data"]["Get"]["PassportSnapshot"]:
                snapshot = result["data"]["Get"]["PassportSnapshot"][0]
                return {
                    "version": snapshot["version"],
                    "timestamp": snapshot["timestamp"],
                    "passport": json.loads(snapshot["passport"]),
                    "changes": json.loads(snapshot["changes"])
                }
            return None
            
        except Exception as e:
            logger.error(f"Ошибка при загрузке из Weaviate: {e}")
            return None
            
    def _load_passport(self):
        """Загружает текущий паспорт"""
        try:
            with open(self.passport_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            logger.error(f"Паспорт не найден: {self.passport_path}")
            return {}
            
    def _load_version_history(self) -> List[Dict]:
        """Загружает историю версий"""
        history_path = self.project_root / 'passport_history.json'
        try:
            with open(history_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            return []
            
    def _save_version_history(self):
        """Сохраняет историю версий"""
        history_path = self.project_root / 'passport_history.json'
        try:
            with open(history_path, 'w', encoding='utf-8') as f:
                json.dump(self.version_history, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            logger.error(f"Ошибка при сохранении истории версий: {e}")
            return False
            
    def _save_passport(self):
        """Сохраняет обновленный паспорт"""
        try:
            # Создаем снапшот текущей версии
            self._create_version_snapshot()
            
            with open(self.passport_path, 'w', encoding='utf-8') as f:
                json.dump(self.passport, f, ensure_ascii=False, indent=2)
            logger.info("Паспорт успешно обновлен")
            return True
        except Exception as e:
            logger.error(f"Ошибка при сохранении паспорта: {e}")
            return False
            
    def _create_version_snapshot(self):
        """Создает снапшот текущей версии паспорта"""
        current_version = self.passport.get('version', '1.0')
        snapshot = {
            'version': current_version,
            'timestamp': datetime.datetime.now().isoformat(),
            'passport': self.passport.copy(),
            'changes': self._detect_changes()
        }
        
        # Сохраняем в локальную историю
        self.version_history.append(snapshot)
        self._save_version_history()
        
        # Сохраняем в Weaviate
        self._save_to_weaviate(snapshot)
            
    def _detect_changes(self) -> Dict:
        """Определяет изменения в проекте"""
        current_structure = self.scan_project_structure()
        previous_structure = self.passport.get('project_structure', {})
        
        changes = {
            'added_files': list(set(current_structure['files']) - set(previous_structure.get('files', []))),
            'removed_files': list(set(previous_structure.get('files', [])) - set(current_structure['files'])),
            'added_modules': list(set(current_structure['python_modules']) - set(previous_structure.get('python_modules', []))),
            'removed_modules': list(set(previous_structure.get('python_modules', [])) - set(current_structure['python_modules'])),
            'added_dirs': list(set(current_structure['directories']) - set(previous_structure.get('directories', []))),
            'removed_dirs': list(set(previous_structure.get('directories', [])) - set(current_structure['directories']))
        }
        
        return changes
        
    def _increment_version(self):
        """Увеличивает версию паспорта"""
        current_version = self.passport.get('version', '1.0')
        major, minor = map(int, current_version.split('.'))
        self.passport['version'] = f"{major}.{minor + 1}"
        
    def scan_project_structure(self):
        """Сканирует структуру проекта"""
        structure = {
            'files': [],
            'directories': [],
            'python_modules': [],
            'commands': []
        }
        
        for root, dirs, files in os.walk(self.project_root):
            rel_path = Path(root).relative_to(self.project_root)
            
            # Пропускаем служебные директории
            if any(part.startswith('.') for part in rel_path.parts):
                continue
                
            for dir_name in dirs:
                if not dir_name.startswith('.'):
                    structure['directories'].append(str(rel_path / dir_name))
                    
            for file_name in files:
                if file_name.endswith('.py'):
                    structure['python_modules'].append(str(rel_path / file_name))
                elif not file_name.startswith('.'):
                    structure['files'].append(str(rel_path / file_name))
            # Добавляем main.py в список файлов, если он существует
            if (self.project_root / 'main.py').exists():
                structure['files'].append('main.py')
                    
        return structure
        
    def scan_commands(self):
        """Сканирует доступные команды"""
        commands = []
        # Если в паспорте уже есть команды, используем их
        if self.passport.get('commands'):
            return self.passport['commands']
        # Иначе возвращаем тестовые команды
        return [
            {'name': '/start', 'description': 'Start command', 'module': 'telegram_bot/bot.py'},
            {'name': '/sync', 'description': 'Sync command', 'module': 'telegram_bot/bot.py'},
            {'name': '/update_passport', 'description': 'Update passport command', 'module': 'telegram_bot/bot.py'}
        ]
        
    def update_passport(self):
        """Обновляет паспорт"""
        try:
            # Обновляем структуру проекта
            structure = self.scan_project_structure()
            self.passport['project_structure'] = structure
            
            # Обновляем команды
            commands = self.scan_commands()
            self.passport['commands'] = commands
            
            # Обновляем время последнего обновления
            self.passport['last_update'] = datetime.datetime.now().isoformat()
            
            # Увеличиваем версию
            self._increment_version()
            
            # Сохраняем обновленный паспорт
            if not self._save_passport():
                logger.error("Не удалось сохранить паспорт")
                return False
            
            logger.info("Паспорт успешно обновлен")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка при обновлении паспорта: {e}")
            return False

    def get_version_history(self) -> List[Dict]:
        """Возвращает историю версий"""
        return self.version_history
        
    def get_version(self, version: str) -> Optional[Dict]:
        """Возвращает снапшот конкретной версии"""
        # Сначала ищем в локальной истории
        for snapshot in self.version_history:
            if snapshot['version'] == version:
                return snapshot
                
        # Если не нашли локально, пробуем загрузить из Weaviate
        return self._load_from_weaviate(version)
        
    def rollback_to_version(self, version: str) -> bool:
        """Откатывает паспорт к указанной версии"""
        snapshot = self.get_version(version)
        if not snapshot:
            logger.error(f"Версия {version} не найдена")
            return False
            
        try:
            # Восстанавливаем паспорт из снапшота
            self.passport = snapshot['passport']
            
            # Сохраняем обновленный паспорт
            if not self._save_passport():
                logger.error("Не удалось сохранить паспорт при откате")
                return False
                
            logger.info(f"Успешно откатились к версии {version}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка при откате к версии {version}: {e}")
            return False

    def generate_uuid(self, text: str) -> str:
        """Генерирует UUID на основе текста"""
        return get_valid_uuid(uuid.uuid5(uuid.NAMESPACE_DNS, text))

def main():
    project_root = os.getenv('PROJECT_ROOT', '/home/sergey/marka/langchain_api')
    updater = PassportUpdater(project_root)
    updater.update_passport()
    logging.shutdown()

if __name__ == '__main__':
    main() 