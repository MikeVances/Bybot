#!/usr/bin/env python3
"""
Экспортер метрик для торговых ботов
Предоставляет метрики в формате Prometheus
"""

import time
import psutil
import subprocess
import logging
from datetime import datetime
from typing import Dict, Any
import threading
import json
import os

class MetricsExporter:
    def __init__(self, port: int = 8000):
        self.port = port
        self.logger = logging.getLogger('metrics_exporter')
        
        # Метрики
        self.metrics = {
            'bot_status': {},
            'system_metrics': {},
            'trading_metrics': {},
            'neural_metrics': {}
        }
        
        # Запускаем обновление метрик в отдельном потоке
        self.running = True
        self.update_thread = threading.Thread(target=self._update_metrics_loop)
        self.update_thread.daemon = True
        self.update_thread.start()
    
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
            # CPU
            cpu_percent = psutil.cpu_percent(interval=1)
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
        """Обновление статуса ботов"""
        try:
            services = ['bybot-trading.service', 'bybot-telegram.service', 'lerabot.service']
            bot_status = {}
            
            for service in services:
                try:
                    result = subprocess.run(['/bin/systemctl', 'is-active', service], 
                                          capture_output=True, text=True)
                    status = result.stdout.strip()
                    bot_status[service] = status
                except Exception as e:
                    bot_status[service] = 'unknown'
                    self.logger.error(f"Ошибка проверки статуса {service}: {e}")
            
            self.metrics['bot_status'] = bot_status
        except Exception as e:
            self.logger.error(f"Ошибка обновления статуса ботов: {e}")
    
    def _update_trading_metrics(self):
        """Обновление торговых метрик"""
        try:
            # Проверяем размер логов
            log_files = {
                'bot.log': '/home/mikevance/bots/bybot/bot.log',
                'trade_journal.csv': '/home/mikevance/bots/bybot/data/trade_journal.csv'
            }
            
            trading_metrics = {}
            for name, path in log_files.items():
                try:
                    if os.path.exists(path):
                        size = os.path.getsize(path)
                        trading_metrics[f'{name}_size'] = size
                    else:
                        trading_metrics[f'{name}_size'] = 0
                except Exception as e:
                    trading_metrics[f'{name}_size'] = 0
                    self.logger.error(f"Ошибка проверки файла {path}: {e}")
            
            # Проверяем количество сигналов в журнале
            try:
                if os.path.exists('/home/mikevance/bots/bybot/data/trade_journal.csv'):
                    with open('/home/mikevance/bots/bybot/data/trade_journal.csv', 'r') as f:
                        lines = f.readlines()
                        trading_metrics['total_signals'] = len(lines) - 1  # Минус заголовок
                else:
                    trading_metrics['total_signals'] = 0
            except Exception as e:
                trading_metrics['total_signals'] = 0
                self.logger.error(f"Ошибка подсчета сигналов: {e}")
            
            self.metrics['trading_metrics'] = trading_metrics
        except Exception as e:
            self.logger.error(f"Ошибка обновления торговых метрик: {e}")
    
    def _update_neural_metrics(self):
        """Обновление метрик нейронной сети"""
        try:
            neural_metrics = {}
            
            # Проверяем файлы нейронной сети
            neural_files = {
                'model': '/home/mikevance/bots/bybot/data/ai/neural_trader_model.json',
                'state': '/home/mikevance/bots/bybot/data/ai/neural_integration_state.json'
            }
            
            for name, path in neural_files.items():
                try:
                    if os.path.exists(path):
                        size = os.path.getsize(path)
                        neural_metrics[f'{name}_size'] = size
                        
                        # Читаем статистику из файла
                        with open(path, 'r') as f:
                            data = json.load(f)
                            if name == 'model':
                                neural_metrics['total_bets'] = data.get('total_bets', 0)
                                neural_metrics['winning_bets'] = data.get('winning_bets', 0)
                                neural_metrics['current_balance'] = data.get('current_balance', 1000.0)
                    else:
                        neural_metrics[f'{name}_size'] = 0
                        if name == 'model':
                            neural_metrics['total_bets'] = 0
                            neural_metrics['winning_bets'] = 0
                            neural_metrics['current_balance'] = 1000.0
                except Exception as e:
                    neural_metrics[f'{name}_size'] = 0
                    if name == 'model':
                        neural_metrics['total_bets'] = 0
                        neural_metrics['winning_bets'] = 0
                        neural_metrics['current_balance'] = 1000.0
                    self.logger.error(f"Ошибка проверки файла {path}: {e}")
            
            self.metrics['neural_metrics'] = neural_metrics
        except Exception as e:
            self.logger.error(f"Ошибка обновления метрик нейронной сети: {e}")
    
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
        
        return '\n'.join(metrics_lines)
    
    def start_server(self):
        """Запускает HTTP сервер для экспорта метрик"""
        from http.server import HTTPServer, BaseHTTPRequestHandler
        import socketserver
        
        class MetricsHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == '/metrics':
                    self.send_response(200)
                    self.send_header('Content-type', 'text/plain')
                    self.end_headers()
                    self.wfile.write(self.server.metrics_exporter.get_prometheus_metrics().encode())
                else:
                    self.send_response(404)
                    self.end_headers()
        
        class MetricsServer(socketserver.ThreadingTCPServer):
            def __init__(self, server_address, RequestHandlerClass, metrics_exporter):
                self.metrics_exporter = metrics_exporter
                super().__init__(server_address, RequestHandlerClass)
        
        server = MetricsServer(('0.0.0.0', self.port), MetricsHandler, self)
        self.logger.info(f"Метрики доступны на http://localhost:{self.port}/metrics")
        
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            self.logger.info("Остановка сервера метрик")
            self.running = False
            server.shutdown()

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
    exporter.start_server() 