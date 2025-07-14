# Примеры использования API Марка

## ⚠️ Важно: Выполнение команд

**Все команды в этом документе должны выполняться из контейнера `app`:**

```bash
# Вместо curl http://localhost:8000/...
# Используйте:
docker exec app python -c "import requests; print(requests.get('http://localhost:8000/...').json())"

# Вместо curl -X POST http://localhost:8000/...
# Используйте:
docker exec app python -c "import requests; print(requests.post('http://localhost:8000/...', json={...}).json())"
```

**Причина:** API доступен только внутри Docker сети контейнеров.

## Базовые сценарии

### 1. Простое взаимодействие с Марком

**Цель:** Получить ответ на простой вопрос

```bash
curl -X POST http://localhost:8000/chat/ask \
  -H "Content-Type: application/json" \
  -d '{
    "question": "Привет! Как дела?"
  }'
```

**Ответ:**
```json
{
  "response": "Привет! У меня все отлично, спасибо что спросил! Я готов помочь тебе с любыми задачами. Что тебя интересует?",
  "chat_id": null,
  "context_used": false,
  "memory_added": false
}
```

### 2. Работа с контекстом

**Цель:** Поддержание контекста разговора

```bash
# Первый вопрос
curl -X POST http://localhost:8000/chat/ask \
  -H "Content-Type: application/json" \
  -d '{
    "question": "Меня зовут Алексей",
    "chat_id": 12345
  }'

# Второй вопрос с тем же chat_id
curl -X POST http://localhost:8000/chat/ask \
  -H "Content-Type: application/json" \
  -d '{
    "question": "Как меня зовут?",
    "chat_id": 12345
  }'
```

**Ответ на второй вопрос:**
```json
{
  "response": "Тебя зовут Алексей! Я запомнил это из нашего предыдущего разговора.",
  "chat_id": 12345,
  "context_used": true,
  "memory_added": false
}
```

### 3. Выполнение команд в песочнице

**Цель:** Безопасное выполнение системных команд

```bash
# Список файлов
curl -X POST http://localhost:8000/sandbox/exec \
  -H "Content-Type: application/json" \
  -d '{
    "command": "ls -la"
  }'
```

**Ответ:**
```json
{
  "success": true,
  "output": "total 8\ndrwxr-xr-x 2 root root 4096 Jan  7 12:00 .\ndrwxr-xr-x 1 root root 4096 Jan  7 12:00 ..\n-rw-r--r-- 1 root root  123 Jan  7 12:00 test.txt",
  "error": null,
  "execution_time": 0.045
}
```

```bash
# Проверка версии Python
curl -X POST http://localhost:8000/sandbox/exec \
  -H "Content-Type: application/json" \
  -d '{
    "command": "python --version"
  }'
```

**Ответ:**
```json
{
  "success": true,
  "output": "Python 3.9.18",
  "error": null,
  "execution_time": 0.123
}
```

## Сложные кейсы

### 1. Анализ данных

**Цель:** Выполнить анализ данных в песочнице

```bash
# Создание Python скрипта для анализа
curl -X POST http://localhost:8000/sandbox/exec \
  -H "Content-Type: application/json" \
  -d '{
    "command": "echo \"import pandas as pd; import numpy as np; data = pd.DataFrame({\"x\": [1,2,3,4,5], \"y\": [2,4,6,8,10]}); print(\"Среднее значение y:\", data[\"y\"].mean()); print(\"Корреляция:\", data.corr())\" > analysis.py"
  }'

# Выполнение анализа
curl -X POST http://localhost:8000/sandbox/exec \
  -H "Content-Type: application/json" \
  -d '{
    "command": "python analysis.py"
  }'
```

**Ответ:**
```json
{
  "success": true,
  "output": "Среднее значение y: 6.0\nКорреляция:\n     x    y\nx  1.0  1.0\ny  1.0  1.0",
  "error": null,
  "execution_time": 1.234
}
```

### 2. Работа с файлами

**Цель:** Создание и обработка файлов

