"""
📊 МОНИТОРИНГ ЗДОРОВЬЯ API
Real-time dashboard для отслеживания состояния API подключений
"""

import threading
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List
import logging

class APIHealthMonitor:
    """Монитор здоровья API подключений"""

    def __init__(self):
        self.logger = logging.getLogger('api_health_monitor')

        # Метрики
        self.metrics_history = []
        self.current_metrics = {}

        # Алерты
        self.alert_thresholds = {
            'response_time_warning': 2.0,  # секунды
            'response_time_critical': 5.0,
            'failure_rate_warning': 0.1,   # 10%
            'failure_rate_critical': 0.25, # 25%
        }

        self.monitoring_active = False
        self.monitoring_thread = None

    def start_monitoring(self):
        """Запуск мониторинга"""
        if not self.monitoring_active:
            self.monitoring_active = True
            self.monitoring_thread = threading.Thread(
                target=self._monitoring_worker,
                daemon=True
            )
            self.monitoring_thread.start()
            self.logger.info("📊 API Health мониторинг запущен")

    def _monitoring_worker(self):
        """Рабочий поток мониторинга"""
        while self.monitoring_active:
            try:
                self._collect_metrics()
                self._check_alerts()
                time.sleep(60)  # Каждую минуту
            except Exception as e:
                self.logger.error(f"Ошибка мониторинга API health: {e}")
                time.sleep(30)

    def _collect_metrics(self):
        """Сбор метрик API"""
        try:
            from bot.core.enhanced_api_connection import get_enhanced_connection_manager
            from bot.core.rate_limiter import get_rate_limiter

            # Метрики подключения
            connection_manager = get_enhanced_connection_manager()
            if connection_manager:
                health = connection_manager.get_connection_health()

                # Метрики rate limiter
                rate_limiter = get_rate_limiter()
                rate_stats = rate_limiter.get_global_status() if rate_limiter else {}

                # Собираем общие метрики
                metrics = {
                    'timestamp': datetime.now(),
                    'connection_state': health.get('state'),
                    'response_time': health.get('endpoint_response_time', 0),
                    'consecutive_failures': health.get('consecutive_failures', 0),
                    'total_requests': health.get('stats', {}).get('total_requests', 0),
                    'failed_requests': health.get('stats', {}).get('failed_requests', 0),
                    'cache_hits': health.get('stats', {}).get('cache_hits', 0),
                    'rate_limit_blocks': rate_stats.get('stats', {}).get('blocked_requests', 0),
                    'cached_items': health.get('cached_items', 0)
                }

                # Вычисляем производные метрики
                if metrics['total_requests'] > 0:
                    metrics['failure_rate'] = metrics['failed_requests'] / metrics['total_requests']
                    metrics['cache_hit_rate'] = metrics['cache_hits'] / metrics['total_requests']
                else:
                    metrics['failure_rate'] = 0
                    metrics['cache_hit_rate'] = 0

                self.current_metrics = metrics
                self.metrics_history.append(metrics)

                # Ограничиваем историю (24 часа при сборе каждую минуту)
                if len(self.metrics_history) > 1440:
                    self.metrics_history = self.metrics_history[-1440:]

        except Exception as e:
            self.logger.error(f"Ошибка сбора метрик: {e}")

    def _check_alerts(self):
        """Проверка алертов"""
        if not self.current_metrics:
            return

        metrics = self.current_metrics

        # Проверка времени отклика
        response_time = metrics.get('response_time', 0)
        if response_time > self.alert_thresholds['response_time_critical']:
            self._send_alert(
                'CRITICAL',
                f"API response time critical: {response_time:.2f}s",
                {'response_time': response_time}
            )
        elif response_time > self.alert_thresholds['response_time_warning']:
            self._send_alert(
                'WARNING',
                f"API response time high: {response_time:.2f}s",
                {'response_time': response_time}
            )

        # Проверка частоты ошибок
        failure_rate = metrics.get('failure_rate', 0)
        if failure_rate > self.alert_thresholds['failure_rate_critical']:
            self._send_alert(
                'CRITICAL',
                f"API failure rate critical: {failure_rate*100:.1f}%",
                {'failure_rate': failure_rate}
            )
        elif failure_rate > self.alert_thresholds['failure_rate_warning']:
            self._send_alert(
                'WARNING',
                f"API failure rate high: {failure_rate*100:.1f}%",
                {'failure_rate': failure_rate}
            )

    def _send_alert(self, level: str, message: str, details: Dict[str, Any]):
        """Отправка алерта"""
        self.logger.warning(f"📊 API HEALTH ALERT [{level}]: {message}")

        # Отправляем через blocking alerts систему (если доступно)
        try:
            from bot.core.blocking_alerts import report_order_block
            report_order_block(
                reason="api_performance",
                symbol="ALL",
                strategy="MONITORING",
                message=f"API Health Alert: {message}",
                details=details
            )
        except ImportError:
            self.logger.warning("Blocking alerts система недоступна")

    def get_dashboard_data(self) -> Dict[str, Any]:
        """Получить данные для dashboard"""
        if not self.current_metrics:
            return {"status": "no_data", "message": "Мониторинг не активен"}

        # Текущие метрики
        current = self.current_metrics

        # Статистика за последний час
        hour_ago = datetime.now() - timedelta(hours=1)
        recent_metrics = [m for m in self.metrics_history if m['timestamp'] > hour_ago]

        if recent_metrics:
            avg_response_time = sum(m['response_time'] for m in recent_metrics) / len(recent_metrics)
            avg_failure_rate = sum(m['failure_rate'] for m in recent_metrics) / len(recent_metrics)
            total_requests_hour = recent_metrics[-1]['total_requests'] - recent_metrics[0]['total_requests']
        else:
            avg_response_time = current.get('response_time', 0)
            avg_failure_rate = current.get('failure_rate', 0)
            total_requests_hour = 0

        return {
            "status": "active",
            "current": {
                "connection_state": current.get('connection_state'),
                "response_time": current.get('response_time'),
                "failure_rate": current.get('failure_rate'),
                "consecutive_failures": current.get('consecutive_failures'),
                "cache_hit_rate": current.get('cache_hit_rate'),
                "cached_items": current.get('cached_items')
            },
            "hourly_stats": {
                "avg_response_time": avg_response_time,
                "avg_failure_rate": avg_failure_rate,
                "total_requests": total_requests_hour,
                "data_points": len(recent_metrics)
            },
            "alerts": {
                "response_time_status": "critical" if current.get('response_time', 0) > self.alert_thresholds['response_time_critical'] else
                                      "warning" if current.get('response_time', 0) > self.alert_thresholds['response_time_warning'] else "ok",
                "failure_rate_status": "critical" if current.get('failure_rate', 0) > self.alert_thresholds['failure_rate_critical'] else
                                      "warning" if current.get('failure_rate', 0) > self.alert_thresholds['failure_rate_warning'] else "ok"
            }
        }

    def stop(self):
        """Остановка мониторинга"""
        self.monitoring_active = False
        if self.monitoring_thread and self.monitoring_thread.is_alive():
            self.monitoring_thread.join(timeout=5)
        self.logger.info("🛑 API Health мониторинг остановлен")

# Глобальный экземпляр монитора
_health_monitor = None

def get_api_health_monitor() -> APIHealthMonitor:
    """Получить глобальный монитор API"""
    global _health_monitor
    if _health_monitor is None:
        _health_monitor = APIHealthMonitor()
        _health_monitor.start_monitoring()
    return _health_monitor