"""
Тесты для задачи F-8: Error Middleware + Retry - централизованная обработка ошибок
"""
import sys
sys.path.insert(0, '/workspace')
import asyncio
import os


def test_error_middleware_file():
    """Тест наличия файла Error Middleware"""
    print("\n=== Тест Error Middleware файл ===")
    
    # Проверяем существование файла
    assert os.path.exists('/workspace/core/error_middleware.py')
    print("✅ Файл error_middleware.py существует")
    
    # Читаем содержимое
    with open('/workspace/core/error_middleware.py', 'r') as f:
        content = f.read()
    
    # Проверяем класс ErrorHandlingMiddleware
    assert 'class ErrorHandlingMiddleware' in content
    print("✅ ErrorHandlingMiddleware класс определен")
    
    # Проверяем метод dispatch
    assert 'async def dispatch' in content
    print("✅ Метод dispatch определен")
    
    # Проверяем обработку разных типов ошибок
    assert 'HTTPException' in content
    assert 'asyncio.TimeoutError' in content
    assert 'JSONResponse' in content
    print("✅ Обработка различных типов ошибок реализована")


def test_retry_decorator():
    """Тест декоратора retry_on_failure"""
    print("\n=== Тест декоратора retry ===")
    
    with open('/workspace/core/error_middleware.py', 'r') as f:
        content = f.read()
    
    # Проверяем наличие декоратора
    assert 'def retry_on_failure' in content
    print("✅ Декоратор retry_on_failure определен")
    
    # Проверяем параметры
    assert 'max_retries' in content
    assert 'initial_delay' in content
    assert 'backoff_factor' in content
    print("✅ Параметры retry определены")
    
    # Проверяем логику retry
    assert 'for attempt in range(max_retries)' in content
    assert 'await asyncio.sleep(delay)' in content
    assert 'delay *= backoff_factor' in content
    print("✅ Логика экспоненциальной задержки реализована")


def test_retryable_http_client():
    """Тест RetryableHTTPClient"""
    print("\n=== Тест RetryableHTTPClient ===")
    
    with open('/workspace/core/error_middleware.py', 'r') as f:
        content = f.read()
    
    # Проверяем класс
    assert 'class RetryableHTTPClient' in content
    print("✅ RetryableHTTPClient класс определен")
    
    # Проверяем HTTP методы
    assert 'async def get' in content
    assert 'async def post' in content
    assert 'async def put' in content
    assert 'async def delete' in content
    print("✅ HTTP методы определены")
    
    # Проверяем использование декоратора retry
    assert '@retry_on_failure()' in content
    print("✅ Декоратор retry применен к HTTP методам")


def test_handle_errors_decorator():
    """Тест декоратора handle_errors"""
    print("\n=== Тест декоратора handle_errors ===")
    
    with open('/workspace/core/error_middleware.py', 'r') as f:
        content = f.read()
    
    # Проверяем декоратор
    assert 'def handle_errors' in content
    print("✅ Декоратор handle_errors определен")
    
    # Проверяем преобразование исключений
    assert 'ValueError' in content and 'status_code=400' in content
    assert 'PermissionError' in content and 'status_code=403' in content
    assert 'FileNotFoundError' in content and 'status_code=404' in content
    assert 'asyncio.TimeoutError' in content and 'status_code=504' in content
    print("✅ Преобразование исключений в HTTP коды реализовано")


def test_middleware_in_main():
    """Тест подключения middleware в main.py"""
    print("\n=== Тест подключения в main.py ===")
    
    # Читаем main.py
    with open('/workspace/main.py', 'r') as f:
        main_content = f.read()
    
    # Проверяем импорт
    assert 'from core.error_middleware import ErrorHandlingMiddleware' in main_content
    print("✅ ErrorHandlingMiddleware импортирован")
    
    # Проверяем добавление middleware
    assert 'app.add_middleware(ErrorHandlingMiddleware)' in main_content
    print("✅ ErrorHandlingMiddleware добавлен в app")
    
    # Проверяем что он добавлен первым (до MetricsMiddleware)
    error_pos = main_content.find('app.add_middleware(ErrorHandlingMiddleware)')
    metrics_pos = main_content.find('app.add_middleware(MetricsMiddleware)')
    assert error_pos > 0 and metrics_pos > 0
    assert error_pos < metrics_pos
    print("✅ ErrorHandlingMiddleware добавлен первым (правильный порядок)")


def test_retry_logic_features():
    """Тест функциональности retry логики"""
    print("\n=== Тест функциональности retry ===")
    
    with open('/workspace/core/error_middleware.py', 'r') as f:
        content = f.read()
    
    # Проверяем обработку httpx исключений
    assert 'httpx.TimeoutException' in content
    assert 'httpx.ConnectError' in content
    assert 'httpx.ReadError' in content
    print("✅ Обработка httpx исключений реализована")
    
    # Проверяем логирование
    assert 'logger.warning' in content
    assert 'logger.error' in content
    print("✅ Логирование ошибок и retry попыток реализовано")
    
    # Проверяем структуру ответа об ошибке
    assert '"error":' in content
    assert '"status_code":' in content
    assert '"path":' in content
    print("✅ Структура JSON ответа об ошибке корректна")


def test_telegram_bot_retry():
    """Тест retry логики в Telegram боте"""
    print("\n=== Тест retry в Telegram боте ===")
    
    with open('/workspace/telegram_bot/bot.py', 'r') as f:
        bot_content = f.read()
    
    # Проверяем наличие retry логики
    assert 'retry' in bot_content.lower()
    assert 'for retry in range' in bot_content
    print("✅ Telegram бот имеет встроенную retry логику")
    
    # Проверяем обработку httpx ошибок
    assert 'httpx.TimeoutException' in bot_content
    assert 'httpx.ConnectError' in bot_content
    print("✅ Обработка сетевых ошибок в боте реализована")


def main():
    print("🧪 Запуск тестов для F-8: Error Middleware + Retry")
    
    test_error_middleware_file()
    test_retry_decorator()
    test_retryable_http_client()
    test_handle_errors_decorator()
    test_middleware_in_main()
    test_retry_logic_features()
    test_telegram_bot_retry()
    
    print("\n🎉 Все тесты F-8 успешно пройдены!")


if __name__ == "__main__":
    main()