```bash
# Создание файла
curl -X POST http://localhost:8000/sandbox/exec \
  -H "Content-Type: application/json" \
  -d '{
    "command": "echo \"Hello, World!\" > hello.txt"
  }'

# Чтение файла
curl -X POST http://localhost:8000/sandbox/exec \
  -H "Content-Type: application/json" \
  -d '{
    "command": "cat hello.txt"
  }'

# Поиск в файле
curl -X POST http://localhost:8000/sandbox/exec \
  -H "Content-Type: application/json" \
  -d '{
    "command": "grep -i hello hello.txt"
  }'
```

### 3. Мониторинг системы

**Цель:** Получение информации о системе

```bash
# Информация о системе
curl -X POST http://localhost:8000/sandbox/exec \
  -H "Content-Type: application/json" \
  -d '{
    "command": "uname -a"
  }'

# Использование памяти
curl -X POST http://localhost:8000/sandbox/exec \
  -H "Content-Type: application/json" \
  -d '{
    "command": "free -h"
  }'

# Использование диска
curl -X POST http://localhost:8000/sandbox/exec \
  -H "Content-Type: application/json" \
  -d '{
    "command": "df -h"
  }'
```

## Интеграционные примеры

### 1. Python клиент

```python
import requests
import json
import time
from typing import Dict, Any, Optional

class MarkClient:
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.session = requests.Session()
    
    def ask_question(self, question: str, chat_id: Optional[int] = None) -> Dict[str, Any]:
        """Задать вопрос Марку"""
        response = self.session.post(
            f"{self.base_url}/chat/ask",
            json={
                "question": question,
                "chat_id": chat_id
            }
        )
        response.raise_for_status()
        return response.json()
    
    def execute_command(self, command: str) -> Dict[str, Any]:
        """Выполнить команду в песочнице"""
        response = self.session.post(
            f"{self.base_url}/sandbox/exec",
            json={"command": command}
        )
        response.raise_for_status()
        return response.json()
    
    def get_health(self) -> Dict[str, Any]:
        """Получить состояние системы"""
        response = self.session.get(f"{self.base_url}/health")
        response.raise_for_status()
        return response.json()
    
    def record_metric(self, name: str, value: float, labels: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """Записать метрику"""
        response = self.session.post(
            f"{self.base_url}/metrics/record",
            json={
                "name": name,
                "value": value,
                "labels": labels or {}
            }
        )
        response.raise_for_status()
        return response.json()
    
    def create_alert(self, severity: str, message: str, source: str) -> Dict[str, Any]:
        """Создать алерт"""
        response = self.session.post(
            f"{self.base_url}/alerts/create",
            json={
                "severity": severity,
                "message": message,
                "source": source
            }
        )
        response.raise_for_status()
        return response.json()

# Примеры использования
def main():
    client = MarkClient()
    
    # Проверка здоровья системы
    print("Проверка здоровья системы...")
    health = client.get_health()
    print(f"Статус: {health['status']}")
    
    # Задаем вопрос
    print("\nЗадаем вопрос Марку...")
    response = client.ask_question("Привет! Расскажи о своих возможностях")
    print(f"Ответ: {response['response']}")
    
    # Выполняем команду
    print("\nВыполняем команду...")
    result = client.execute_command("echo 'Hello from Mark!'")
    print(f"Результат: {result['output']}")
    
    # Записываем метрику
    print("\nЗаписываем метрику...")
    client.record_metric("test_requests", 1.0, {"test": "example"})
    print("Метрика записана")
    
    # Создаем алерт
    print("\nСоздаем алерт...")
    alert = client.create_alert("info", "Тестовый алерт", "example_script")
    print(f"Алерт создан: {alert['alert_id']}")

if __name__ == "__main__":
    main()
```

### 2. JavaScript клиент

