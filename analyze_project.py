import json

from core.code_analysis import CodeAnalyzer


def main():
    analyzer = CodeAnalyzer('/app/langchain_api')
    analysis = analyzer.analyze_codebase()

    print('Анализ кодовой базы:')
    print(f'Всего файлов: {analysis["total_files"]}')
    print(f'Всего классов: {analysis["total_classes"]}')
    print(f'Всего функций: {analysis["total_functions"]}')
    print(f'Всего импортов: {analysis["total_imports"]}')

    print('\nМетрики сложности:')
    print(f'Среднее количество методов в классе: {analysis["complexity_metrics"]["avg_methods_per_class"]:.2f}')
    print(f'Среднее количество аргументов в функции: {analysis["complexity_metrics"]["avg_args_per_function"]:.2f}')
    print(f'Количество тестовых файлов: {analysis["complexity_metrics"]["test_files"]}')

    print('\nЗависимости:')
    print(f'Количество компонентов с зависимостями: {analysis["dependencies"]["components_with_deps"]}')
    print(f'Максимальное количество зависимостей: {analysis["dependencies"]["max_dependencies"]}')

    # Сохраняем полный анализ в JSON файл
    with open('project_analysis.json', 'w') as f:
        json.dump(analysis, f, indent=2)

if __name__ == '__main__':
    main()
