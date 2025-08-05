#!/usr/bin/env python3
"""
Скрипт для автоматического сбора карты архитектуры проекта:
- Обходит все .py-файлы в указанных папках
- Для каждого файла собирает импорты, классы, функции
- Строит граф зависимостей (импортов)
- Сохраняет результат в project_map.json

Запускать из контейнера app или sandbox:
    python3 langchain_api/scripts/generate_project_map.py
"""
import ast
import json
import os
import subprocess

PROJECT_ROOTS = [
    "langchain_api",
    "memory",
    "utils",
    # "rag",  # Удалено - упрощена система

    "telegram_bot",
    "core_docs",
    "extras",
]

result = {"modules": {}, "edges": [], "insights": []}

for root in PROJECT_ROOTS:
    if not os.path.isdir(root):
        continue
    for dirpath, _, filenames in os.walk(root):
        for fname in filenames:
            if not fname.endswith(".py"):
                continue
            fpath = os.path.join(dirpath, fname)
            rel_fpath = os.path.relpath(fpath)
            try:
                with open(fpath, encoding="utf-8") as f:
                    source = f.read()
                tree = ast.parse(source, filename=fpath)
            except Exception as e:
                print(f"[WARN] Не удалось обработать {fpath}: {e}")
                continue
            imports = set()
            classes = set()
            functions = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for n in node.names:
                        imports.add(n.name)
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        imports.add(node.module)
                elif isinstance(node, ast.ClassDef):
                    classes.add(node.name)
                elif isinstance(node, ast.FunctionDef):
                    functions.add(node.name)
            result["modules"][rel_fpath] = {
                "imports": sorted(imports),
                "classes": sorted(classes),
                "functions": sorted(functions),
            }
            # Добавляем рёбра для внутренних импортов
            for imp in imports:
                # Простейшая эвристика: если импорт начинается с одного из PROJECT_ROOTS, считаем его внутренним
                if any(imp.startswith(r) for r in PROJECT_ROOTS):
                    result["edges"].append({"from": rel_fpath, "to": imp.replace(".", "/") + ".py"})

# Добавляем инсайты из дневника пробуждения
try:
    with open("sandbox_awakenings.log", encoding="utf-8") as f:
        lines = f.readlines()
    for line in reversed(lines):
        if "| INSIGHT |" in line or "| REFLECTION |" in line:
            result["insights"].append(line.strip())
        if len(result["insights"]) >= 10:
            break
except Exception:
    pass

# Сохраняем результат
with open("project_map.json", "w", encoding="utf-8") as f:
    json.dump(result, f, ensure_ascii=False, indent=2)

print("✅ Карта архитектуры сохранена в project_map.json")

# Логируем инсайт в дневник пробуждения
subprocess.run([
    "python3", "langchain_api/scripts/log_awakening_event.py",
    "INSIGHT", "Сгенерирована карта архитектуры проекта (JSON и GraphML)", "SUCCESS", "system"
], check=False)

# Сохраняем GraphML
try:
    with open("project_map.graphml", "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        f.write('<graphml xmlns="http://graphml.graphdrawing.org/xmlns">\n')
        f.write('  <graph id="G" edgedefault="directed">\n')
        # Узлы
        for mod in result["modules"]:
            f.write(f'    <node id="{mod}"/>\n')
        # Рёбра
        for edge in result["edges"]:
            src, dst = edge
            f.write(f'    <edge source="{src}" target="{dst}"/>\n')
        f.write('  </graph>\n')
        f.write('</graphml>\n')
    print("✅ Карта архитектуры сохранена в project_map.graphml (GraphML)")
except Exception as e:
    print(f"❌ Ошибка при сохранении GraphML: {e}")