```javascript
class MarkClient {
    constructor(baseUrl = 'http://localhost:8000') {
        this.baseUrl = baseUrl;
    }
    
    async askQuestion(question, chatId = null) {
        const response = await fetch(`${this.baseUrl}/chat/ask`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                question: question,
                chat_id: chatId
            })
        });
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        return await response.json();
    }
    
    async executeCommand(command) {
        const response = await fetch(`${this.baseUrl}/sandbox/exec`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ command: command })
        });
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        return await response.json();
    }
    
    async getHealth() {
        const response = await fetch(`${this.baseUrl}/health`);
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        return await response.json();
    }
    
    async recordMetric(name, value, labels = {}) {
        const response = await fetch(`${this.baseUrl}/metrics/record`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                name: name,
                value: value,
                labels: labels
            })
        });
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        return await response.json();
    }
    
    async createAlert(severity, message, source) {
        const response = await fetch(`${this.baseUrl}/alerts/create`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                severity: severity,
                message: message,
                source: source
            })
        });
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        return await response.json();
    }
}

// Примеры использования
async function main() {
    const client = new MarkClient();
    
    try {
        // Проверка здоровья системы
        console.log('Проверка здоровья системы...');
        const health = await client.getHealth();
        console.log(`Статус: ${health.status}`);
        
        // Задаем вопрос
        console.log('\nЗадаем вопрос Марку...');
        const response = await client.askQuestion('Привет! Как дела?');
        console.log(`Ответ: ${response.response}`);
        
        // Выполняем команду
        console.log('\nВыполняем команду...');
        const result = await client.executeCommand('echo "Hello from Mark!"');
        console.log(`Результат: ${result.output}`);
        
        // Записываем метрику
        console.log('\nЗаписываем метрику...');
        await client.recordMetric('test_requests', 1.0, { test: 'example' });
        console.log('Метрика записана');
        
        // Создаем алерт
        console.log('\nСоздаем алерт...');
        const alert = await client.createAlert('info', 'Тестовый алерт', 'example_script');
        console.log(`Алерт создан: ${alert.alert_id}`);
        
    } catch (error) {
        console.error('Ошибка:', error.message);
    }
}

// Запуск примера
main();
```

### 3. Bash скрипты

```bash
#!/bin/bash
# mark_client.sh - Клиент для работы с API Марка

BASE_URL="http://localhost:8000"

# Функция для работы с API
mark_api() {
    local endpoint=$1
    local method=${2:-GET}
    local data=${3:-}
    
    if [ -n "$data" ]; then
        curl -s -X "$method" \
            -H "Content-Type: application/json" \
            -d "$data" \
            "$BASE_URL$endpoint"
    else
        curl -s -X "$method" \
            "$BASE_URL$endpoint"
    fi
}

# Функция для извлечения значения из JSON
extract_value() {
    local json=$1
    local key=$2
    echo "$json" | jq -r ".$key"
}

# Проверка здоровья системы
check_health() {
    echo "Проверка здоровья системы..."
    local health=$(mark_api "/health")
    local status=$(extract_value "$health" "status")
    echo "Статус: $status"
    
    if [ "$status" = "healthy" ]; then
        echo "✅ Система работает нормально"
    else
        echo "❌ Проблемы с системой"
        return 1
    fi
}

# Задать вопрос Марку
ask_question() {
    local question=$1
    local chat_id=${2:-}
    
    echo "Задаем вопрос: $question"
    
    local data="{\"question\": \"$question\""
    if [ -n "$chat_id" ]; then
        data="$data, \"chat_id\": $chat_id"
    fi
    data="$data}"
    
    local response=$(mark_api "/chat/ask" "POST" "$data")
    local answer=$(extract_value "$response" "response")
    
    echo "Ответ: $answer"
}

# Выполнить команду
execute_command() {
    local command=$1
    
    echo "Выполняем команду: $command"
    
    local data="{\"command\": \"$command\"}"
    local response=$(mark_api "/sandbox/exec" "POST" "$data")
    local success=$(extract_value "$response" "success")
    local output=$(extract_value "$response" "output")
    local error=$(extract_value "$response" "error")
    
    if [ "$success" = "true" ]; then
        echo "✅ Команда выполнена успешно"
        echo "Вывод: $output"
    else
        echo "❌ Ошибка выполнения команды"
        echo "Ошибка: $error"
    fi
}

# Записать метрику
record_metric() {
    local name=$1
    local value=$2
    local labels=${3:-}
    
    echo "Записываем метрику: $name = $value"
    
    local data="{\"name\": \"$name\", \"value\": $value"
    if [ -n "$labels" ]; then
        data="$data, \"labels\": $labels"
    fi
    data="$data}"
    
    local response=$(mark_api "/metrics/record" "POST" "$data")
    local success=$(extract_value "$response" "success")
    
    if [ "$success" = "true" ]; then
        echo "✅ Метрика записана"
    else
        echo "❌ Ошибка записи метрики"
    fi
}

# Создать алерт
create_alert() {
    local severity=$1
    local message=$2
    local source=$3
    
    echo "Создаем алерт: $severity - $message"
    
    local data="{\"severity\": \"$severity\", \"message\": \"$message\", \"source\": \"$source\"}"
    local response=$(mark_api "/alerts/create" "POST" "$data")
    local success=$(extract_value "$response" "success")
    local alert_id=$(extract_value "$response" "alert_id")
    
    if [ "$success" = "true" ]; then
        echo "✅ Алерт создан: $alert_id"
    else
        echo "❌ Ошибка создания алерта"
    fi
}

# Получить сводку метрик
get_metrics() {
    echo "Получаем сводку метрик..."
    local metrics=$(mark_api "/metrics/summary")
    echo "$metrics" | jq '.'
}

# Получить сводку алертов
get_alerts() {
    echo "Получаем сводку алертов..."
    local alerts=$(mark_api "/alerts/summary")
    echo "$alerts" | jq '.'
}

# Основная функция
main() {
    echo "=== Клиент для работы с API Марка ==="
    
    # Проверка здоровья
    check_health || exit 1
    
    echo ""
    
    # Задаем вопрос
    ask_question "Привет! Расскажи о своих возможностях"
    
    echo ""
    
    # Выполняем команду
    execute_command "echo 'Hello from Mark!'"
    
    echo ""
    
    # Записываем метрику
    record_metric "test_requests" 1.0 '{"test": "example"}'
    
    echo ""
    
    # Создаем алерт
    create_alert "info" "Тестовый алерт из bash скрипта" "bash_client"
    
    echo ""
    
    # Получаем метрики
    get_metrics
    
    echo ""
    
    # Получаем алерты
    get_alerts
}

# Запуск скрипта
main
```

