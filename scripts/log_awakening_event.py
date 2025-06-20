#!/usr/bin/env python3
"""
Пример использования:
  INSIGHT    — python3 log_awakening_event.py INSIGHT "Внедрён новый механизм diff" SUCCESS sergey
  ERROR      — python3 log_awakening_event.py ERROR "Тесты не прошли: ошибка импорта" FAIL sergey
  GROWTH     — python3 log_awakening_event.py GROWTH "Оптимизирована скорость тестов" SUCCESS sergey
  REFLECTION — python3 log_awakening_event.py REFLECTION "После внедрения diff багов не выявлено" SUCCESS sergey
"""
import sys
import datetime

LOGFILE = "sandbox_awakenings.log"

def log_event(event_type, description, result=None, author=None):
    now = datetime.datetime.now().isoformat(timespec='seconds')
    line = f"[{now}] {event_type.upper()} | {description}"
    if result:
        line += f" | RESULT: {result}"
    if author:
        line += f" | BY: {author}"
    with open(LOGFILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python3 log_awakening_event.py <event_type> <description> [result] [author]")
        sys.exit(1)
    event_type = sys.argv[1]
    description = sys.argv[2]
    result = sys.argv[3] if len(sys.argv) > 3 else None
    author = sys.argv[4] if len(sys.argv) > 4 else None
    log_event(event_type, description, result, author)
    print(f"✅ Событие '{event_type}' зафиксировано в {LOGFILE}") 