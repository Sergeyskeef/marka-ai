# 🧹 КОМАНДЫ ДЛЯ ОЧИСТКИ ПРОЕКТА

## ⚠️ ВНИМАНИЕ
Перед выполнением команд убедитесь, что у вас есть резервная копия проекта!

---

## 🗑️ 1. УДАЛЕНИЕ gRPC/PROTOBUF ФАЙЛОВ

```bash
# Удаляем gRPC файлы
rm tests/helloworld_pb2.py
rm tests/helloworld_pb2_grpc.py
rm proto/helloworld.proto

# Удаляем пустую директорию proto (если пустая)
rmdir proto/ 2>/dev/null || echo "Директория proto не пустая или не существует"
```

---

## 🗑️ 2. УДАЛЕНИЕ НЕИСПОЛЬЗУЕМЫХ ДЕМО-СКРИПТОВ

```bash
# Удаляем демо-скрипт автономной разработки
rm scripts/test_autonomous_development_demo.py
```

---

## 🗑️ 3. УДАЛЕНИЕ ЗАГЛУШЕК И STUB ФАЙЛОВ

```bash
# Удаляем stub файлы
rm memory/multi_layer_memory.py

# Проверяем, есть ли наследники у base_memory.py
grep -r "class.*BaseMemory" core/ memory/ || echo "Наследников BaseMemory не найдено"
# Если наследников нет, удаляем:
# rm core/memory/base_memory.py
```

---

## 🗑️ 4. УДАЛЕНИЕ ВРЕМЕННЫХ ФАЙЛОВ

```bash
# Удаляем все .log файлы
find . -name "*.log" -type f -delete

# Удаляем все .tmp файлы
find . -name "*.tmp" -type f -delete

# Удаляем все .cache файлы
find . -name "*.cache" -type f -delete

# Удаляем все __pycache__ директории
find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null

# Удаляем .ruff_cache
rm -rf .ruff_cache/ 2>/dev/null
```

---

## 🗑️ 5. УДАЛЕНИЕ ОТЛАДОЧНЫХ ФАЙЛОВ

```bash
# Удаляем отладочные файлы
rm analyze_project.py
rm local_test.py
```

---

## 🔧 6. ЗАМЕНА PRINT() НА LOGGER

### Ручная замена в файлах:

#### rag/enhanced_rag_chain.py
```python
# Добавить в начало файла:
import logging
logger = logging.getLogger(__name__)

# Заменить все print() на logger.info()
# Например: print("debug info") -> logger.info("debug info")
```

#### rag/enhanced_rag_chain_tools.py
```python
# Добавить в начало файла:
import logging
logger = logging.getLogger(__name__)

# Заменить все print() на logger.info()
```

#### core/backend_selector.py
```python
# Добавить в начало файла:
import logging
logger = logging.getLogger(__name__)

# Заменить все print() на logger.info()
```

#### core/graphiti_config.py
```python
# Добавить в начало файла:
import logging
logger = logging.getLogger(__name__)

# Заменить все print() на logger.info()
```

#### main.py
```python
# Добавить в начало файла (если нет):
import logging
logger = logging.getLogger(__name__)

# Заменить все print() на logger.info()
```

---

## 🔍 7. ПРОВЕРКА РЕЗУЛЬТАТОВ

```bash
# Проверяем, что все тесты проходят
docker compose exec app python -m pytest -m core -v

# Проверяем, что приложение запускается
docker compose exec app python -c "import main; print('OK')"

# Проверяем Docker Compose
docker compose config

# Проверяем, что нет ошибок линтера
docker compose exec app ruff check . --exit-zero

# Подсчитываем количество файлов
find . -name "*.py" -type f | wc -l
```

---

## 📊 8. АВТОМАТИЧЕСКАЯ ОЧИСТКА

Вместо ручного выполнения команд можно использовать автоматический скрипт:

```bash
# Запуск скрипта очистки
python scripts/cleanup_project.py

# Или с указанием пути к проекту
python scripts/cleanup_project.py /path/to/project
```

---

## ⚠️ 9. ПРОВЕРКА ПОСЛЕ ОЧИСТКИ

После выполнения всех команд проверьте:

1. **Тесты проходят:**
   ```bash
   docker compose exec app python -m pytest -m core -v
   ```

2. **Приложение запускается:**
   ```bash
   docker compose exec app python -c "import main"
   ```

3. **Docker Compose работает:**
   ```bash
   docker compose config
   docker compose ps
   ```

4. **Health endpoints работают:**
   ```bash
   curl http://localhost:8000/health
   curl http://localhost:7878/health
   ```

5. **Нет критических ошибок линтера:**
   ```bash
   docker compose exec app ruff check . --exit-zero
   ```

---

## 🚨 ЕСЛИ ЧТО-ТО ПОШЛО НЕ ТАК

### Восстановление из git:
```bash
# Отменить все изменения
git checkout -- .

# Или восстановить конкретные файлы
git checkout -- main.py
git checkout -- rag/enhanced_rag_chain.py
```

### Проверка удаленных файлов:
```bash
# Посмотреть, какие файлы были удалены
git status

# Восстановить удаленные файлы
git checkout -- <filename>
```

---

## 📋 ЧЕК-ЛИСТ ВЫПОЛНЕНИЯ

- [ ] Удалены gRPC/Protobuf файлы
- [ ] Удалены неиспользуемые демо-скрипты
- [ ] Удалены заглушки и stub файлы
- [ ] Удалены временные файлы
- [ ] Удалены отладочные файлы
- [ ] Заменен print() на logger в продакшн файлах
- [ ] Проверены тесты
- [ ] Проверено приложение
- [ ] Проверен Docker Compose
- [ ] Проверены health endpoints

---

## 📞 ПОДДЕРЖКА

Если возникли проблемы:
1. Проверьте логи: `docker compose logs app`
2. Проверьте статус контейнеров: `docker compose ps`
3. Перезапустите контейнеры: `docker compose restart`
4. При необходимости восстановите из git: `git checkout -- .` 