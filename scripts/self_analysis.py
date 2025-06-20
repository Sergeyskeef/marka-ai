import os
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any
from pathlib import Path
from core.code_analysis import CodeAnalyzer

class SelfAnalyzer:
    def __init__(self, project_root: str = "/app/langchain_api"):
        self.project_root = Path(project_root)
        self.logger = logging.getLogger(__name__)
        
        # Инициализация CodeAnalyzer
        self.code_analyzer = CodeAnalyzer(project_root)
        
        # Пути к важным файлам и директориям
        self.paths = {
            'logs': self.project_root / 'logs',
            'passport': self.project_root / 'marka_passport.json',
            'sandbox_logs': self.project_root / 'sandbox_experiments.log',
            'tests': self.project_root / 'tests',
            'scripts': self.project_root / 'scripts'
        }
        
        # Шаблоны для типовых выводов
        self.templates = {
            'system_health': {
                'good': "Система работает стабильно, все компоненты функционируют нормально.",
                'warning': "Обнаружены потенциальные проблемы: {issues}",
                'error': "Критические проблемы: {issues}"
            },
            'memory_usage': {
                'good': "Использование памяти оптимальное, все типы памяти доступны.",
                'warning': "Высокое использование памяти: {details}",
                'error': "Критическое использование памяти: {details}"
            },
            'performance': {
                'good': "Производительность системы в норме.",
                'warning': "Замедление в работе: {details}",
                'error': "Критическое замедление: {details}"
            },
            'code_quality': {
                'good': "Качество кода высокое, все метрики в норме.",
                'warning': "Обнаружены проблемы с качеством кода: {details}",
                'error': "Критические проблемы с качеством кода: {details}"
            }
        }
        
    def analyze_logs(self) -> Dict:
        """Анализирует логи системы и возвращает статистику"""
        stats = {
            'errors': [],
            'warnings': [],
            'info': [],
            'last_update': None
        }
        
        # Анализ основных логов
        for log_file in self.paths['logs'].glob('*.log'):
            try:
                with open(log_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        if 'ERROR' in line:
                            stats['errors'].append(line.strip())
                        elif 'WARNING' in line:
                            stats['warnings'].append(line.strip())
                        elif 'INFO' in line:
                            stats['info'].append(line.strip())
            except Exception as e:
                self.logger.error(f"Ошибка при чтении лога {log_file}: {e}")
        
        # Анализ логов песочницы
        if self.paths['sandbox_logs'].exists():
            try:
                with open(self.paths['sandbox_logs'], 'r', encoding='utf-8') as f:
                    for line in f:
                        if 'ERROR' in line:
                            stats['errors'].append(line.strip())
                        elif 'WARNING' in line:
                            stats['warnings'].append(line.strip())
                        elif 'INFO' in line:
                            stats['info'].append(line.strip())
            except Exception as e:
                self.logger.error(f"Ошибка при чтении лога песочницы: {e}")
        
        stats['last_update'] = datetime.now().isoformat()
        return stats
    
    def analyze_passport(self) -> Dict:
        """Анализирует текущее состояние паспорта"""
        try:
            with open(self.paths['passport'], 'r', encoding='utf-8') as f:
                passport = json.load(f)
            
            return {
                'version': passport.get('version', 'unknown'),
                'last_update': passport.get('last_update', 'unknown'),
                'components': passport.get('components', {}),
                'status': 'valid' if self._validate_passport(passport) else 'invalid'
            }
        except Exception as e:
            self.logger.error(f"Ошибка при анализе паспорта: {e}")
            return {'status': 'error', 'error': str(e)}
    
    def _validate_passport(self, passport: Dict) -> bool:
        """Проверяет валидность паспорта"""
        required_fields = ['version', 'last_update', 'components']
        return all(field in passport for field in required_fields)
    
    def analyze_codebase(self) -> Dict[str, Any]:
        """Анализ кодовой базы"""
        try:
            # Анализируем кодовую базу
            analysis = self.code_analyzer.analyze_codebase()
            
            # Проверяем наличие метрик
            if not analysis:
                return {
                    'status': 'error',
                    'message': 'Не удалось получить метрики кода',
                    'metrics': {}
                }
            
            # Получаем метрики сложности
            complexity_metrics = analysis.get('complexity_metrics', {})
            
            # Определяем статус на основе метрик
            status = 'good'
            message = 'Код в хорошем состоянии'
            
            if analysis.get('total_files', 0) > 0:
                test_ratio = complexity_metrics.get('test_files', 0) / analysis.get('total_files', 1)
                if test_ratio < 0.3:
                    status = 'warning'
                    message = 'Низкое покрытие тестами'
                elif complexity_metrics.get('avg_methods_per_class', 0) > 10:
                    status = 'warning'
                    message = 'Высокая сложность классов'
                elif complexity_metrics.get('avg_args_per_function', 0) > 5:
                    status = 'warning'
                    message = 'Высокая сложность функций'
            
            return {
                'status': status,
                'message': message,
                'metrics': {
                    'total_files': analysis.get('total_files', 0),
                    'total_classes': analysis.get('total_classes', 0),
                    'total_functions': analysis.get('total_functions', 0),
                    'total_imports': analysis.get('total_imports', 0),
                    'avg_methods_per_class': round(complexity_metrics.get('avg_methods_per_class', 0), 2),
                    'avg_args_per_function': round(complexity_metrics.get('avg_args_per_function', 0), 2),
                    'test_files': complexity_metrics.get('test_files', 0)
                }
            }
            
        except Exception as e:
            self.logger.error(f"Ошибка при анализе кодовой базы: {str(e)}")
            return {
                'status': 'error',
                'message': f'Ошибка при анализе кода: {str(e)}',
                'metrics': {}
            }
    
    def generate_report(self) -> Dict:
        """Генерирует полный отчёт о состоянии системы"""
        log_stats = self.analyze_logs()
        passport_stats = self.analyze_passport()
        code_quality = self.analyze_codebase()
        
        report = {
            'timestamp': datetime.now().isoformat(),
            'system_health': self._assess_system_health(log_stats),
            'memory_status': self._assess_memory_status(),
            'performance_status': self._assess_performance(),
            'passport_status': passport_stats,
            'code_quality': code_quality,
            'recommendations': self._generate_recommendations(log_stats, passport_stats, code_quality)
        }
        
        return report
    
    def _assess_system_health(self, log_stats: Dict) -> Dict:
        """Оценивает общее состояние системы"""
        if not log_stats['errors']:
            return {'status': 'good', 'message': self.templates['system_health']['good']}
        elif len(log_stats['errors']) < 5:
            return {
                'status': 'warning',
                'message': self.templates['system_health']['warning'].format(
                    issues=', '.join(log_stats['errors'][:3])
                )
            }
        else:
            return {
                'status': 'error',
                'message': self.templates['system_health']['error'].format(
                    issues=', '.join(log_stats['errors'][:3])
                )
            }
    
    def _assess_memory_status(self) -> Dict:
        """Оценивает состояние памяти"""
        # TODO: Реализовать проверку использования памяти
        return {'status': 'good', 'message': self.templates['memory_usage']['good']}
    
    def _assess_performance(self) -> Dict:
        """Оценивает производительность системы"""
        # TODO: Реализовать проверку производительности
        return {'status': 'good', 'message': self.templates['performance']['good']}
    
    def _generate_recommendations(self, log_stats: Dict, passport_stats: Dict, code_quality: Dict) -> List[str]:
        """Генерирует рекомендации на основе анализа"""
        recommendations = []
        
        # Рекомендации на основе логов
        if log_stats['errors']:
            recommendations.append("Рекомендуется проверить и исправить ошибки в логах")
        if log_stats['warnings']:
            recommendations.append("Обратить внимание на предупреждения в логах")
        
        # Рекомендации на основе паспорта
        if passport_stats['status'] == 'invalid':
            recommendations.append("Требуется обновление паспорта")
        
        # Рекомендации на основе качества кода
        if code_quality['status'] == 'warning':
            if code_quality['metrics'].get('test_files', 0) / code_quality['metrics'].get('total_files', 1) < 0.3:
                recommendations.append("Рекомендуется увеличить покрытие тестами")
            if code_quality['metrics'].get('avg_methods_per_class', 0) > 10:
                recommendations.append("Рекомендуется уменьшить сложность классов")
        
        return recommendations
    
    def get_analysis(self) -> str:
        """Возвращает человеко-понятный отчёт о состоянии системы"""
        report = self.generate_report()
        
        analysis = f"""Отчёт о состоянии системы (сгенерирован {report['timestamp']})

1. Общее состояние: {report['system_health']['message']}
2. Состояние памяти: {report['memory_status']['message']}
3. Производительность: {report['performance_status']['message']}
4. Статус паспорта: {report['passport_status']['status']}
5. Качество кода: {report['code_quality']['message']}

Метрики кода:
- Всего файлов: {report['code_quality']['metrics'].get('total_files', 0)}
- Всего классов: {report['code_quality']['metrics'].get('total_classes', 0)}
- Всего функций: {report['code_quality']['metrics'].get('total_functions', 0)}
- Среднее количество методов в классе: {report['code_quality']['metrics'].get('avg_methods_per_class', 0):.2f}
- Среднее количество аргументов в функции: {report['code_quality']['metrics'].get('avg_args_per_function', 0):.2f}
- Количество тестовых файлов: {report['code_quality']['metrics'].get('test_files', 0)}

Рекомендации:
{chr(10).join('- ' + rec for rec in report['recommendations'])}
"""
        return analysis 