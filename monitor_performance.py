#!/usr/bin/env python3
"""
🔬 МОНИТОР ПРОИЗВОДИТЕЛЬНОСТИ ОПТИМИЗИРОВАННОЙ СИСТЕМЫ BYBOT

Отслеживает метрики производительности в реальном времени:
- Латентность стратегий
- Memory usage
- TTL cache статистика
- Confluence факторы
- Генерация сигналов
"""

import time
import psutil
import os
import re
from datetime import datetime
from collections import defaultdict, deque

class PerformanceMonitor:
    def __init__(self, log_file="fixed_system.log"):
        self.log_file = log_file
        self.metrics = {
            'strategy_latency': defaultdict(list),
            'memory_usage': deque(maxlen=100),
            'signal_count': 0,
            'cache_operations': defaultdict(int),
            'confluence_stats': defaultdict(list),
            'errors': 0
        }
        self.start_time = datetime.now()

    def parse_log_line(self, line):
        """Парсинг одной строки лога для извлечения метрик"""
        timestamp_match = re.search(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}', line)
        if not timestamp_match:
            return None

        # Ищем метрики производительности
        if 'Время выполнения' in line or 'execution time' in line.lower():
            # Извлекаем время выполнения
            time_match = re.search(r'(\d+\.?\d*)\s*ms', line)
            if time_match:
                latency = float(time_match.group(1))
                strategy_match = re.search(r'(VolumeVWAP|MultiTF|CumDelta|Fibonacci|Range)', line)
                strategy = strategy_match.group(1) if strategy_match else 'Unknown'
                self.metrics['strategy_latency'][strategy].append(latency)

        # Ищем TTL операции
        if 'TTL' in line or 'кэш' in line.lower() or 'cache' in line.lower():
            if 'hit' in line.lower():
                self.metrics['cache_operations']['hits'] += 1
            elif 'miss' in line.lower():
                self.metrics['cache_operations']['misses'] += 1
            elif 'очистка' in line.lower() or 'cleanup' in line.lower():
                self.metrics['cache_operations']['cleanups'] += 1

        # Ищем сигналы
        if 'сигнал' in line.lower() or 'signal' in line.lower():
            if 'BUY' in line or 'SELL' in line:
                self.metrics['signal_count'] += 1

        # Ищем confluence факторы
        confluence_match = re.search(r'confluence.*?(\d+).*?факторов?', line.lower())
        if confluence_match:
            factors = int(confluence_match.group(1))
            self.metrics['confluence_stats']['factors'].append(factors)

        # Ищем ошибки
        if 'ERROR' in line or 'ошибка' in line.lower():
            self.metrics['errors'] += 1

    def get_memory_usage(self):
        """Получить текущее использование памяти"""
        try:
            # Найти процессы Python, связанные с bybot
            memory_mb = 0
            for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'memory_info']):
                try:
                    if 'python' in proc.info['name'].lower():
                        cmdline = ' '.join(proc.info['cmdline']) if proc.info['cmdline'] else ''
                        if 'main.py' in cmdline or 'bybot' in cmdline.lower():
                            memory_mb += proc.info['memory_info'].rss / 1024 / 1024
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            return memory_mb
        except Exception:
            return 0

    def monitor_logs(self):
        """Мониторинг логов в реальном времени"""
        if not os.path.exists(self.log_file):
            print(f"❌ Лог файл {self.log_file} не найден")
            return

        print(f"🔬 ЗАПУСК МОНИТОРИНГА ПРОИЗВОДИТЕЛЬНОСТИ")
        print(f"📋 Отслеживается: {self.log_file}")
        print(f"⏰ Начало: {self.start_time.strftime('%H:%M:%S')}")
        print("=" * 60)

        with open(self.log_file, 'r', encoding='utf-8') as f:
            # Перейти в конец файла
            f.seek(0, 2)

            while True:
                line = f.readline()
                if line:
                    self.parse_log_line(line.strip())
                else:
                    time.sleep(0.5)
                    self.update_display()

    def update_display(self):
        """Обновить отображение метрик"""
        # Очистить экран
        os.system('clear' if os.name == 'posix' else 'cls')

        print(f"🔬 BYBOT PERFORMANCE MONITOR - {datetime.now().strftime('%H:%M:%S')}")
        print("=" * 70)

        # Runtime
        runtime = datetime.now() - self.start_time
        print(f"⏱️  Runtime: {str(runtime).split('.')[0]}")

        # Memory Usage
        current_memory = self.get_memory_usage()
        self.metrics['memory_usage'].append(current_memory)
        avg_memory = sum(self.metrics['memory_usage']) / len(self.metrics['memory_usage']) if self.metrics['memory_usage'] else 0
        print(f"🧠 Memory: {current_memory:.1f}MB (avg: {avg_memory:.1f}MB)")

        # Strategy Latency
        print(f"\n⚡ ЛАТЕНТНОСТЬ СТРАТЕГИЙ:")
        for strategy, latencies in self.metrics['strategy_latency'].items():
            if latencies:
                avg_latency = sum(latencies[-10:]) / len(latencies[-10:])  # Последние 10
                max_latency = max(latencies[-10:])
                status = "✅" if avg_latency < 50 else "⚠️"
                print(f"   {status} {strategy}: {avg_latency:.1f}ms avg, {max_latency:.1f}ms max ({len(latencies)} calls)")

        # Signal Statistics
        signals_per_hour = self.metrics['signal_count'] / max(runtime.total_seconds() / 3600, 0.01)
        print(f"\n📊 ТОРГОВЫЕ СИГНАЛЫ:")
        print(f"   📈 Всего сигналов: {self.metrics['signal_count']}")
        print(f"   📊 Сигналов/час: {signals_per_hour:.1f}")

        # Cache Statistics
        cache_hits = self.metrics['cache_operations']['hits']
        cache_misses = self.metrics['cache_operations']['misses']
        total_cache_ops = cache_hits + cache_misses
        hit_rate = (cache_hits / total_cache_ops * 100) if total_cache_ops > 0 else 0

        print(f"\n🗂️  TTL КЭШИРОВАНИЕ:")
        print(f"   ✅ Cache hits: {cache_hits}")
        print(f"   ❌ Cache misses: {cache_misses}")
        print(f"   📊 Hit rate: {hit_rate:.1f}%")
        print(f"   🧹 Cleanups: {self.metrics['cache_operations']['cleanups']}")

        # Confluence Statistics
        confluence_factors = self.metrics['confluence_stats']['factors']
        if confluence_factors:
            avg_confluence = sum(confluence_factors) / len(confluence_factors)
            print(f"\n🎯 CONFLUENCE ФАКТОРЫ:")
            print(f"   📊 Средние факторы: {avg_confluence:.1f}/3")
            print(f"   📈 Последние: {confluence_factors[-5:] if len(confluence_factors) >= 5 else confluence_factors}")

        # Error Statistics
        error_rate = self.metrics['errors'] / max(runtime.total_seconds() / 60, 0.01)  # errors per minute
        status_errors = "✅" if error_rate < 0.1 else "⚠️" if error_rate < 1 else "❌"
        print(f"\n{status_errors} ОШИБКИ:")
        print(f"   ❌ Всего ошибок: {self.metrics['errors']}")
        print(f"   📊 Ошибок/мин: {error_rate:.2f}")

        # System Status
        print(f"\n🚀 СТАТУС СИСТЕМЫ:")
        memory_ok = current_memory < 1000  # <1GB
        latency_ok = all(
            sum(latencies[-5:]) / len(latencies[-5:]) < 50
            for latencies in self.metrics['strategy_latency'].values()
            if latencies
        ) if self.metrics['strategy_latency'] else True

        overall_status = "🟢 ОТЛИЧНО" if memory_ok and latency_ok and error_rate < 0.1 else \
                        "🟡 ХОРОШО" if memory_ok and error_rate < 1 else \
                        "🔴 ПРОБЛЕМЫ"

        print(f"   {overall_status}")
        print(f"   Memory: {'✅' if memory_ok else '❌'} | Latency: {'✅' if latency_ok else '❌'} | Errors: {'✅' if error_rate < 0.1 else '❌'}")

        print("\n" + "="*70)
        print("Нажмите Ctrl+C для остановки мониторинга")

if __name__ == "__main__":
    monitor = PerformanceMonitor()
    try:
        monitor.monitor_logs()
    except KeyboardInterrupt:
        print(f"\n🛑 Мониторинг остановлен")
        print(f"📊 Итоговая статистика:")
        print(f"   💾 Memory: {monitor.get_memory_usage():.1f}MB")
        print(f"   📈 Сигналов: {monitor.metrics['signal_count']}")
        print(f"   ❌ Ошибок: {monitor.metrics['errors']}")