## Сценарии автоматизации

### 1. Мониторинг системы

```python
import time
import requests
from datetime import datetime

class SystemMonitor:
    def __init__(self, base_url="http://localhost:8000"):
        self.base_url = base_url
        self.session = requests.Session()
    
    def check_system_health(self):
        """Проверка здоровья системы"""
        try:
            response = self.session.get(f"{self.base_url}/health")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            return {"status": "error", "error": str(e)}
    
    def get_system_metrics(self):
        """Получение метрик системы"""
        try:
            response = self.session.get(f"{self.base_url}/metrics/summary")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            return {"error": str(e)}
    
    def record_monitoring_metric(self, metric_name, value):
        """Запись метрики мониторинга"""
        try:
            self.session.post(
                f"{self.base_url}/metrics/record",
                json={
                    "name": metric_name,
                    "value": value,
                    "labels": {"source": "system_monitor"}
                }
            )
        except Exception as e:
            print(f"Ошибка записи метрики: {e}")
    
    def create_alert_if_needed(self, health_data, metrics_data):
        """Создание алерта при необходимости"""
        try:
            # Проверка общего статуса
            if health_data.get("status") != "healthy":
                self.session.post(
                    f"{self.base_url}/alerts/create",
                    json={
                        "severity": "critical",
                        "message": f"Система нездорова: {health_data.get('status')}",
                        "source": "system_monitor"
                    }
                )
            
            # Проверка метрик
            if metrics_data.get("error_counter", 0) > 10:
                self.session.post(
                    f"{self.base_url}/alerts/create",
                    json={
                        "severity": "warning",
                        "message": f"Высокая частота ошибок: {metrics_data.get('error_counter')}",
                        "source": "system_monitor"
                    }
                )
            
            # Проверка времени ответа
            avg_response_time = metrics_data.get("request_duration", {}).get("avg", 0)
            if avg_response_time > 2.0:
                self.session.post(
                    f"{self.base_url}/alerts/create",
                    json={
                        "severity": "warning",
                        "message": f"Медленное время ответа: {avg_response_time:.2f}s",
                        "source": "system_monitor"
                    }
                )
                
        except Exception as e:
            print(f"Ошибка создания алерта: {e}")
    
    def run_monitoring_loop(self, interval=60):
        """Запуск цикла мониторинга"""
        print(f"Запуск мониторинга системы (интервал: {interval} сек)")
        
        while True:
            try:
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                print(f"\n[{timestamp}] Проверка системы...")
                
                # Проверка здоровья
                health = self.check_system_health()
                print(f"Статус здоровья: {health.get('status', 'unknown')}")
                
                # Получение метрик
                metrics = self.get_system_metrics()
                print(f"Запросов: {metrics.get('request_counter', 0)}")
                print(f"Ошибок: {metrics.get('error_counter', 0)}")
                
                # Запись метрики мониторинга
                self.record_monitoring_metric("monitoring_checks", 1)
                
                # Создание алертов при необходимости
                self.create_alert_if_needed(health, metrics)
                
                print("Мониторинг завершен")
                
            except Exception as e:
                print(f"Ошибка мониторинга: {e}")
            
            time.sleep(interval)

# Запуск мониторинга
if __name__ == "__main__":
    monitor = SystemMonitor()
    monitor.run_monitoring_loop()
```

