#!/usr/bin/env python3
"""
Скрипт для автоматических бэкапов Neo4j
Поддерживает локальные бэкапы и загрузку в облачное хранилище
"""

import logging
import os
import subprocess
import sys
import time
from datetime import datetime

import boto3

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/app/logs/backup.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class Neo4jBackup:
    def __init__(self,
                 neo4j_uri: str = "bolt://graphiti-neo4j:7687",
                 username: str = "neo4j",
                 password: str = "password",
                 backup_dir: str = "/app/backups"):
        self.neo4j_uri = neo4j_uri
        self.username = username
        self.password = password
        self.backup_dir = backup_dir

        # Создаем директорию для бэкапов
        os.makedirs(backup_dir, exist_ok=True)

        # Настройки облачного хранилища
        self.s3_bucket = os.getenv('S3_BACKUP_BUCKET')
        self.s3_access_key = os.getenv('S3_ACCESS_KEY')
        self.s3_secret_key = os.getenv('S3_SECRET_KEY')
        self.s3_endpoint = os.getenv('S3_ENDPOINT')

    def create_backup(self) -> str | None:
        """Создать бэкап Neo4j"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"neo4j_backup_{timestamp}.dump"
        backup_path = os.path.join(self.backup_dir, backup_filename)

        logger.info(f"🔄 Создание бэкапа: {backup_filename}")

        try:
            # Команда для создания бэкапа
            cmd = [
                "neo4j-admin", "database", "dump",
                "--database=neo4j",
                f"--to={backup_path}",
                f"--server-uri={self.neo4j_uri}",
                f"--username={self.username}",
                f"--password={self.password}"
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300  # 5 минут таймаут
            )

            if result.returncode == 0:
                logger.info(f"✅ Бэкап создан: {backup_path}")
                return backup_path
            else:
                logger.error(f"❌ Ошибка создания бэкапа: {result.stderr}")
                return None

        except subprocess.TimeoutExpired:
            logger.error("❌ Таймаут создания бэкапа")
            return None
        except Exception as e:
            logger.error(f"❌ Ошибка создания бэкапа: {e}")
            return None

    def upload_to_s3(self, backup_path: str) -> bool:
        """Загрузить бэкап в S3/Yandex Object Storage"""
        if not all([self.s3_bucket, self.s3_access_key, self.s3_secret_key]):
            logger.warning("⚠️ S3 настройки неполные, пропускаем загрузку")
            return False

        try:
            # Создаем S3 клиент
            s3_client = boto3.client(
                's3',
                aws_access_key_id=self.s3_access_key,
                aws_secret_access_key=self.s3_secret_key,
                endpoint_url=self.s3_endpoint
            )

            # Имя файла в S3
            s3_key = f"neo4j-backups/{os.path.basename(backup_path)}"

            logger.info(f"🔄 Загрузка в S3: {s3_key}")

            # Загружаем файл
            s3_client.upload_file(backup_path, self.s3_bucket, s3_key)

            logger.info(f"✅ Бэкап загружен в S3: s3://{self.s3_bucket}/{s3_key}")
            return True

        except Exception as e:
            logger.error(f"❌ Ошибка загрузки в S3: {e}")
            return False

    def cleanup_old_backups(self, keep_days: int = 7):
        """Удалить старые бэкапы"""
        logger.info(f"🧹 Очистка бэкапов старше {keep_days} дней")

        current_time = time.time()
        cutoff_time = current_time - (keep_days * 24 * 60 * 60)

        try:
            for filename in os.listdir(self.backup_dir):
                if filename.startswith("neo4j_backup_") and filename.endswith(".dump"):
                    file_path = os.path.join(self.backup_dir, filename)
                    file_time = os.path.getmtime(file_path)

                    if file_time < cutoff_time:
                        os.remove(file_path)
                        logger.info(f"🗑️ Удален старый бэкап: {filename}")

        except Exception as e:
            logger.error(f"❌ Ошибка очистки старых бэкапов: {e}")

    def restore_backup(self, backup_path: str) -> bool:
        """Восстановить бэкап"""
        logger.info(f"🔄 Восстановление из бэкапа: {backup_path}")

        try:
            cmd = [
                "neo4j-admin", "database", "load",
                "--database=neo4j",
                f"--from={backup_path}",
                f"--server-uri={self.neo4j_uri}",
                f"--username={self.username}",
                f"--password={self.password}",
                "--force"  # Принудительное восстановление
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600  # 10 минут таймаут
            )

            if result.returncode == 0:
                logger.info("✅ Бэкап восстановлен успешно")
                return True
            else:
                logger.error(f"❌ Ошибка восстановления: {result.stderr}")
                return False

        except Exception as e:
            logger.error(f"❌ Ошибка восстановления: {e}")
            return False

    def run_backup(self, upload_to_cloud: bool = True, cleanup: bool = True):
        """Запустить полный процесс бэкапа"""
        logger.info("🚀 Начало процесса бэкапа")

        # Создаем бэкап
        backup_path = self.create_backup()
        if not backup_path:
            logger.error("❌ Не удалось создать бэкап")
            return False

        # Загружаем в облако
        if upload_to_cloud:
            self.upload_to_s3(backup_path)

        # Очищаем старые бэкапы
        if cleanup:
            self.cleanup_old_backups()

        logger.info("✅ Процесс бэкапа завершен")
        return True

def main():
    """Главная функция"""
    # Получаем параметры из переменных окружения
    neo4j_uri = os.getenv('NEO4J_URI', 'bolt://graphiti-neo4j:7687')
    username = os.getenv('NEO4J_USERNAME', 'neo4j')
    password = os.getenv('NEO4J_PASSWORD', 'password')
    backup_dir = os.getenv('BACKUP_DIR', '/app/backups')

    # Создаем экземпляр бэкапа
    backup = Neo4jBackup(neo4j_uri, username, password, backup_dir)

    # Запускаем бэкап
    success = backup.run_backup()

    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
