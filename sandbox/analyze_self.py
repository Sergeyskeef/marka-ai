from self_awareness import MarkSelfAwareness
import argparse
import json
from pathlib import Path

def main():
    parser = argparse.ArgumentParser(description='Анализ структуры и возможностей Марка')
    parser.add_argument('--output', type=str, default='mark_self_description.json',
                      help='Путь для сохранения описания (по умолчанию: mark_self_description.json)')
    parser.add_argument('--format', choices=['json', 'text'], default='text',
                      help='Формат вывода (json или text)')
    parser.add_argument('--project-root', type=str, default='langchain_api',
                      help='Корневая директория проекта')
    
    args = parser.parse_args()
    
    # Создаем экземпляр класса самоанализа
    mark = MarkSelfAwareness(project_root=args.project_root)
    
    if args.format == 'json':
        # Сохраняем структурированное описание в JSON
        output_path = mark.save_self_description(args.output)
        print(f"Описание сохранено в файл: {output_path}")
    else:
        # Выводим текстовое описание
        description = mark.get_self_description()
        print(description)
        
        # Также сохраняем JSON для дальнейшего использования
        json_path = Path(args.output)
        if json_path.suffix != '.json':
            json_path = json_path.with_suffix('.json')
        mark.save_self_description(str(json_path))
        print(f"\nСтруктурированное описание сохранено в файл: {json_path}")

if __name__ == '__main__':
    main() 