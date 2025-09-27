#!/usr/bin/env python3
"""
Экспортер метрик для торговых ботов
Предоставляет метрики в формате Prometheus
"""

import json
import logging
import os
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Dict, Any, Iterable, Optional

import psutil
import socketserver

class MetricsExporter:
    def __init__(
        self,
        port: int = 8000,
        *,
        risk_manager: Any = None,
        strategy_manager: Any = None,
        base_path: Optional[Path] = None,
        process_checks: Optional[Dict[str, Iterable[str]]] = None,
        log_files: Optional[Dict[str, Any]] = None,
    ):
        self.port = port
        self.risk_manager = risk_manager
        self.strategy_manager = strategy_manager
        self.logger = logging.getLogger('metrics_exporter')

        self.base_path = Path(base_path) if base_path else Path(__file__).resolve().parents[2]

        self.metrics = {
            'bot_status': {},
            'system_metrics': {},
            'trading_metrics': {},
            'neural_metrics': {},
            'performance_metrics': {},
        }

        self.running = False
        self.update_thread: Optional[threading.Thread] = None
        self._http_thread: Optional[threading.Thread] = None
        self._http_server: Optional[socketserver.ThreadingTCPServer] = None
        self.shutdown_event: Optional[threading.Event] = None

        self.process_checks = process_checks or {
            'trading_main': ('main.py',),
        }

        default_logs = {
            'trading_bot.log': self.base_path / 'trading_bot.log',
            'trade_journal.csv': self.base_path / 'data' / 'trade_journal.csv',
        }
        if log_files:
            for name, path in log_files.items():
                default_logs[name] = Path(path)
        self.log_files = default_logs
    
    def _update_metrics_loop(self):
        """Цикл обновления метрик"""
        while self.running:
            try:
                self._update_system_metrics()
                self._update_bot_status()
                self._update_trading_metrics()
                self._update_neural_metrics()
                time.sleep(10)  # Обновляем каждые 10 секунд
            except Exception as e:
                self.logger.error(f"Ошибка обновления метрик: {e}")
                time.sleep(30)
    
    def _update_system_metrics(self):
        """Обновление системных метрик"""
        try:
            # CPU (без блокировки, корректное чтение)
            # Первый вызов инициализирует замер, второй дает корректное значение
            if not hasattr(self, '_cpu_initialized'):
                psutil.cpu_percent(interval=None)
                self._cpu_initialized = True
                cpu_percent = 0  # Для первого замера используем 0
            else:
                cpu_percent = psutil.cpu_percent(interval=None)
            cpu_count = psutil.cpu_count()
            
            # Память
            memory = psutil.virtual_memory()
            
            # Диск
            disk = psutil.disk_usage('/')
            
            # Сеть
            network = psutil.net_io_counters()
            
            self.metrics['system_metrics'] = {
                'cpu_percent': cpu_percent,
                'cpu_count': cpu_count,
                'memory_total': memory.total,
                'memory_available': memory.available,
                'memory_percent': memory.percent,
                'disk_total': disk.total,
                'disk_used': disk.used,
                'disk_percent': disk.percent,
                'network_bytes_sent': network.bytes_sent,
                'network_bytes_recv': network.bytes_recv
            }
        except Exception as e:
            self.logger.error(f"Ошибка обновления системных метрик: {e}")
    
    def _update_bot_status(self):
        """Обновление статуса ключевых процессов системы."""
        try:
            running_cmdlines: list[str] = []
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    cmdline = proc.info.get('cmdline') or []
                    if cmdline:
                        running_cmdlines.append(' '.join(cmdline))
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

            bot_status = {}
            for label, patterns in self.process_checks.items():
                patterns_tuple = tuple(patterns) if isinstance(patterns, (list, tuple)) else (patterns,)
                is_running = any(
                    all(pattern in cmd for pattern in patterns_tuple)
                    for cmd in running_cmdlines
                )
                bot_status[label] = 'active' if is_running else 'inactive'

            self.metrics['bot_status'] = bot_status
        except Exception as e:
            self.logger.error(f"Ошибка обновления статуса ботов: {e}")
    
    def _update_trading_metrics(self):
        """Обновление торговых метрик"""
        try:
            trading_metrics = {}
            for name, path in self.log_files.items():
                file_path = Path(path)
                metric_key = f"{name.replace('.', '_')}_size_bytes"
                try:
                    trading_metrics[metric_key] = file_path.stat().st_size if file_path.exists() else 0
                except Exception as e:
                    trading_metrics[metric_key] = 0
                    self.logger.error(f"Ошибка проверки файла {file_path}: {e}")

            journal_path = self.log_files.get('trade_journal.csv')
            try:
                if journal_path and Path(journal_path).exists():
                    with Path(journal_path).open('r', encoding='utf-8') as f:
                        total_lines = sum(1 for _ in f)
                    trading_metrics['total_signals'] = max(total_lines - 1, 0)
                else:
                    trading_metrics['total_signals'] = 0
            except Exception as e:
                trading_metrics['total_signals'] = 0
                self.logger.error(f"Ошибка подсчета сигналов: {e}")

            # Статус API подключения
            try:
                from bot.core.enhanced_api_connection import get_enhanced_connection_manager

                connection_manager = get_enhanced_connection_manager()
                if connection_manager:
                    health = connection_manager.get_connection_health()
                    trading_metrics['api_connection_state'] = health.get('state')
                    trading_metrics['api_consecutive_failures'] = health.get('consecutive_failures')
                    trading_metrics['api_response_time'] = (
                        health.get('endpoint_response_time') or 0.0
                    )
            except Exception as api_metrics_error:
                self.logger.error(f"Ошибка получения метрик API: {api_metrics_error}")

            self.metrics['trading_metrics'] = trading_metrics
        except Exception as e:
            self.logger.error(f"Ошибка обновления торговых метрик: {e}")
    
    def _update_neural_metrics(self):
        """Обновление метрик нейронной сети"""
        try:
            neural_metrics = {}
            
            # Проверяем файлы нейронной сети
            neural_files = {
                'model': self.base_path / 'data' / 'ai' / 'neural_trader_model.json',
                'state': self.base_path / 'data' / 'ai' / 'neural_integration_state.json',
            }
            
            for name, path in neural_files.items():
                try:
                    file_path = Path(path)
                    if file_path.exists():
                        size = file_path.stat().st_size
                        neural_metrics[f'{name}_size_bytes'] = size

                        with file_path.open('r', encoding='utf-8') as f:
                            data = json.load(f)
                            if name == 'model':
                                neural_metrics['total_bets'] = data.get('total_bets', 0)
                                neural_metrics['winning_bets'] = data.get('winning_bets', 0)
                                neural_metrics['current_balance'] = data.get('current_balance', 1000.0)
                    else:
                        neural_metrics[f'{name}_size_bytes'] = 0
                        if name == 'model':
                            neural_metrics['total_bets'] = 0
                            neural_metrics['winning_bets'] = 0
                            neural_metrics['current_balance'] = 1000.0
                except Exception as e:
                    neural_metrics[f'{name}_size_bytes'] = 0
                    if name == 'model':
                        neural_metrics['total_bets'] = 0
                        neural_metrics['winning_bets'] = 0
                        neural_metrics['current_balance'] = 1000.0
                    self.logger.error(f"Ошибка проверки файла {path}: {e}")

            self.metrics['neural_metrics'] = neural_metrics
        except Exception as e:
            self.logger.error(f"Ошибка обновления метрик нейронной сети: {e}")

    def _start_update_thread(self):
        if self.update_thread and self.update_thread.is_alive():
            return
        self.update_thread = threading.Thread(target=self._update_metrics_loop, daemon=True)
        self.update_thread.start()

    def _serve_http(self):
        exporter = self

        class MetricsHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == '/metrics':
                    payload = exporter.get_prometheus_metrics().encode()
                    self.send_response(200)
                    self.send_header('Content-type', 'text/plain; version=0.0.4; charset=utf-8')
                    self.send_header('Content-Length', str(len(payload)))
                    self.end_headers()
                    self.wfile.write(payload)
                else:
                    self.send_response(404)
                    self.end_headers()

            def log_message(self, format, *args):  # noqa: A003 (signature fixed by BaseHTTPRequestHandler)
                # Подавляем стандартный HTTP-лог, чтобы не замусоривать stdout
                exporter.logger.debug("HTTP %s - %s", self.path, format % args)

        class MetricsServer(socketserver.ThreadingTCPServer):
            allow_reuse_address = True

        try:
            with MetricsServer(('0.0.0.0', self.port), MetricsHandler) as server:
                server.timeout = 0.5
                self._http_server = server
                self.logger.info('Метрики доступны на http://0.0.0.0:%s/metrics', self.port)

                while self.running:
                    server.handle_request()
        except OSError as exc:
            self.logger.error('Не удалось запустить HTTP сервер метрик: %s', exc)
            self.running = False
        finally:
            self._http_server = None

    def _start_http_server(self):
        if self._http_thread and self._http_thread.is_alive():
            return
        self._http_thread = threading.Thread(target=self._serve_http, daemon=True)
        self._http_thread.start()

    def start(self, shutdown_event: Optional[threading.Event] = None) -> None:
        if self.running:
            return

        self.running = True
        self.shutdown_event = shutdown_event
        self._start_update_thread()
        self._start_http_server()

        if shutdown_event is not None:
            def _wait_for_shutdown():
                shutdown_event.wait()
                self.stop()

            threading.Thread(target=_wait_for_shutdown, daemon=True).start()

    def stop(self) -> None:
        if not self.running:
            return

        self.running = False

        if self._http_server is not None:
            try:
                self._http_server.shutdown()
            except Exception:
                pass

        if self.update_thread and self.update_thread.is_alive():
            self.update_thread.join(timeout=2)

        if self._http_thread and self._http_thread.is_alive():
            self._http_thread.join(timeout=2)

    def get_prometheus_metrics(self) -> str:
        """Формирует метрики в формате Prometheus"""
        metrics_lines = []
        
        # Системные метрики
        system = self.metrics.get('system_metrics', {})
        metrics_lines.append(f"# HELP system_cpu_percent CPU usage percentage")
        metrics_lines.append(f"# TYPE system_cpu_percent gauge")
        metrics_lines.append(f"system_cpu_percent {system.get('cpu_percent', 0)}")
        
        metrics_lines.append(f"# HELP system_memory_percent Memory usage percentage")
        metrics_lines.append(f"# TYPE system_memory_percent gauge")
        metrics_lines.append(f"system_memory_percent {system.get('memory_percent', 0)}")
        
        metrics_lines.append(f"# HELP system_disk_percent Disk usage percentage")
        metrics_lines.append(f"# TYPE system_disk_percent gauge")
        metrics_lines.append(f"system_disk_percent {system.get('disk_percent', 0)}")
        
        # Статус ботов
        bot_status = self.metrics.get('bot_status', {})
        for service, status in bot_status.items():
            status_value = 1 if status == 'active' else 0
            metrics_lines.append(f"# HELP bot_status_{service.replace('.', '_')} Bot service status")
            metrics_lines.append(f"# TYPE bot_status_{service.replace('.', '_')} gauge")
            metrics_lines.append(f"bot_status_{service.replace('.', '_')} {status_value}")
        
        # Торговые метрики
        trading = self.metrics.get('trading_metrics', {})
        metrics_lines.append(f"# HELP trading_total_signals Total number of trading signals")
        metrics_lines.append(f"# TYPE trading_total_signals counter")
        metrics_lines.append(f"trading_total_signals {trading.get('total_signals', 0)}")
        
        # Метрики нейронной сети
        neural = self.metrics.get('neural_metrics', {})
        metrics_lines.append(f"# HELP neural_total_bets Total number of neural network bets")
        metrics_lines.append(f"# TYPE neural_total_bets counter")
        metrics_lines.append(f"neural_total_bets {neural.get('total_bets', 0)}")

        metrics_lines.append(f"# HELP neural_winning_bets Number of winning bets")
        metrics_lines.append(f"# TYPE neural_winning_bets counter")
        metrics_lines.append(f"neural_winning_bets {neural.get('winning_bets', 0)}")

        metrics_lines.append(f"# HELP neural_balance Current neural network balance")
        metrics_lines.append(f"# TYPE neural_balance gauge")
        metrics_lines.append(f"neural_balance {neural.get('current_balance', 1000.0)}")

        # Новые метрики оптимизаций (если доступны)
        performance = self.metrics.get('performance_metrics', {})
        if performance:
            metrics_lines.append(f"# HELP strategy_latency_ms Average strategy execution latency")
            metrics_lines.append(f"# TYPE strategy_latency_ms gauge")
            metrics_lines.append(f"strategy_latency_ms {performance.get('avg_latency', 0)}")

            metrics_lines.append(f"# HELP ttl_cache_hit_rate TTL cache hit rate percentage")
            metrics_lines.append(f"# TYPE ttl_cache_hit_rate gauge")
            metrics_lines.append(f"ttl_cache_hit_rate {performance.get('cache_hit_rate', 0)}")

        return '\n'.join(metrics_lines)

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Экспортер метрик для торговых ботов')
    parser.add_argument('--port', type=int, default=8000, help='Порт для HTTP сервера')
    args = parser.parse_args()
    
    # Настройка логирования
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    exporter = MetricsExporter(port=args.port)
    try:
        exporter.start()
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        exporter.logger.info('Остановка сервера метрик')
        exporter.stop()
