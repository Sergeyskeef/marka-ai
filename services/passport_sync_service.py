import os
import asyncio
import logging
from typing import Optional, Callable, List
from pathlib import Path
from scripts.auto_sync_passport import PassportSyncHandler, ChangeReport
from scripts.update_passport import PassportUpdater

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename='passport_sync_service.log'
)
logger = logging.getLogger(__name__)

class PassportSyncService:
    def __init__(self, project_root: str, sync_interval: int = 60):
        self.project_root = Path(project_root)
        self.sync_interval = sync_interval
        self.updater = PassportUpdater(project_root)
        self.handler = PassportSyncHandler(self.updater, sync_interval)
        self.observer = None
        self.is_running = False
        self.notification_callbacks: List[Callable[[ChangeReport], None]] = []
        
    async def start(self):
        """Запускает сервис автосинхронизации"""
        if self.is_running:
            logger.warning("Сервис уже запущен")
            return
            
        try:
            from watchdog.observers import Observer
            self.observer = Observer()
            self.observer.schedule(self.handler, self.project_root, recursive=True)
            self.observer.start()
            self.is_running = True
            
            logger.info(f"Сервис автосинхронизации запущен в {self.project_root}")
            
            # Запускаем цикл проверки изменений
            asyncio.create_task(self._check_changes_loop())
            
        except Exception as e:
            logger.error(f"Ошибка при запуске сервиса: {e}")
            raise
            
    async def stop(self):
        """Останавливает сервис автосинхронизации"""
        if not self.is_running:
            logger.warning("Сервис не запущен")
            return
            
        try:
            if self.observer:
                self.observer.stop()
                self.observer.join()
            self.is_running = False
            logger.info("Сервис автосинхронизации остановлен")
        except Exception as e:
            logger.error(f"Ошибка при остановке сервиса: {e}")
            raise
            
    def register_notification_callback(self, callback: Callable[[ChangeReport], None]):
        """Регистрирует callback для уведомлений об изменениях"""
        self.notification_callbacks.append(callback)
        
    def unregister_notification_callback(self, callback: Callable[[ChangeReport], None]):
        """Удаляет callback из списка уведомлений"""
        if callback in self.notification_callbacks:
            self.notification_callbacks.remove(callback)
            
    async def _notify_changes(self, changes: ChangeReport):
        """Отправляет уведомления об изменениях всем зарегистрированным callback'ам"""
        for callback in self.notification_callbacks:
            try:
                callback(changes)
            except Exception as e:
                logger.error(f"Ошибка при отправке уведомления: {e}")
                
    async def _check_changes_loop(self):
        """Цикл проверки изменений"""
        while self.is_running:
            try:
                changes = self.handler.get_pending_changes()
                if any(changes.changes.values()):
                    await self._notify_changes(changes)
            except Exception as e:
                logger.error(f"Ошибка в цикле проверки изменений: {e}")
            await asyncio.sleep(self.sync_interval)
            
    async def apply_changes(self) -> bool:
        """Применяет накопленные изменения"""
        try:
            return self.handler.apply_changes()
        except Exception as e:
            logger.error(f"Ошибка при применении изменений: {e}")
            return False
            
    def get_pending_changes(self) -> ChangeReport:
        """Возвращает отчет о накопленных изменениях"""
        return self.handler.get_pending_changes()
        
    def clear_pending_changes(self):
        """Очищает накопленные изменения"""
        self.handler.clear_pending_changes()
        
    @property
    def status(self) -> dict:
        """Возвращает статус сервиса"""
        return {
            'is_running': self.is_running,
            'project_root': str(self.project_root),
            'sync_interval': self.sync_interval,
            'has_pending_changes': any(self.handler.get_pending_changes().changes.values())
        } 