# bot/core/security_scanner.py
"""
💀 КРИТИЧЕСКИЙ КОМПОНЕНТ: Security Scanner
АВТОМАТИЧЕСКОЕ ОБНАРУЖЕНИЕ УТЕЧЕК API КЛЮЧЕЙ В КОДЕ
ZERO TOLERANCE К КОМПРОМЕТАЦИИ!
"""

import os
import re
import hashlib
import json
from typing import List, Dict, Any, Tuple, Optional
from datetime import datetime
from pathlib import Path
import ast

from bot.core.exceptions import APIKeyLeakError


class SecurityScanner:
    """
    🔍 СКАНЕР БЕЗОПАСНОСТИ ДЛЯ ОБНАРУЖЕНИЯ УТЕЧЕК
    
    Функции:
    - Сканирование всех Python файлов
    - Поиск hardcoded ключей
    - Анализ логирования чувствительных данных  
    - Проверка файлов конфигурации
    - Генерация отчётов безопасности
    """
    
    def __init__(self, project_root: str = "."):
        self.project_root = Path(project_root).absolute()
        self.scan_results = {}
        self.critical_leaks = []
        self.warning_leaks = []
        self.info_notes = []
        
        # 🔍 ПАТТЕРНЫ ДЛЯ ПОИСКА КРИТИЧЕСКИХ УТЕЧЕК
        self.critical_patterns = [
            # Hardcoded API ключи
            {
                'name': 'Hardcoded Bybit API Key',
                'pattern': re.compile(r'["\']?(?:BYBIT_)?API_KEY["\']?\s*[:=]\s*["\']([a-zA-Z0-9]{20,})["\']', re.IGNORECASE),
                'severity': 'CRITICAL',
                'description': 'Hardcoded Bybit API key found'
            },
            {
                'name': 'Hardcoded Bybit API Secret',
                'pattern': re.compile(r'["\']?(?:BYBIT_)?API_SECRET["\']?\s*[:=]\s*["\']([a-zA-Z0-9]{20,})["\']', re.IGNORECASE),
                'severity': 'CRITICAL', 
                'description': 'Hardcoded Bybit API secret found'
            },
            {
                'name': 'Hardcoded Telegram Token',
                'pattern': re.compile(r'["\']([0-9]{8,10}:[a-zA-Z0-9_-]{35})["\']'),
                'severity': 'CRITICAL',
                'description': 'Hardcoded Telegram bot token found'
            },
            # Private keys
            {
                'name': 'Private Key',
                'pattern': re.compile(r'-----BEGIN (?:RSA )?PRIVATE KEY-----.*?-----END (?:RSA )?PRIVATE KEY-----', re.DOTALL),
                'severity': 'CRITICAL',
                'description': 'Private key found in code'
            }
        ]
        
        # ⚠️ ПАТТЕРНЫ ДЛЯ ПОИСКА ПРЕДУПРЕЖДЕНИЙ
        self.warning_patterns = [
            # Логирование API объектов
            {
                'name': 'API Response Logging',
                'pattern': re.compile(r'log(?:ger)?\.(?:info|debug|error)\([^)]*(?:response|api_response|result)[^)]*\)', re.IGNORECASE),
                'severity': 'WARNING',
                'description': 'Potentially unsafe API response logging'
            },
            {
                'name': 'Exception with API Data',
                'pattern': re.compile(r'(?:raise|except)[^:]*(?:api|key|secret|token)', re.IGNORECASE),
                'severity': 'WARNING', 
                'description': 'Exception handling with potential API data exposure'
            },
            {
                'name': 'Print API Data',
                'pattern': re.compile(r'print\([^)]*(?:api|key|secret|token|response)', re.IGNORECASE),
                'severity': 'WARNING',
                'description': 'Print statement with potential API data'
            }
        ]
        
        # 📁 ФАЙЛЫ И ПАПКИ ДЛЯ ИСКЛЮЧЕНИЯ
        self.exclude_patterns = [
            r'__pycache__',
            r'\.git',
            r'\.venv',
            r'venv',
            r'\.pytest_cache',
            r'node_modules',
            r'\.DS_Store',
            r'security_scanner\.py',  # Исключаем этот файл
            r'test_.*\.py$',  # Тестовые файлы могут содержать mock данные
        ]
        
        # 🔐 ЧУВСТВИТЕЛЬНЫЕ ФАЙЛЫ (ПРОВЕРЯЕМ ОБЯЗАТЕЛЬНО)
        self.sensitive_files = [
            'config.py', 'config_*.py', 'settings.py', '.env', 
            '*.key', '*.pem', '*.p12', 'secrets/*'
        ]
    
    def scan_project(self) -> Dict[str, Any]:
        """Полное сканирование проекта на утечки"""
        print("🔍 Запуск сканирования безопасности...")
        
        start_time = datetime.now()
        
        # 1. Сканируем Python файлы
        python_files = self._find_python_files()
        print(f"📁 Найдено Python файлов: {len(python_files)}")
        
        for file_path in python_files:
            self._scan_file(file_path)
        
        # 2. Сканируем конфигурационные файлы
        config_files = self._find_config_files()
        print(f"⚙️ Найдено конфигурационных файлов: {len(config_files)}")
        
        for file_path in config_files:
            self._scan_config_file(file_path)
        
        # 3. Проверяем папку secrets
        self._scan_secrets_directory()
        
        # 4. Анализируем импорты
        self._analyze_imports()
        
        # 5. Генерируем отчёт
        scan_duration = (datetime.now() - start_time).total_seconds()
        
        report = {
            'scan_time': datetime.now().isoformat(),
            'scan_duration_seconds': scan_duration,
            'project_root': str(self.project_root),
            'files_scanned': len(python_files) + len(config_files),
            'critical_leaks': len(self.critical_leaks),
            'warning_leaks': len(self.warning_leaks),
            'info_notes': len(self.info_notes),
            'critical_issues': self.critical_leaks,
            'warnings': self.warning_leaks,
            'information': self.info_notes,
            'recommendations': self._generate_recommendations()
        }
        
        self._save_report(report)
        self._print_summary(report)
        
        return report
    
    def _find_python_files(self) -> List[Path]:
        """Поиск всех Python файлов в проекте"""
        python_files = []
        
        for root, dirs, files in os.walk(self.project_root):
            # Исключаем ненужные директории
            dirs[:] = [d for d in dirs if not any(
                re.search(pattern, d) for pattern in self.exclude_patterns
            )]
            
            for file in files:
                if file.endswith('.py'):
                    file_path = Path(root) / file
                    
                    # Проверяем исключения
                    relative_path = file_path.relative_to(self.project_root)
                    if not any(re.search(pattern, str(relative_path)) for pattern in self.exclude_patterns):
                        python_files.append(file_path)
        
        return python_files
    
    def _find_config_files(self) -> List[Path]:
        """Поиск конфигурационных файлов"""
        config_files = []
        
        # Поиск по паттернам
        for pattern in self.sensitive_files:
            for file_path in self.project_root.rglob(pattern):
                if file_path.is_file():
                    config_files.append(file_path)
        
        return config_files
    
    def _scan_file(self, file_path: Path) -> None:
        """Сканирование Python файла"""
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            relative_path = file_path.relative_to(self.project_root)
            
            # Проверяем критические паттерны
            for pattern_info in self.critical_patterns:
                matches = pattern_info['pattern'].findall(content)
                if matches:
                    for match in matches:
                        leak = {
                            'file': str(relative_path),
                            'type': pattern_info['name'],
                            'severity': pattern_info['severity'],
                            'description': pattern_info['description'],
                            'line': self._find_line_number(content, match if isinstance(match, str) else match[0]),
                            'leak_hash': hashlib.md5(f"{file_path}:{match}".encode()).hexdigest()[:8]
                        }
                        self.critical_leaks.append(leak)
            
            # Проверяем предупреждения
            for pattern_info in self.warning_patterns:
                matches = pattern_info['pattern'].finditer(content)
                for match in matches:
                    leak = {
                        'file': str(relative_path),
                        'type': pattern_info['name'],
                        'severity': pattern_info['severity'],
                        'description': pattern_info['description'],
                        'line': content[:match.start()].count('\n') + 1,
                        'code_snippet': match.group().strip()
                    }
                    self.warning_leaks.append(leak)
            
            # AST анализ для более глубокой проверки
            self._analyze_ast(file_path, content)
            
        except Exception as e:
            self.info_notes.append({
                'file': str(file_path.relative_to(self.project_root)),
                'type': 'Scan Error',
                'description': f'Ошибка сканирования файла: {str(e)}'
            })
    
    def _analyze_ast(self, file_path: Path, content: str) -> None:
        """AST анализ для поиска сложных утечек"""
        try:
            tree = ast.parse(content)
            
            class SecurityVisitor(ast.NodeVisitor):
                def __init__(self, scanner, file_path):
                    self.scanner = scanner
                    self.file_path = file_path
                
                def visit_Assign(self, node):
                    # Проверяем присваивания
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            name = target.id.lower()
                            if any(keyword in name for keyword in ['key', 'secret', 'token', 'password']):
                                if isinstance(node.value, ast.Str):
                                    # Найдено присваивание строки чувствительной переменной
                                    if len(node.value.s) > 10:  # Игнорируем короткие строки
                                        leak = {
                                            'file': str(self.file_path.relative_to(self.scanner.project_root)),
                                            'type': 'Suspicious Variable Assignment',
                                            'severity': 'WARNING',
                                            'description': f'Suspicious assignment to variable "{target.id}"',
                                            'line': node.lineno
                                        }
                                        self.scanner.warning_leaks.append(leak)
                    self.generic_visit(node)
                
                def visit_Call(self, node):
                    # Проверяем вызовы функций логирования
                    if isinstance(node.func, ast.Attribute):
                        if node.func.attr in ['info', 'debug', 'error', 'warning']:
                            # Это может быть вызов logger
                            for arg in node.args:
                                if isinstance(arg, ast.JoinedStr):  # f-string
                                    # Анализируем f-string на предмет чувствительных данных
                                    for value in arg.values:
                                        if isinstance(value, ast.FormattedValue):
                                            # Проверяем переменные в f-string
                                            pass  # Можно добавить более глубокий анализ
                    self.generic_visit(node)
            
            visitor = SecurityVisitor(self, file_path)
            visitor.visit(tree)
            
        except SyntaxError:
            # Игнорируем файлы с синтаксическими ошибками
            pass
        except Exception as e:
            self.info_notes.append({
                'file': str(file_path.relative_to(self.project_root)),
                'type': 'AST Analysis Error',
                'description': f'Ошибка AST анализа: {str(e)}'
            })
    
    def _scan_config_file(self, file_path: Path) -> None:
        """Сканирование конфигурационного файла"""
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            # Особо внимательно проверяем конфигурационные файлы
            for pattern_info in self.critical_patterns + self.warning_patterns:
                matches = pattern_info['pattern'].findall(content)
                if matches:
                    for match in matches:
                        leak = {
                            'file': str(file_path.relative_to(self.project_root)),
                            'type': f"Config File: {pattern_info['name']}",
                            'severity': 'CRITICAL',  # Все утечки в конфиге критичны
                            'description': f"Configuration file contains: {pattern_info['description']}",
                            'line': self._find_line_number(content, match if isinstance(match, str) else match[0])
                        }
                        self.critical_leaks.append(leak)
                        
        except Exception as e:
            self.info_notes.append({
                'file': str(file_path.relative_to(self.project_root)),
                'type': 'Config Scan Error',
                'description': f'Ошибка сканирования конфига: {str(e)}'
            })
    
    def _scan_secrets_directory(self) -> None:
        """Сканирование папки secrets"""
        secrets_dir = self.project_root / 'secrets'
        
        if secrets_dir.exists():
            self.critical_leaks.append({
                'file': 'secrets/',
                'type': 'Secrets Directory Exists',
                'severity': 'CRITICAL',
                'description': 'Directory "secrets/" exists and may contain sensitive data',
                'line': 0,
                'recommendation': 'Remove secrets directory from repository and use environment variables'
            })
            
            # Сканируем файлы в secrets
            for file_path in secrets_dir.rglob('*'):
                if file_path.is_file():
                    self.critical_leaks.append({
                        'file': str(file_path.relative_to(self.project_root)),
                        'type': 'Secrets File',
                        'severity': 'CRITICAL', 
                        'description': 'File in secrets directory - potential API keys exposure',
                        'line': 0
                    })
    
    def _analyze_imports(self) -> None:
        """Анализ импортов на предмет небезопасных практик"""
        # Можно добавить анализ импортов config модулей и т.д.
        pass
    
    def _find_line_number(self, content: str, search_text: str) -> int:
        """Поиск номера строки для текста"""
        try:
            lines = content.split('\n')
            for i, line in enumerate(lines):
                if search_text in line:
                    return i + 1
            return 0
        except:
            return 0
    
    def _generate_recommendations(self) -> List[str]:
        """Генерация рекомендаций по безопасности"""
        recommendations = []
        
        if self.critical_leaks:
            recommendations.append("🚨 КРИТИЧНО: Немедленно смените все обнаруженные API ключи и токены!")
            recommendations.append("🔐 Используйте переменные окружения для всех секретных данных")
            recommendations.append("📁 Добавьте все секретные файлы в .gitignore")
            
        if any(leak['type'] == 'Secrets Directory Exists' for leak in self.critical_leaks):
            recommendations.append("🗂️ Удалите папку secrets/ из репозитория")
            recommendations.append("🔒 Используйте системы управления секретами (HashiCorp Vault, AWS Secrets Manager)")
            
        if self.warning_leaks:
            recommendations.append("⚠️ Внедрите secure_logger для фильтрации чувствительных данных")
            recommendations.append("🔍 Проведите code review всех мест логирования API данных")
            
        recommendations.extend([
            "✅ Настройте pre-commit hooks для проверки секретов",
            "🛡️ Используйте SecureLogger для всего логирования",
            "📊 Регулярно запускайте security scanner",
            "🔄 Ротируйте API ключи каждые 30 дней"
        ])
        
        return recommendations
    
    def _save_report(self, report: Dict[str, Any]) -> None:
        """Сохранение отчёта в файл"""
        reports_dir = self.project_root / 'data' / 'security_reports'
        reports_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = reports_dir / f"security_scan_{timestamp}.json"
        
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        print(f"💾 Отчёт сохранён: {report_file}")
    
    def _print_summary(self, report: Dict[str, Any]) -> None:
        """Печать краткого отчёта"""
        print("\n" + "="*60)
        print("🔍 ОТЧЁТ СКАНИРОВАНИЯ БЕЗОПАСНОСТИ")
        print("="*60)
        
        print(f"📁 Файлов проверено: {report['files_scanned']}")
        print(f"⏱️ Время сканирования: {report['scan_duration_seconds']:.2f} сек")
        
        if report['critical_leaks'] > 0:
            print(f"\n🚨 КРИТИЧЕСКИЕ УТЕЧКИ: {report['critical_leaks']}")
            for leak in report['critical_issues'][:5]:  # Показываем первые 5
                print(f"   💀 {leak['file']}:{leak.get('line', 0)} - {leak['type']}")
        
        if report['warning_leaks'] > 0:
            print(f"\n⚠️ ПРЕДУПРЕЖДЕНИЯ: {report['warning_leaks']}")
            
        if report['critical_leaks'] == 0 and report['warning_leaks'] == 0:
            print("\n✅ УТЕЧЕК НЕ ОБНАРУЖЕНО!")
        
        print(f"\n📋 РЕКОМЕНДАЦИИ:")
        for rec in report['recommendations'][:3]:
            print(f"   {rec}")
        
        print("="*60)


def scan_for_api_leaks(project_root: str = ".") -> Dict[str, Any]:
    """Быстрое сканирование на утечки API ключей"""
    scanner = SecurityScanner(project_root)
    return scanner.scan_project()


if __name__ == "__main__":
    # Запуск сканирования
    print("🔍 Запуск Security Scanner...")
    result = scan_for_api_leaks()
    
    if result['critical_leaks'] > 0:
        print("\n💀 ОБНАРУЖЕНЫ КРИТИЧЕСКИЕ УТЕЧКИ! ТРЕБУЕТСЯ НЕМЕДЛЕННОЕ ИСПРАВЛЕНИЕ!")
        exit(1)
    else:
        print("\n✅ Критических утечек не обнаружено")
        exit(0)