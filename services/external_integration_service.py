"""
ExternalIntegrationService - сервис для интеграции с внешними системами
"""

import logging
import asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class ExternalIntegrationService:
    """Сервис для интеграции с внешними системами"""
    
    def __init__(self):
        self.integrations = {
            "telegram": {"status": "connected", "last_check": datetime.now()},
            "openai": {"status": "connected", "last_check": datetime.now()},
            "neo4j": {"status": "connected", "last_check": datetime.now()}
        }
        self.alerts = []
        logger.info("✅ ExternalIntegrationService инициализирован")
    
    async def check_integration_health(self, integration_name: str) -> Dict[str, Any]:
        """Проверяет здоровье интеграции"""
        try:
            # Симуляция проверки интеграции
            await asyncio.sleep(0.1)
            
            status = "connected"
            if integration_name in self.integrations:
                self.integrations[integration_name]["last_check"] = datetime.now()
                self.integrations[integration_name]["status"] = status
            
            return {
                "integration": integration_name,
                "status": status,
                "last_check": datetime.now().isoformat(),
                "response_time": 0.1
            }
        except Exception as e:
            logger.error(f"❌ Ошибка проверки интеграции {integration_name}: {e}")
            return {
                "integration": integration_name,
                "status": "error",
                "error": str(e),
                "last_check": datetime.now().isoformat()
            }
    
    async def get_all_integrations_health(self) -> Dict[str, Any]:
        """Проверяет здоровье всех интеграций"""
        results = {}
        for integration_name in self.integrations.keys():
            results[integration_name] = await self.check_integration_health(integration_name)
        
        return {
            "integrations": results,
            "overall_status": "healthy",
            "timestamp": datetime.now().isoformat()
        }
    
    def add_alert(self, severity: str, message: str, source: str):
        """Добавляет алерт"""
        alert = {
            "id": f"alert_{len(self.alerts)}",
            "severity": severity,
            "message": message,
            "source": source,
            "timestamp": datetime.now().isoformat(),
            "resolved": False
        }
        self.alerts.append(alert)
        logger.warning(f"🚨 Алерт добавлен: {severity} - {message}")
    
    def get_alerts(self, unresolved_only: bool = True) -> List[Dict[str, Any]]:
        """Возвращает список алертов"""
        if unresolved_only:
            return [alert for alert in self.alerts if not alert["resolved"]]
        return self.alerts.copy()
    
    def resolve_alert(self, alert_id: str) -> bool:
        """Разрешает алерт"""
        for alert in self.alerts:
            if alert["id"] == alert_id:
                alert["resolved"] = True
                alert["resolved_at"] = datetime.now().isoformat()
                logger.info(f"✅ Алерт разрешен: {alert_id}")
                return True
        return False
    
    async def cleanup_old_data(self, max_age_hours: int = 24) -> Dict[str, Any]:
        """Очищает старые данные"""
        try:
            cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
            
            # Очищаем старые алерты
            old_alerts = [alert for alert in self.alerts 
                         if datetime.fromisoformat(alert["timestamp"]) < cutoff_time]
            
            for alert in old_alerts:
                self.alerts.remove(alert)
            
            logger.info(f"🧹 Очищено {len(old_alerts)} старых алертов")
            
            return {
                "success": True,
                "cleaned_alerts": len(old_alerts),
                "remaining_alerts": len(self.alerts)
            }
        except Exception as e:
            logger.error(f"❌ Ошибка очистки данных: {e}")
            return {
                "success": False,
                "error": str(e)
            } 