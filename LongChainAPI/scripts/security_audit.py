#!/usr/bin/env python3
"""
Аудит безопасности для Mark AI
Проверка на уязвимости, утечки данных и соответствие best practices
"""
import os
import re
import json
import subprocess
from pathlib import Path
from typing import List, Dict, Tuple
import hashlib
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

class SecurityAuditor:
    def __init__(self):
        self.workspace = Path("/workspace")
        self.issues = {
            "critical": [],
            "high": [],
            "medium": [],
            "low": [],
            "info": []
        }
        
        # Паттерны для поиска чувствительных данных
        self.sensitive_patterns = {
            "api_key": r"(?i)(api[_\-]?key|apikey)\s*[:=]\s*['\"]?([a-zA-Z0-9\-_]{20,})['\"]?",
            "secret": r"(?i)(secret|password|passwd|pwd)\s*[:=]\s*['\"]?([^\s'\"]{8,})['\"]?",
            "token": r"(?i)(token|bearer)\s*[:=]\s*['\"]?([a-zA-Z0-9\-_\.]{20,})['\"]?",
            "private_key": r"-----BEGIN\s+(RSA\s+)?PRIVATE\s+KEY-----",
            "aws_access": r"(?i)(aws_access_key_id|aws_secret_access_key)\s*[:=]\s*['\"]?([a-zA-Z0-9/+=]{20,})['\"]?",
            "connection_string": r"(?i)(mongodb|postgresql|mysql|redis)://[^:]+:[^@]+@[^\s]+",
            "jwt": r"eyJ[a-zA-Z0-9_-]*\.eyJ[a-zA-Z0-9_-]*\.[a-zA-Z0-9_-]*"
        }
        
        # Файлы для игнорирования
        self.ignore_patterns = [
            "*.pyc", "__pycache__", ".git", ".env.example*", "*.md",
            "tests/*", "docs/*", "*.log", "node_modules", "venv", ".venv"
        ]
    
    def add_issue(self, severity: str, category: str, description: str, file_path: str = None, line_num: int = None):
        """Добавить найденную проблему"""
        issue = {
            "category": category,
            "description": description,
            "file": str(file_path) if file_path else None,
            "line": line_num
        }
        self.issues[severity].append(issue)
    
    def scan_secrets(self):
        """Сканирование на утечки секретов"""
        print("\n🔍 Сканирование на утечки секретов...")
        
        for py_file in self.workspace.rglob("*.py"):
            if any(py_file.match(pattern) for pattern in self.ignore_patterns):
                continue
            
            try:
                content = py_file.read_text()
                lines = content.split('\n')
                
                for i, line in enumerate(lines, 1):
                    for pattern_name, pattern in self.sensitive_patterns.items():
                        matches = re.finditer(pattern, line)
                        for match in matches:
                            # Проверяем, не является ли это примером или тестом
                            if any(x in line.lower() for x in ['example', 'test', 'dummy', 'your-']):
                                continue
                            
                            self.add_issue(
                                "critical",
                                "secret_exposure",
                                f"Потенциальная утечка {pattern_name}",
                                py_file,
                                i
                            )
            except Exception as e:
                pass
    
    def check_dependencies(self):
        """Проверка зависимостей на уязвимости"""
        print("\n📦 Проверка зависимостей...")
        
        try:
            # Используем safety для проверки
            result = subprocess.run(
                ["safety", "check", "--json"],
                capture_output=True,
                text=True,
                cwd=self.workspace
            )
            
            if result.returncode != 0 and result.stdout:
                vulnerabilities = json.loads(result.stdout)
                for vuln in vulnerabilities:
                    self.add_issue(
                        "high",
                        "vulnerable_dependency",
                        f"{vuln['package']}: {vuln['vulnerability']}"
                    )
        except (subprocess.CalledProcessError, FileNotFoundError):
            # Fallback: проверяем известные проблемные версии
            req_file = self.workspace / "requirements.txt"
            if req_file.exists():
                content = req_file.read_text()
                
                # Проверка устаревших версий
                old_packages = {
                    "django<3.2": "Django версии ниже 3.2 имеют известные уязвимости",
                    "flask<2.0": "Flask версии ниже 2.0 имеют проблемы безопасности",
                    "requests<2.25": "Requests версии ниже 2.25 имеют уязвимости",
                    "cryptography<3.4": "Cryptography версии ниже 3.4 имеют уязвимости"
                }
                
                for pkg, desc in old_packages.items():
                    if pkg.split('<')[0] in content:
                        self.add_issue("medium", "outdated_dependency", desc)
    
    def check_code_security(self):
        """Проверка кода на уязвимости"""
        print("\n🛡️ Проверка кода на уязвимости...")
        
        security_patterns = {
            # SQL инъекции
            r"f['\"].*SELECT.*WHERE.*{": ("sql_injection", "Потенциальная SQL инъекция через f-string"),
            r"\.format\(.*\).*SELECT.*WHERE": ("sql_injection", "Потенциальная SQL инъекция через format"),
            
            # Command injection
            r"os\.system\(": ("command_injection", "Использование os.system может привести к command injection"),
            r"subprocess\..*shell=True": ("command_injection", "shell=True в subprocess опасно"),
            r"eval\(": ("code_injection", "eval() выполняет произвольный код"),
            r"exec\(": ("code_injection", "exec() выполняет произвольный код"),
            
            # Path traversal
            r"open\([^,)]*\+": ("path_traversal", "Конкатенация путей может привести к path traversal"),
            
            # Insecure random
            r"random\.": ("weak_random", "random не криптографически безопасен, используйте secrets"),
            
            # Hardcoded credentials
            r"password\s*=\s*['\"][^'\"]+['\"]": ("hardcoded_creds", "Возможно захардкоженный пароль"),
            
            # Insecure deserialization
            r"pickle\.loads": ("insecure_deserialization", "pickle.loads небезопасен для недоверенных данных"),
            r"yaml\.load\(": ("insecure_deserialization", "yaml.load небезопасен, используйте yaml.safe_load"),
        }
        
        for py_file in self.workspace.rglob("*.py"):
            if any(py_file.match(pattern) for pattern in self.ignore_patterns):
                continue
            
            try:
                content = py_file.read_text()
                lines = content.split('\n')
                
                for i, line in enumerate(lines, 1):
                    for pattern, (category, desc) in security_patterns.items():
                        if re.search(pattern, line):
                            # Пропускаем комментарии
                            if line.strip().startswith('#'):
                                continue
                            
                            severity = "high" if category in ["sql_injection", "command_injection", "code_injection"] else "medium"
                            self.add_issue(severity, category, desc, py_file, i)
            except Exception:
                pass
    
    def check_permissions(self):
        """Проверка прав доступа к файлам"""
        print("\n🔐 Проверка прав доступа...")
        
        sensitive_files = [
            ".env",
            "*.pem",
            "*.key",
            "*.p12",
            "id_rsa*"
        ]
        
        for pattern in sensitive_files:
            for file_path in self.workspace.rglob(pattern):
                stat = os.stat(file_path)
                mode = oct(stat.st_mode)[-3:]
                
                if mode != "600":
                    self.add_issue(
                        "high",
                        "insecure_permissions",
                        f"Файл {file_path.name} имеет небезопасные права доступа: {mode}",
                        file_path
                    )
    
    def check_cors_csrf(self):
        """Проверка CORS и CSRF настроек"""
        print("\n🌐 Проверка CORS и CSRF...")
        
        # Проверяем FastAPI настройки
        for py_file in self.workspace.rglob("*.py"):
            if any(py_file.match(pattern) for pattern in self.ignore_patterns):
                continue
            
            try:
                content = py_file.read_text()
                
                # CORS
                if "CORSMiddleware" in content:
                    if 'allow_origins=["*"]' in content or "allow_origins=['*']" in content:
                        self.add_issue(
                            "high",
                            "cors_misconfiguration",
                            "CORS разрешает все источники (*)",
                            py_file
                        )
                    
                    if "allow_credentials=True" in content and "*" in content:
                        self.add_issue(
                            "critical",
                            "cors_misconfiguration",
                            "CORS разрешает credentials со всех источников",
                            py_file
                        )
            except Exception:
                pass
    
    def check_input_validation(self):
        """Проверка валидации входных данных"""
        print("\n✅ Проверка валидации входных данных...")
        
        # Проверяем наличие валидации в API эндпоинтах
        api_files = list(self.workspace.glob("**/api/*.py"))
        api_files.extend(list(self.workspace.glob("**/routers/*.py")))
        
        for py_file in api_files:
            try:
                content = py_file.read_text()
                
                # Проверяем, есть ли Pydantic модели
                if "@router." in content or "@app." in content:
                    if "BaseModel" not in content and "Field" not in content:
                        self.add_issue(
                            "medium",
                            "missing_validation",
                            "API эндпоинт без явной валидации через Pydantic",
                            py_file
                        )
            except Exception:
                pass
    
    def check_error_handling(self):
        """Проверка обработки ошибок"""
        print("\n🚨 Проверка обработки ошибок...")
        
        for py_file in self.workspace.rglob("*.py"):
            if any(py_file.match(pattern) for pattern in self.ignore_patterns):
                continue
            
            try:
                content = py_file.read_text()
                lines = content.split('\n')
                
                for i, line in enumerate(lines, 1):
                    # Проверка на голый except
                    if re.match(r'^\s*except\s*:', line):
                        self.add_issue(
                            "low",
                            "broad_exception",
                            "Использование except без указания типа исключения",
                            py_file,
                            i
                        )
                    
                    # Проверка на раскрытие стека в production
                    if "traceback.format_exc()" in line or "exc_info=True" in line:
                        self.add_issue(
                            "medium",
                            "information_disclosure",
                            "Возможное раскрытие информации через stack trace",
                            py_file,
                            i
                        )
            except Exception:
                pass
    
    def check_tls_ssl(self):
        """Проверка использования TLS/SSL"""
        print("\n🔒 Проверка TLS/SSL...")
        
        for py_file in self.workspace.rglob("*.py"):
            if any(py_file.match(pattern) for pattern in self.ignore_patterns):
                continue
            
            try:
                content = py_file.read_text()
                
                # Проверка на отключение проверки сертификатов
                if "verify=False" in content or "check_hostname=False" in content:
                    self.add_issue(
                        "high",
                        "tls_verification_disabled",
                        "Отключена проверка SSL сертификатов",
                        py_file
                    )
                
                # Проверка на использование HTTP вместо HTTPS
                if re.search(r'http://(?!localhost|127\.0\.0\.1)', content):
                    self.add_issue(
                        "medium",
                        "unencrypted_connection",
                        "Использование HTTP вместо HTTPS",
                        py_file
                    )
            except Exception:
                pass
    
    def generate_report(self):
        """Генерация отчета об аудите"""
        total_issues = sum(len(issues) for issues in self.issues.values())
        
        report = {
            "summary": {
                "total_issues": total_issues,
                "critical": len(self.issues["critical"]),
                "high": len(self.issues["high"]),
                "medium": len(self.issues["medium"]),
                "low": len(self.issues["low"]),
                "info": len(self.issues["info"])
            },
            "issues": self.issues,
            "recommendations": []
        }
        
        # Рекомендации
        if self.issues["critical"]:
            report["recommendations"].append("🚨 НЕМЕДЛЕННО исправьте критические уязвимости!")
        
        if self.issues["high"]:
            report["recommendations"].append("⚠️ Исправьте высокоприоритетные проблемы перед деплоем")
        
        if any("secret_exposure" in issue["category"] for issues in self.issues.values() for issue in issues):
            report["recommendations"].append("🔑 Используйте переменные окружения для секретов")
            report["recommendations"].append("🔄 Смените все найденные ключи и пароли")
        
        if any("vulnerable_dependency" in issue["category"] for issues in self.issues.values() for issue in issues):
            report["recommendations"].append("📦 Обновите уязвимые зависимости")
        
        # Сохранение отчета
        with open("/workspace/security_audit_report.json", "w") as f:
            json.dump(report, f, indent=2)
        
        # Вывод результатов
        print("\n" + "="*60)
        print("📊 РЕЗУЛЬТАТЫ АУДИТА БЕЗОПАСНОСТИ")
        print("="*60)
        print(f"Всего проблем: {total_issues}")
        print(f"  🔴 Критические: {report['summary']['critical']}")
        print(f"  🟠 Высокие: {report['summary']['high']}")
        print(f"  🟡 Средние: {report['summary']['medium']}")
        print(f"  🔵 Низкие: {report['summary']['low']}")
        print(f"  ⚪ Информационные: {report['summary']['info']}")
        
        if report["recommendations"]:
            print("\n📋 Рекомендации:")
            for rec in report["recommendations"]:
                print(f"  {rec}")
        
        # Детали критических проблем
        if self.issues["critical"]:
            print("\n🚨 КРИТИЧЕСКИЕ ПРОБЛЕМЫ:")
            for issue in self.issues["critical"][:5]:  # Показываем первые 5
                print(f"\n  Категория: {issue['category']}")
                print(f"  Описание: {issue['description']}")
                if issue['file']:
                    print(f"  Файл: {issue['file']}:{issue['line']}")
        
        print(f"\n📄 Полный отчет сохранен в security_audit_report.json")
        
        return report["summary"]["critical"] == 0 and report["summary"]["high"] == 0
    
    def run_audit(self):
        """Запуск полного аудита"""
        print("🔍 Запуск аудита безопасности Mark AI...")
        
        self.scan_secrets()
        self.check_dependencies()
        self.check_code_security()
        self.check_permissions()
        self.check_cors_csrf()
        self.check_input_validation()
        self.check_error_handling()
        self.check_tls_ssl()
        
        return self.generate_report()


if __name__ == "__main__":
    auditor = SecurityAuditor()
    success = auditor.run_audit()
    
    sys.exit(0 if success else 1)