### 2. Автоматическое тестирование

```python
import requests
import time
import json
from typing import List, Dict

class MarkTester:
    def __init__(self, base_url="http://localhost:8000"):
        self.base_url = base_url
        self.session = requests.Session()
        self.test_results = []
    
    def test_health_endpoint(self) -> Dict:
        """Тест эндпоинта здоровья"""
        try:
            response = self.session.get(f"{self.base_url}/health")
            response.raise_for_status()
            data = response.json()
            
            return {
                "test": "health_endpoint",
                "status": "passed" if data.get("status") == "healthy" else "failed",
                "response_time": response.elapsed.total_seconds(),
                "details": data
            }
        except Exception as e:
            return {
                "test": "health_endpoint",
                "status": "failed",
                "error": str(e)
            }
    
    def test_chat_endpoint(self) -> Dict:
        """Тест эндпоинта чата"""
        try:
            response = self.session.post(
                f"{self.base_url}/chat/ask",
                json={"question": "Тестовый вопрос"}
            )
            response.raise_for_status()
            data = response.json()
            
            return {
                "test": "chat_endpoint",
                "status": "passed" if "response" in data else "failed",
                "response_time": response.elapsed.total_seconds(),
                "details": data
            }
        except Exception as e:
            return {
                "test": "chat_endpoint",
                "status": "failed",
                "error": str(e)
            }
    
    def test_sandbox_endpoint(self) -> Dict:
        """Тест эндпоинта песочницы"""
        try:
            response = self.session.post(
                f"{self.base_url}/sandbox/exec",
                json={"command": "echo 'test'"}
            )
            response.raise_for_status()
            data = response.json()
            
            return {
                "test": "sandbox_endpoint",
                "status": "passed" if data.get("success") else "failed",
                "response_time": response.elapsed.total_seconds(),
                "details": data
            }
        except Exception as e:
            return {
                "test": "sandbox_endpoint",
                "status": "failed",
                "error": str(e)
            }
    
    def test_metrics_endpoint(self) -> Dict:
        """Тест эндпоинта метрик"""
        try:
            response = self.session.get(f"{self.base_url}/metrics/summary")
            response.raise_for_status()
            data = response.json()
            
            return {
                "test": "metrics_endpoint",
                "status": "passed",
                "response_time": response.elapsed.total_seconds(),
                "details": data
            }
        except Exception as e:
            return {
                "test": "metrics_endpoint",
                "status": "failed",
                "error": str(e)
            }
    
    def run_all_tests(self) -> List[Dict]:
        """Запуск всех тестов"""
        print("Запуск тестов API Марка...")
        
        tests = [
            self.test_health_endpoint,
            self.test_chat_endpoint,
            self.test_sandbox_endpoint,
            self.test_metrics_endpoint
        ]
        
        for test in tests:
            result = test()
            self.test_results.append(result)
            
            status_icon = "✅" if result["status"] == "passed" else "❌"
            print(f"{status_icon} {result['test']}: {result['status']}")
            
            if result["status"] == "failed":
                print(f"   Ошибка: {result.get('error', 'Unknown error')}")
            else:
                print(f"   Время ответа: {result.get('response_time', 0):.3f}s")
        
        return self.test_results
    
    def generate_report(self) -> Dict:
        """Генерация отчета о тестировании"""
        total_tests = len(self.test_results)
        passed_tests = len([r for r in self.test_results if r["status"] == "passed"])
        failed_tests = total_tests - passed_tests
        
        avg_response_time = sum(
            r.get("response_time", 0) for r in self.test_results 
            if r["status"] == "passed"
        ) / max(passed_tests, 1)
        
        return {
            "timestamp": time.time(),
            "summary": {
                "total_tests": total_tests,
                "passed_tests": passed_tests,
                "failed_tests": failed_tests,
                "success_rate": passed_tests / total_tests * 100,
                "avg_response_time": avg_response_time
            },
            "results": self.test_results
        }
    
    def save_report(self, filename="test_report.json"):
        """Сохранение отчета в файл"""
        report = self.generate_report()
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        print(f"\nОтчет сохранен в {filename}")
        print(f"Всего тестов: {report['summary']['total_tests']}")
        print(f"Пройдено: {report['summary']['passed_tests']}")
        print(f"Провалено: {report['summary']['failed_tests']}")
        print(f"Процент успеха: {report['summary']['success_rate']:.1f}%")
        print(f"Среднее время ответа: {report['summary']['avg_response_time']:.3f}s")

# Запуск тестирования
if __name__ == "__main__":
    tester = MarkTester()
    tester.run_all_tests()
    tester.save_report()
```

