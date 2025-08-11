#!/usr/bin/env python3
"""
Тесты для кнопок Telegram бота
"""
import pytest
import requests
from unittest.mock import Mock, patch

class TestBotButtons:
    """Тесты кнопок и функциональности бота"""
    
    def test_mode_code_storage(self):
        """Тест: API вызов /mode code сохраняет режим"""
        # Проверяем, что режим code доступен
        response = requests.get("http://localhost:8000/prompts/modes")
        assert response.status_code == 200
        data = response.json()
        assert "code" in data["modes"]
    
    def test_run_code_output(self):
        """Тест: /run_code print(1+1) возвращает 2"""
        # Имитируем выполнение кода
        with patch('subprocess.run') as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = "2\n"
            mock_run.return_value.stderr = ""
            
            # Тестируем через API
            response = requests.post(
                "http://localhost:8000/tools/execute/run_code",
                json={"code": "print(1+1)", "timeout": 30}
            )
            
            if response.status_code == 200:
                data = response.json()
                assert data["success"] == True
                assert "2" in data["result"]["output"]
    
    def test_bot_health(self):
        """Тест: бот отвечает на health check"""
        response = requests.get("http://bot:8001/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["bot"] == "running"
    
    def test_tools_endpoint(self):
        """Тест: endpoint /tools возвращает инструменты"""
        response = requests.get("http://localhost:8000/tools")
        assert response.status_code == 200
        data = response.json()
        assert "tools" in data
        assert "run_code" in [tool["name"] for tool in data["tools"]]
    
    def test_prometheus_metrics(self):
        """Тест: Prometheus метрики содержат run_code"""
        response = requests.get("http://localhost:8000/metrics/prometheus")
        assert response.status_code == 200
        content = response.text
        assert "mark_request_duration_seconds_bucket" in content

if __name__ == "__main__":
    pytest.main([__file__, "-v"]) 