### 3. Интеграция с CI/CD

```yaml
# .github/workflows/api-test.yml
name: API Tests

on:
  push:
    branches: [ main, develop ]
  pull_request:
    branches: [ main ]

jobs:
  test:
    runs-on: ubuntu-latest
    
    steps:
    - uses: actions/checkout@v3
    
    - name: Start services
      run: |
        docker-compose up -d
        sleep 30  # Ожидание запуска сервисов
    
    - name: Run API tests
      run: |
        python tests/api_test.py
    
    - name: Upload test results
      uses: actions/upload-artifact@v3
      with:
        name: test-results
        path: test_report.json
    
    - name: Check test results
      run: |
        python -c "
        import json
        with open('test_report.json') as f:
            report = json.load(f)
        success_rate = report['summary']['success_rate']
        if success_rate < 90:
            print(f'Test success rate too low: {success_rate}%')
            exit(1)
        print(f'All tests passed! Success rate: {success_rate}%')
        "
```

## Видео туториалы

### Создание видео туториалов

Для создания видео туториалов рекомендуется использовать следующие инструменты:

1. **Screen recording:**
   - OBS Studio (бесплатно)
   - Camtasia (платно)
   - Loom (онлайн)

2. **Структура туториала:**
   - Введение (30 сек)
   - Установка и настройка (2-3 мин)
   - Базовые примеры (3-5 мин)
   - Продвинутые сценарии (5-7 мин)
   - Troubleshooting (2-3 мин)
   - Заключение (30 сек)

3. **Рекомендуемые темы:**
   - "Быстрый старт с API Марка"
   - "Интеграция с существующими системами"
   - "Мониторинг и алерты"
   - "Работа с песочницей"
   - "Отладка и troubleshooting"

### Скрипт для демонстрации

```bash
#!/bin/bash
# demo_script.sh - Скрипт для демонстрации API

echo "=== Демонстрация API Марка ==="
echo ""

# Проверка здоровья
echo "1. Проверка здоровья системы..."
curl -s http://localhost:8000/health | jq '.status'
echo ""

# Простой вопрос
echo "2. Задаем простой вопрос..."
curl -s -X POST http://localhost:8000/chat/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "Привет! Как дела?"}' | jq '.response'
echo ""

# Выполнение команды
echo "3. Выполняем команду в песочнице..."
curl -s -X POST http://localhost:8000/sandbox/exec \
  -H "Content-Type: application/json" \
  -d '{"command": "echo \"Hello from Mark!\" && date"}' | jq '.output'
echo ""

# Метрики
echo "4. Просматриваем метрики..."
curl -s http://localhost:8000/metrics/summary | jq '.request_counter'
echo ""

echo "=== Демонстрация завершена ==="
```

Эти примеры помогут разработчикам быстро начать работу с API Марка и интегрировать его в свои проекты. 